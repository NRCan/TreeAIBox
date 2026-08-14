#!/usr/bin/env python
"""
Semantic Field Assignment (sklearn feature-vector method)
=========================================================

Assign LiDAR trees (from the enhancer's trunk_metrics export) to
field-measured trees using a combination of spatial proximity and a
hand-built "semantic" feature vector.

This version uses ONLY packages that are already installed in the
component_extraction environment (numpy, scipy, sklearn, pyogrio,
geopandas). No new installs are required.

The LiDAR side is read from the enhancer's exported trunk_metrics CSV
(which already contains tree height, DBH, XY location, volume, and point
count per tree) instead of re-reading the LAS.

The "semantic" part comes from encoding each tree's attributes
(species, height class, DBH, crown class, ...) into a numeric feature
vector, then matching LiDAR trees to field trees by nearest-neighbour
search in that feature space, constrained by XY distance.

Height classes (field `hightlevel`):
    1 = < 5 m
    2 = 5-10 m
    3 = 10-15 m
    4 = 15-20 m
    5 = > 20 m

Usage
-----
    python semantic_field_assignment.py \
        --gdb "path/to/Field Data.gdb" \
        --layer TreePosition_LiDARGeom_Transect1stemCenter \
        --metrics "path/to/..._trunk_metrics.csv" \
        --out "path/to/output_dir" \
        [--tolerance 2.0] [--weight-semantic 0.5] [--height-class-field hightlevel]

Outputs
-------
    field_assignment.csv      - one row per matched LiDAR tree
    match_report.txt          - human-readable summary
"""

import argparse
import os
import sys
import time
from collections import defaultdict

import numpy as np


# ---------------------------------------------------------------------------
# Height class helpers
# ---------------------------------------------------------------------------
HEIGHT_CLASS_BINS = [0.0, 5.0, 10.0, 15.0, 20.0, np.inf]
HEIGHT_CLASS_LABELS = [1, 2, 3, 4, 5]


def height_to_class(height_m):
    """Map a height in metres to a field height class (1-5)."""
    if height_m is None or not np.isfinite(height_m) or height_m < 0:
        return 0  # unknown
    for label, (lo, hi) in zip(HEIGHT_CLASS_LABELS, zip(HEIGHT_CLASS_BINS[:-1], HEIGHT_CLASS_BINS[1:])):
        if lo <= height_m < hi:
            return label
    return 5  # >= 20 m


# ---------------------------------------------------------------------------
# Feature vector builder
# ---------------------------------------------------------------------------
class FeatureEncoder:
    """Build a numeric feature vector describing a tree's attributes.

    The vector is the "semantic" representation used for matching. It is
    built from the same attribute space for both field and LiDAR trees so
    they can be compared directly.
    """

    def __init__(self):
        # Categorical vocabularies (extend as needed). Order matters and must
        # stay consistent between field and LiDAR encodings.
        self.species_vocab = []
        self.crown_vocab = []
        self.health_vocab = []
        self._species_index = {}
        self._crown_index = {}
        self._health_index = {}

    def fit(self, field_df, species_col='species', crown_col='crownclass', health_col='healthleve'):
        """Learn categorical vocabularies from the field data."""
        for col, index, vocab in (
            (species_col, self._species_index, self.species_vocab),
            (crown_col, self._crown_index, self.crown_vocab),
            (health_col, self._health_index, self.health_vocab),
        ):
            if col in field_df.columns:
                for val in field_df[col].dropna().unique():
                    key = str(val).strip().lower()
                    if key and key not in index:
                        index[key] = len(vocab)
                        vocab.append(key)
        return self

    def _onehot(self, value, index, vocab):
        vec = np.zeros(len(vocab), dtype=float)
        key = str(value).strip().lower() if value is not None else ''
        idx = index.get(key)
        if idx is not None:
            vec[idx] = 1.0
        return vec

    def encode(self, species=None, height_class=0, dbh_cm=None,
               crown_class=None, health=None, volume_m3=None, n_points=None):
        """Return the feature vector for one tree."""
        parts = []
        parts.append(self._onehot(species, self._species_index, self.species_vocab))
        parts.append(self._onehot(crown_class, self._crown_index, self.crown_vocab))
        parts.append(self._onehot(health, self._health_index, self.health_vocab))

        # Height class as a small one-hot (5 classes + unknown)
        hc = np.zeros(6, dtype=float)
        hc[int(height_class) if 0 <= int(height_class) <= 5 else 0] = 1.0
        parts.append(hc)

        # Continuous attributes, normalized to roughly [0,1]
        dbh = float(dbh_cm) / 100.0 if dbh_cm is not None and np.isfinite(dbh_cm) else 0.0
        vol = float(volume_m3) if volume_m3 is not None and np.isfinite(volume_m3) else 0.0
        npts = float(n_points) / 5000.0 if n_points is not None and np.isfinite(n_points) else 0.0
        parts.append(np.array([dbh, vol, npts], dtype=float))

        return np.concatenate(parts)


# ---------------------------------------------------------------------------
# LiDAR reading (from enhancer trunk_metrics CSV)
# ---------------------------------------------------------------------------
def read_lidar_metrics(metrics_path, tree_id_field='tree_ids',
                       height_field='tree_height_m', dbh_field='dbh_cm',
                       x_field='location_x_m', y_field='location_y_m',
                       volume_field='total_volume_m3', npoints_field='total_points'):
    """Read per-tree LiDAR metrics from the enhancer's trunk_metrics CSV.

    Returns
    -------
    trees : dict
        tree_id -> {'height_m': float, 'height_class': int,
                    'dbh_cm': float, 'n_points': int,
                    'volume_m3': float, 'centroid_xy': (2,) array}
    """
    import csv

    trees = {}
    with open(metrics_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                tid = int(float(row[tree_id_field]))
            except (ValueError, TypeError, KeyError):
                continue

            def _num(col):
                try:
                    v = float(row[col])
                    return v if np.isfinite(v) else None
                except (ValueError, TypeError, KeyError):
                    return None

            height_m = _num(height_field)
            x = _num(x_field)
            y = _num(y_field)
            if height_m is None or x is None or y is None:
                continue

            trees[tid] = {
                'height_m': height_m,
                'height_class': height_to_class(height_m),
                'dbh_cm': _num(dbh_field),
                'n_points': int(_num(npoints_field) or 0),
                'volume_m3': _num(volume_field),
                'centroid_xy': np.array([x, y]),
            }
    return trees


# ---------------------------------------------------------------------------
# Field GDB reading
# ---------------------------------------------------------------------------
def read_field_points(gdb_path, layer, height_class_field='hightlevel',
                      dbh_field='dbh_cm', species_field='species',
                      crown_field='crownclass', health_field='healthleve'):
    """Read field tree points from a File Geodatabase.

    Returns
    -------
    field_trees : list of dict
        Each dict has 'treeid', 'xy', 'height_class', 'dbh_cm', 'species',
        'crown_class', 'health', and 'raw' (the full row).
    """
    import pyogrio

    gdf = pyogrio.read_dataframe(gdb_path, layer=layer)
    if gdf.empty:
        raise ValueError(f"Layer '{layer}' has no features")

    field_trees = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        xy = np.array([geom.x, geom.y], dtype=float)

        def _get(col, default=None):
            if col in gdf.columns:
                v = row[col]
                return default if v is None else v
            return default

        field_trees.append({
            'treeid': _get('treeid', idx),
            'xy': xy,
            'height_class': int(_get(height_class_field, 0) or 0),
            'dbh_cm': _get(dbh_field),
            'species': _get(species_field),
            'crown_class': _get(crown_field),
            'health': _get(health_field),
            'raw': row,
        })
    return field_trees


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def match_trees(field_trees, lidar_trees, encoder, tolerance_m=2.0,
                weight_semantic=0.5, height_class_weight=2.0):
    """Match LiDAR trees to field trees.

    For each LiDAR tree:
      1. Spatial gate: only field points within `tolerance_m` XY distance.
      2. Semantic score: cosine similarity of feature vectors.
      3. Height-class bonus: strong preference for matching height classes.
      4. Combined score = (1-w)*spatial + w*semantic (+ height bonus).
      5. Greedy one-to-one assignment.

    Returns
    -------
    assignments : list of dict
        One per LiDAR tree with matched field treeid (or None).
    """
    from sklearn.preprocessing import normalize
    from scipy.spatial.distance import cdist

    # Encode all field trees
    field_vecs = []
    for ft in field_trees:
        field_vecs.append(encoder.encode(
            species=ft['species'],
            height_class=ft['height_class'],
            dbh_cm=ft['dbh_cm'],
            crown_class=ft['crown_class'],
            health=ft['health'],
        ))
    field_vecs = np.array(field_vecs, dtype=float)
    field_vecs_n = normalize(field_vecs, norm='l2')

    field_xy = np.array([ft['xy'] for ft in field_trees], dtype=float)

    # Encode all LiDAR trees
    lidar_ids = sorted(lidar_trees.keys())
    lidar_vecs = []
    for tid in lidar_ids:
        lt = lidar_trees[tid]
        lidar_vecs.append(encoder.encode(
            height_class=lt['height_class'],
            dbh_cm=lt['dbh_cm'],
            volume_m3=lt['volume_m3'],
            n_points=lt['n_points'],
        ))
    lidar_vecs = np.array(lidar_vecs, dtype=float)
    lidar_vecs_n = normalize(lidar_vecs, norm='l2')

    # Spatial distance matrix (LiDAR x field)
    spatial = cdist(np.array([lidar_trees[t]['centroid_xy'] for t in lidar_ids]),
                    field_xy, metric='euclidean')

    # Semantic similarity matrix (cosine)
    semantic = lidar_vecs_n @ field_vecs_n.T  # higher = more similar

    # Height-class match bonus matrix
    hc_bonus = np.zeros_like(semantic)
    for i, tid in enumerate(lidar_ids):
        lhc = lidar_trees[tid]['height_class']
        for j, ft in enumerate(field_trees):
            if lhc == ft['height_class'] and lhc != 0:
                hc_bonus[i, j] = height_class_weight

    # Combined score (higher = better)
    # Normalize spatial to [0,1] similarity (1 - dist/tolerance)
    spatial_sim = np.clip(1.0 - spatial / max(tolerance_m, 1e-9), 0.0, 1.0)
    combined = (1.0 - weight_semantic) * spatial_sim + weight_semantic * semantic + hc_bonus

    # Greedy one-to-one assignment (best available field point per LiDAR tree)
    used_field = set()
    assignments = []
    order = np.argsort(-np.max(combined, axis=1))  # process most-confident first
    for i in order:
        tid = lidar_ids[i]
        # Candidates within spatial tolerance
        cand = np.where(spatial[i] <= tolerance_m)[0]
        if len(cand) == 0:
            assignments.append({'lidar_tree_id': tid, 'field_treeid': None,
                                'distance_m': None, 'semantic_sim': None,
                                'score': None, 'height_class': lidar_trees[tid]['height_class']})
            continue
        # Exclude already-used field points
        cand = [j for j in cand if j not in used_field]
        if not cand:
            assignments.append({'lidar_tree_id': tid, 'field_treeid': None,
                                'distance_m': None, 'semantic_sim': None,
                                'score': None, 'height_class': lidar_trees[tid]['height_class']})
            continue
        best_j = max(cand, key=lambda j: combined[i, j])
        used_field.add(best_j)
        ft = field_trees[best_j]
        assignments.append({
            'lidar_tree_id': tid,
            'field_treeid': ft['treeid'],
            'distance_m': float(spatial[i, best_j]),
            'semantic_sim': float(semantic[i, best_j]),
            'score': float(combined[i, best_j]),
            'height_class': lidar_trees[tid]['height_class'],
            'field_height_class': ft['height_class'],
            'field_dbh_cm': ft['dbh_cm'],
            'field_species': ft['species'],
        })
    return assignments


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def write_outputs(assignments, lidar_trees, out_dir, field_trees):
    os.makedirs(out_dir, exist_ok=True)

    # 1. CSV
    csv_path = os.path.join(out_dir, 'field_assignment.csv')
    import csv
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'lidar_tree_id', 'field_treeid', 'height_m', 'height_class',
            'dbh_cm', 'volume_m3', 'n_points', 'distance_m', 'semantic_sim', 'score',
            'field_height_class', 'field_dbh_cm', 'field_species',
        ])
        writer.writeheader()
        for a in assignments:
            lt = lidar_trees[a['lidar_tree_id']]
            writer.writerow({
                'lidar_tree_id': a['lidar_tree_id'],
                'field_treeid': a['field_treeid'],
                'height_m': round(lt['height_m'], 3),
                'height_class': a['height_class'],
                'dbh_cm': round(lt['dbh_cm'], 3) if lt['dbh_cm'] is not None else '',
                'volume_m3': round(lt['volume_m3'], 4) if lt['volume_m3'] is not None else '',
                'n_points': lt['n_points'],
                'distance_m': round(a['distance_m'], 3) if a['distance_m'] is not None else '',
                'semantic_sim': round(a['semantic_sim'], 4) if a['semantic_sim'] is not None else '',
                'score': round(a['score'], 4) if a['score'] is not None else '',
                'field_height_class': a.get('field_height_class', ''),
                'field_dbh_cm': a.get('field_dbh_cm', ''),
                'field_species': a.get('field_species', ''),
            })

    # 2. Report
    report_path = os.path.join(out_dir, 'match_report.txt')
    matched = [a for a in assignments if a['field_treeid'] is not None]
    unmatched = [a for a in assignments if a['field_treeid'] is None]
    with open(report_path, 'w') as f:
        f.write("Semantic Field Assignment Report\n")
        f.write("=" * 50 + "\n")
        f.write(f"Field trees: {len(field_trees)}\n")
        f.write(f"LiDAR trees: {len(lidar_trees)}\n")
        f.write(f"Matched: {len(matched)}\n")
        f.write(f"Unmatched: {len(unmatched)}\n")
        if matched:
            dists = [a['distance_m'] for a in matched if a['distance_m'] is not None]
            sims = [a['semantic_sim'] for a in matched if a['semantic_sim'] is not None]
            f.write(f"Mean match distance: {np.mean(dists):.3f} m\n" if dists else "")
            f.write(f"Mean semantic similarity: {np.mean(sims):.4f}\n" if sims else "")
        f.write("\nUnmatched LiDAR trees:\n")
        for a in unmatched:
            f.write(f"  lidar_tree_id={a['lidar_tree_id']} height_class={a['height_class']}\n")

    print(f"Wrote: {csv_path}")
    print(f"Wrote: {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Semantic field assignment (sklearn method)')
    parser.add_argument('--gdb', required=True, help='Path to .gdb folder')
    parser.add_argument('--layer', default='TreePosition_LiDARGeom_Transect1stemCenter',
                        help='Field point feature layer name')
    parser.add_argument('--metrics', required=True,
                        help='Path to enhancer trunk_metrics CSV (LiDAR side)')
    parser.add_argument('--out', default='semantic_assignment_out', help='Output directory')
    parser.add_argument('--tolerance', type=float, default=2.0,
                        help='Max XY distance (m) to consider a match')
    parser.add_argument('--weight-semantic', type=float, default=0.5,
                        help='Weight (0-1) for semantic vs spatial in combined score')
    parser.add_argument('--height-class-field', default='hightlevel',
                        help='Field column holding the height class')
    args = parser.parse_args()

    t0 = time.time()

    print("Reading field points...")
    field_trees = read_field_points(
        args.gdb, args.layer,
        height_class_field=args.height_class_field,
    )
    print(f"  {len(field_trees)} field trees")

    print("Reading LiDAR metrics from trunk_metrics CSV...")
    lidar_trees = read_lidar_metrics(args.metrics)
    print(f"  {len(lidar_trees)} LiDAR trees")

    print("Building feature encoder...")
    import geopandas as gpd
    # Build a small DataFrame from field trees for encoder.fit
    field_df = gpd.GeoDataFrame([ft['raw'] for ft in field_trees])
    encoder = FeatureEncoder().fit(field_df)

    print("Matching...")
    assignments = match_trees(
        field_trees, lidar_trees, encoder,
        tolerance_m=args.tolerance,
        weight_semantic=args.weight_semantic,
    )

    print("Writing outputs...")
    write_outputs(assignments, lidar_trees, args.out, field_trees)

    print(f"Done in {time.time() - t0:.2f}s")


if __name__ == '__main__':
    main()
