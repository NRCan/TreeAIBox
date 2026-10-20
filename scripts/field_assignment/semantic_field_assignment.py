#!/usr/bin/env python
"""
Field Assignment (Spatial + Shared Attribute Matching)
======================================================

Assign LiDAR trees (from the enhancer's trunk_metrics export) to
field-measured trees using a combination of spatial proximity and shared
physical attributes (DBH and Tree Height / Height Class).

Key Improvements:
-----------------
1. Shared-Attribute Matching: Only compares attributes present on BOTH sides
   (XY position, DBH, and Height/Height-Class). Unshared attributes (species,
   health, volume, point count) are preserved in outputs without corrupting
   the distance metric.
2. Global Optimal Assignment: Uses the Hungarian algorithm (Linear Sum Assignment)
   to maximize overall matching quality across the entire stand rather than
   suboptimal greedy picking.
3. Smooth Ordinal & Continuous Similarities:
   - Spatial: Normalized linear decay within tolerance gate.
   - DBH: Exponential decay based on absolute cm difference.
   - Height: Smooth ordinal class similarity (off-by-1 class is scored much
     better than off-by-3) or continuous height error if field height is present.
4. Flexible Column Aliasing: Automatically resolves common field name variations
   in GDB/CSV files (e.g. TreeID, DBH, hightlevel, etc.).
5. Enhanced Diagnostics & GIS Output: Comprehensive match metrics, DBH correlation,
   and optional spatial vector line export for GIS visualization (QGIS/ArcGIS).

Height classes (field `hightlevel`):
    1 = < 5 m
    2 = 5-10 m
    3 = 10-15 m
    4 = 15-20 m
    5 = > 20 m

Usage
-----
    python semantic_field_assignment.py \\
        --gdb "path/to/Field Data.gdb" \\
        --layer TreePosition_LiDARGeom_Transect1stemCenter \\
        --metrics "path/to/..._trunk_metrics.csv" \\
        --out "path/to/output_dir" \\
        [--tolerance 2.5] [--weight-spatial 0.5] [--weight-dbh 0.25] [--weight-height 0.25] \\
        [--method optimal]

Outputs
-------
    field_assignment.csv      - Table of matched and unmatched trees with all attributes
    match_report.txt          - Comprehensive match statistics, DBH error, confusion table
    match_vectors.geojson     - (Optional) Spatial lines connecting matched trees for GIS
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist


# ---------------------------------------------------------------------------
# Height class helpers
# ---------------------------------------------------------------------------
HEIGHT_CLASS_BINS = [0.0, 5.0, 10.0, 15.0, 20.0, np.inf]
HEIGHT_CLASS_LABELS = [1, 2, 3, 4, 5]
HEIGHT_CLASS_RANGES = {
    1: "< 5m",
    2: "5-10m",
    3: "10-15m",
    4: "15-20m",
    5: "> 20m",
}
HEIGHT_CLASS_MIDPOINTS = {
    1: 2.5,
    2: 7.5,
    3: 12.5,
    4: 17.5,
    5: 22.5,
}


def height_to_class(height_m):
    """Map a continuous height in metres to a field height class (1-5)."""
    if height_m is None or not np.isfinite(height_m) or height_m < 0:
        return 0  # unknown
    for label, (lo, hi) in zip(HEIGHT_CLASS_LABELS, zip(HEIGHT_CLASS_BINS[:-1], HEIGHT_CLASS_BINS[1:])):
        if lo <= height_m < hi:
            return label
    return 5  # >= 20 m


def class_to_height_range(height_class):
    """Return human-readable height range string for a height class."""
    try:
        hc = int(height_class)
        return HEIGHT_CLASS_RANGES.get(hc, "Unknown")
    except (ValueError, TypeError):
        return "Unknown"


def class_to_midpoint_height(height_class):
    """Return estimated midpoint height in metres for a height class."""
    try:
        hc = int(height_class)
        return HEIGHT_CLASS_MIDPOINTS.get(hc, None)
    except (ValueError, TypeError):
        return None


def find_column(available_cols, preferred_name, aliases=None):
    """Case-insensitive search for column with common aliases."""
    cols_lower = {str(c).strip().lower(): c for c in available_cols}
    if preferred_name and preferred_name.lower() in cols_lower:
        return cols_lower[preferred_name.lower()]
    if aliases:
        for alias in aliases:
            if alias.lower() in cols_lower:
                return cols_lower[alias.lower()]
    return None


# ---------------------------------------------------------------------------
# LiDAR reading (from enhancer trunk_metrics CSV)
# ---------------------------------------------------------------------------
def read_lidar_metrics(metrics_path, tree_id_field='tree_ids',
                       height_field='tree_height_m', dbh_field='dbh_cm',
                       x_field='location_x_m', y_field='location_y_m',
                       volume_field='total_volume_m3', npoints_field='total_points'):
    """Read per-tree LiDAR metrics from the enhancer's trunk_metrics CSV."""
    trees = {}
    with open(metrics_path, 'r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        
        # Resolve column names with aliases
        tid_col = find_column(fieldnames, tree_id_field, ['tree_id', 'treeid', 'id', 'itc_id'])
        ht_col = find_column(fieldnames, height_field, ['height_m', 'tree_height', 'height', 'z_max'])
        dbh_col = find_column(fieldnames, dbh_field, ['dbh', 'diameter_cm', 'trunk_dbh'])
        x_col = find_column(fieldnames, x_field, ['x', 'x_m', 'centroid_x', 'location_x'])
        y_col = find_column(fieldnames, y_field, ['y', 'y_m', 'centroid_y', 'location_y'])
        vol_col = find_column(fieldnames, volume_field, ['volume_m3', 'volume', 'trunk_volume_m3'])
        npts_col = find_column(fieldnames, npoints_field, ['n_points', 'points', 'point_count'])

        if not tid_col or not x_col or not y_col:
            raise ValueError(f"CSV must contain Tree ID and XY columns. Found: {fieldnames}")

        for row in reader:
            try:
                tid = int(float(row[tid_col]))
            except (ValueError, TypeError, KeyError):
                continue

            def _num(col):
                if not col or col not in row:
                    return None
                try:
                    v = float(row[col])
                    return v if np.isfinite(v) else None
                except (ValueError, TypeError):
                    return None

            height_m = _num(ht_col)
            x = _num(x_col)
            y = _num(y_col)
            if x is None or y is None:
                continue

            trees[tid] = {
                'lidar_tree_id': tid,
                'height_m': height_m,
                'height_class': height_to_class(height_m) if height_m is not None else 0,
                'dbh_cm': _num(dbh_col),
                'n_points': int(_num(npts_col) or 0),
                'volume_m3': _num(vol_col),
                'centroid_xy': np.array([x, y], dtype=float),
            }
    return trees


def resolve_gdb_path(path):
    """Resolve actual FileGDB folder if nested inside a parent folder (e.g. unzipped folders)."""
    if not path or not os.path.exists(path):
        return path
    path = os.path.normpath(path)
    if os.path.isdir(path):
        try:
            entries = os.listdir(path)
        except OSError:
            return path
        # Direct GDB containing .gdbtable files
        if any(f.lower().endswith('.gdbtable') for f in entries):
            return path
        # Check subfolders for .gdbtable or .gdb
        for item in entries:
            sub = os.path.join(path, item)
            if os.path.isdir(sub):
                if sub.lower().endswith('.gdb'):
                    return sub
                try:
                    if any(f.lower().endswith('.gdbtable') for f in os.listdir(sub)):
                        return sub
                except OSError:
                    continue
    return path


# ---------------------------------------------------------------------------
# Field GDB reading
# ---------------------------------------------------------------------------
def read_field_points(gdb_path, layer=None, height_class_field='hightlevel',
                       dbh_field='dbh_cm', height_m_field=None,
                       tree_id_field='treeid', species_field='species',
                       crown_field='crownclass', health_field='healthleve',
                       min_height_class=1, max_height_class=5,
                       min_dbh=None, max_dbh=None, species_filter=None):
    """Read field tree points from a File Geodatabase or spatial file with optional filtering."""
    import pyogrio

    resolved_path = resolve_gdb_path(gdb_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Field data path does not exist: {gdb_path}")

    # Auto-detect layer if not supplied or if invalid
    if not layer:
        try:
            available_layers = pyogrio.list_layers(resolved_path)
            layer_names = [l[0] for l in available_layers] if len(available_layers) > 0 and isinstance(available_layers[0], (list, tuple, np.ndarray)) else list(available_layers)
            layer = layer_names[0] if layer_names else None
        except Exception:
            layer = None

    gdf = pyogrio.read_dataframe(resolved_path, layer=layer)
    if gdf.empty:
        raise ValueError(f"Layer '{layer}' has no features")

    source_crs = gdf.crs

    # ------------------------------------------------------------------
    # CRS normalization: the matching/geometry engine works in projected
    # METERS (consistent with the LiDAR trunk_metrics, which are UTM).
    # If the field layer is in a geographic CRS (lat/lon degrees), e.g. a
    # field_etl .gpkg exported to EPSG:4326, reproject its points to a
    # projected UTM CRS so distances/tolerance are meaningful in metres.
    # ------------------------------------------------------------------
    projected_xy = None
    working_crs = source_crs
    if source_crs is not None:
        try:
            from pyproj import CRS as _PCCRS
            from pyproj import Transformer as _PTrans
            _src = _PCCRS.from_user_input(source_crs)
            if _src.is_geographic:
                _xs = [geom.x for geom in gdf.geometry if geom is not None and not geom.is_empty]
                _lon = float(np.mean(_xs)) if _xs else 0.0
                _zone = int((_lon + 180) / 6) % 60 + 1
                _lat0 = float(gdf.geometry.iloc[0].y)
                _epsg = 32600 + _zone if _lat0 >= 0 else 32700 + _zone
                working_crs = "EPSG:%d" % _epsg
                _t = _PTrans.from_crs(_src, working_crs, always_xy=True)
                projected_xy = _t
        except Exception:
            projected_xy = None

    cols = list(gdf.columns)
    id_col = find_column(cols, tree_id_field, ['tree_id', 'treeid', 'id', 'tag_no', 'tag', 'fid'])
    hc_col = find_column(cols, height_class_field, ['height_class', 'heightclass', 'hight_level', 'ht_class'])
    dbh_col = find_column(cols, dbh_field, ['dbh', 'diameter_cm', 'dbh_mm', 'diameter'])
    hm_col = find_column(cols, height_m_field, ['height_m', 'tree_height_m', 'height', 'total_height'])
    sp_col = find_column(cols, species_field, ['specie', 'tree_species', 'botanical_name'])
    cr_col = find_column(cols, crown_field, ['crown_class', 'crown', 'canopy_class'])
    hl_col = find_column(cols, health_field, ['health_level', 'health', 'condition'])

    # Parse species filter
    allowed_species = set()
    if species_filter:
        if isinstance(species_filter, (list, set, tuple)):
            allowed_species = {str(s).strip().lower() for s in species_filter if str(s).strip()}
        elif isinstance(species_filter, str):
            allowed_species = {s.strip().lower() for s in species_filter.split(',') if s.strip()}

    field_trees = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        xy = np.array([geom.x, geom.y], dtype=float)
        if projected_xy is not None:
            xy = np.array(projected_xy.transform(float(xy[0]), float(xy[1])), dtype=float)

        def _get_val(col):
            if col and col in gdf.columns:
                v = row[col]
                return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v
            return None

        def _get_num(col):
            v = _get_val(col)
            if v is not None:
                try:
                    num = float(v)
                    return num if np.isfinite(num) else None
                except (ValueError, TypeError):
                    return None
            return None

        tid = _get_val(id_col)
        if tid is None:
            tid = idx

        f_hc = int(_get_num(hc_col) or 0)
        f_hm = _get_num(hm_col)
        f_dbh = _get_num(dbh_col)
        f_sp = _get_val(sp_col)

        # Apply Exclusion Filters
        if min_height_class is not None and f_hc < min_height_class:
            continue
        if max_height_class is not None and f_hc > max_height_class:
            continue
        if min_dbh is not None and f_dbh is not None and f_dbh < min_dbh:
            continue
        if max_dbh is not None and f_dbh is not None and f_dbh > max_dbh:
            continue
        if allowed_species and f_sp and str(f_sp).strip().lower() not in allowed_species:
            continue

        derived_hm = f_hm if f_hm is not None else class_to_midpoint_height(f_hc)
        height_range = class_to_height_range(f_hc)

        field_trees.append({
            'field_treeid': tid,
            'xy': xy,
            'height_class': f_hc,
            'height_m': f_hm,
            'derived_height_m': derived_hm,
            'height_range': height_range,
            'dbh_cm': f_dbh,
            'species': f_sp,
            'crown_class': _get_val(cr_col),
            'health': _get_val(hl_col),
            'crs': str(working_crs) if working_crs else None,
            'raw': row.to_dict() if hasattr(row, 'to_dict') else dict(row),
        })
    return field_trees


# ---------------------------------------------------------------------------
# Field-boundary filter (convex hull + buffer), mirrors Step-1 boundary_polygon
# ---------------------------------------------------------------------------
def build_field_boundary(field_trees, buffer_m=5.0):
    """Build a buffered convex-hull boundary from the field survey points.

    Field points are already in projected METRES (read_field_points guarantees
    this via CRS normalization). A convex hull is taken and expanded outward by
    ``buffer_m`` metres (true perpendicular buffer via shapely), producing a
    generous survey-area polygon used to filter out LiDAR detections that lie
    outside the measured plot.
    """
    pts = np.array([
        [ft['xy'][0], ft['xy'][1]] for ft in field_trees if ft.get('xy') is not None
    ])
    crs = field_trees[0].get('crs') if field_trees else None
    out = {'polygon': None, 'inside': None, 'buffer_m': buffer_m, 'crs': crs}
    if len(pts) < 3:
        return out
    from scipy.spatial import ConvexHull as _Hull
    from shapely.geometry import Polygon as _Polygon
    try:
        hull = _Hull(pts)
        ring = pts[hull.vertices]
        poly = _Polygon(ring).buffer(max(buffer_m, 0.0), cap_style=1, join_style=2)
        if poly is None or poly.is_empty or poly.area <= 0:
            return out
        def _inside(x, y):
            try:
                p = _Polygon([[x, y], [x, y], [x, y]]).centroid
                return bool(poly.contains(p))
            except Exception:
                return False
        out['polygon'] = poly
        out['inside'] = _inside
    except Exception:
        pass
    return out


def clip_lidar_to_boundary(lidar_trees, field_trees, buffer_m=5.0):
    """Filter LiDAR detections to those inside the field-point boundary.

    Returns (clipped_lidar, boundary_dict). LiDAR trees whose centroid falls
    outside the buffered field convex hull are dropped so detection/match
    percentages only reflect trees expected within the surveyed plot.
    """
    boundary = build_field_boundary(field_trees, buffer_m=buffer_m)
    inside = boundary['inside']
    if inside is None:
        return lidar_trees, boundary
    clipped = {}
    for tid, lt in lidar_trees.items():
        xy = lt.get('centroid_xy')
        if xy is None:
            continue
        try:
            if inside(float(xy[0]), float(xy[1])):
                clipped[tid] = lt
        except Exception:
            continue
    return clipped, boundary



def compute_similarity_matrices(lidar_trees, field_trees, tolerance_m=2.5,
                                dbh_scale_cm=12.0, height_scale_m=3.0):
    """Compute normalized [0, 1] similarity matrices for shared attributes.

    Returns:
        spatial_sim, dbh_sim, height_sim, dist_matrix, lidar_ids
        (all shapes: N_lidar x M_field)
    """
    lidar_ids = sorted(lidar_trees.keys())
    lidar_xy = np.array([lidar_trees[t]['centroid_xy'] for t in lidar_ids])
    field_xy = np.array([ft['xy'] for ft in field_trees])

    # 1. Spatial distance & similarity
    dist_matrix = cdist(lidar_xy, field_xy, metric='euclidean')
    # Linear decay to 0 at tolerance_m
    spatial_sim = np.clip(1.0 - (dist_matrix / max(tolerance_m, 1e-6)), 0.0, 1.0)

    N, M = len(lidar_ids), len(field_trees)
    dbh_sim = np.ones((N, M), dtype=float) * 0.5  # Neutral default for missing DBH
    height_sim = np.ones((N, M), dtype=float) * 0.5  # Neutral default for missing Height

    for i, tid in enumerate(lidar_ids):
        lt = lidar_trees[tid]
        l_dbh = lt['dbh_cm']
        l_hc = lt['height_class']
        l_hm = lt['height_m']

        for j, ft in enumerate(field_trees):
            f_dbh = ft['dbh_cm']
            f_hc = ft['height_class']
            f_hm = ft['height_m']

            # 2. DBH Similarity (Exponential decay based on error)
            if l_dbh is not None and f_dbh is not None:
                diff_dbh = abs(l_dbh - f_dbh)
                dbh_sim[i, j] = np.exp(-diff_dbh / max(dbh_scale_cm, 1.0))

            # 3. Height / Height Class Similarity
            if l_hm is not None and f_hm is not None:
                # Direct continuous height similarity
                diff_ht = abs(l_hm - f_hm)
                height_sim[i, j] = np.exp(-diff_ht / max(height_scale_m, 1.0))
            elif l_hc > 0 and f_hc > 0:
                # Smooth ordinal class similarity: 1.0 (exact), 0.75 (off by 1), 0.50 (off by 2)...
                class_diff = abs(l_hc - f_hc)
                height_sim[i, j] = max(0.0, 1.0 - (class_diff / 4.0))

    return spatial_sim, dbh_sim, height_sim, dist_matrix, lidar_ids


# ---------------------------------------------------------------------------
# Matching Algorithms
# ---------------------------------------------------------------------------
def match_trees(field_trees, lidar_trees, tolerance_m=2.5,
                weight_spatial=0.50, weight_dbh=0.25, weight_height=0.25,
                dbh_scale_cm=12.0, method='optimal'):
    """Match LiDAR trees to field trees using shared attributes.

    Parameters:
        method: 'optimal' (Hungarian 1-to-1 linear sum assignment) or 'greedy'
    """
    spatial_sim, dbh_sim, height_sim, dist_matrix, lidar_ids = compute_similarity_matrices(
        lidar_trees, field_trees, tolerance_m=tolerance_m, dbh_scale_cm=dbh_scale_cm
    )

    # Normalize weights so they sum to 1.0
    w_sum = weight_spatial + weight_dbh + weight_height
    w_sp = weight_spatial / w_sum
    w_dbh = weight_dbh / w_sum
    w_ht = weight_height / w_sum

    # Combined composite similarity score [0, 1]
    composite_score = (w_sp * spatial_sim) + (w_dbh * dbh_sim) + (w_ht * height_sim)

    # Spatial tolerance mask (strictly gate pairs exceeding tolerance)
    valid_mask = dist_matrix <= tolerance_m
    cost_matrix = 1.0 - composite_score
    cost_matrix[~valid_mask] = 1e6  # Impose prohibitive penalty for out-of-bounds pairs

    matched_pairs = {}  # lidar_idx -> field_idx

    if method == 'optimal':
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        for r, c in zip(row_ind, col_ind):
            if valid_mask[r, c] and cost_matrix[r, c] < 1e5:
                matched_pairs[r] = c
    else:  # Greedy matching
        used_field = set()
        # Sort all pairs by highest composite score first
        order = np.argsort(-composite_score, axis=None)
        for idx in order:
            r, c = np.unravel_index(idx, composite_score.shape)
            if r in matched_pairs or c in used_field:
                continue
            if valid_mask[r, c]:
                matched_pairs[r] = c
                used_field.add(c)

    # Compile assignments
    assignments = []
    for i, tid in enumerate(lidar_ids):
        lt = lidar_trees[tid]
        if i in matched_pairs:
            j = matched_pairs[i]
            ft = field_trees[j]
            assignments.append({
                'lidar_tree_id': tid,
                'field_treeid': ft['field_treeid'],
                'distance_m': float(dist_matrix[i, j]),
                'score': float(composite_score[i, j]),
                'spatial_sim': float(spatial_sim[i, j]),
                'dbh_sim': float(dbh_sim[i, j]),
                'height_sim': float(height_sim[i, j]),
                'lidar_height_m': lt['height_m'],
                'lidar_height_class': lt['height_class'],
                'lidar_height_range': class_to_height_range(lt['height_class']),
                'lidar_dbh_cm': lt['dbh_cm'],
                'lidar_volume_m3': lt['volume_m3'],
                'lidar_n_points': lt['n_points'],
                'lidar_xy': lt['centroid_xy'],
                'field_height_class': ft['height_class'],
                'field_height_m': ft['height_m'],
                'field_derived_height_m': ft['derived_height_m'],
                'field_height_range': ft['height_range'],
                'field_dbh_cm': ft['dbh_cm'],
                'field_species': ft['species'],
                'field_crown_class': ft['crown_class'],
                'field_health': ft['health'],
                'field_xy': ft['xy'],
            })
        else:
            assignments.append({
                'lidar_tree_id': tid,
                'field_treeid': None,
                'distance_m': None,
                'score': None,
                'spatial_sim': None,
                'dbh_sim': None,
                'height_sim': None,
                'lidar_height_m': lt['height_m'],
                'lidar_height_class': lt['height_class'],
                'lidar_height_range': class_to_height_range(lt['height_class']),
                'lidar_dbh_cm': lt['dbh_cm'],
                'lidar_volume_m3': lt['volume_m3'],
                'lidar_n_points': lt['n_points'],
                'lidar_xy': lt['centroid_xy'],
                'field_height_class': None,
                'field_height_m': None,
                'field_derived_height_m': None,
                'field_height_range': None,
                'field_dbh_cm': None,
                'field_species': None,
                'field_crown_class': None,
                'field_health': None,
                'field_xy': None,
            })

    # Also append unmatched field trees
    matched_field_ids = {a['field_treeid'] for a in assignments if a['field_treeid'] is not None}
    for ft in field_trees:
        if ft['field_treeid'] not in matched_field_ids:
            assignments.append({
                'lidar_tree_id': None,
                'field_treeid': ft['field_treeid'],
                'distance_m': None,
                'score': None,
                'spatial_sim': None,
                'dbh_sim': None,
                'height_sim': None,
                'lidar_height_m': None,
                'lidar_height_class': None,
                'lidar_height_range': None,
                'lidar_dbh_cm': None,
                'lidar_volume_m3': None,
                'lidar_n_points': None,
                'lidar_xy': None,
                'field_height_class': ft['height_class'],
                'field_height_m': ft['height_m'],
                'field_derived_height_m': ft['derived_height_m'],
                'field_height_range': ft['height_range'],
                'field_dbh_cm': ft['dbh_cm'],
                'field_species': ft['species'],
                'field_crown_class': ft['crown_class'],
                'field_health': ft['health'],
                'field_xy': ft['xy'],
            })

    return assignments


# ---------------------------------------------------------------------------
# Outputs & Reporting
# ---------------------------------------------------------------------------
def write_outputs(assignments, lidar_trees, field_trees, out_dir,
                  export_geojson=True, source_crs=None):
    """Write assignment tables, comprehensive statistical report, and spatial vectors."""
    os.makedirs(out_dir, exist_ok=True)

    # Detect CRS from field trees if not passed
    if not source_crs and field_trees and field_trees[0].get('crs'):
        source_crs = field_trees[0]['crs']

    # 1. Assignment CSV
    csv_path = os.path.join(out_dir, 'field_assignment.csv')
    fieldnames = [
        'lidar_tree_id', 'field_treeid', 'distance_m', 'match_score',
        'lidar_dbh_cm', 'field_dbh_cm', 'dbh_error_cm',
        'lidar_height_m', 'field_height_m', 'field_derived_height_m', 'field_height_range',
        'lidar_height_class', 'field_height_class',
        'field_species', 'field_crown_class', 'field_health',
        'lidar_volume_m3', 'lidar_n_points',
        'lidar_x', 'lidar_y', 'field_x', 'field_y'
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in assignments:
            l_dbh = a['lidar_dbh_cm']
            f_dbh = a['field_dbh_cm']
            dbh_err = (l_dbh - f_dbh) if (l_dbh is not None and f_dbh is not None) else None
            
            l_xy = a['lidar_xy']
            f_xy = a['field_xy']

            writer.writerow({
                'lidar_tree_id': a['lidar_tree_id'] if a['lidar_tree_id'] is not None else '',
                'field_treeid': a['field_treeid'] if a['field_treeid'] is not None else '',
                'distance_m': round(a['distance_m'], 3) if a['distance_m'] is not None else '',
                'match_score': round(a['score'], 4) if a['score'] is not None else '',
                'lidar_dbh_cm': round(l_dbh, 2) if l_dbh is not None else '',
                'field_dbh_cm': round(f_dbh, 2) if f_dbh is not None else '',
                'dbh_error_cm': round(dbh_err, 2) if dbh_err is not None else '',
                'lidar_height_m': round(a['lidar_height_m'], 2) if a['lidar_height_m'] is not None else '',
                'field_height_m': round(a['field_height_m'], 2) if a['field_height_m'] is not None else '',
                'field_derived_height_m': round(a['field_derived_height_m'], 2) if a['field_derived_height_m'] is not None else '',
                'field_height_range': a.get('field_height_range', '') or '',
                'lidar_height_class': a['lidar_height_class'] if a['lidar_height_class'] is not None else '',
                'field_height_class': a['field_height_class'] if a['field_height_class'] is not None else '',
                'field_species': a['field_species'] or '',
                'field_crown_class': a['field_crown_class'] or '',
                'field_health': a['field_health'] or '',
                'lidar_volume_m3': round(a['lidar_volume_m3'], 4) if a['lidar_volume_m3'] is not None else '',
                'lidar_n_points': a['lidar_n_points'] if a['lidar_n_points'] is not None else '',
                'lidar_x': round(l_xy[0], 3) if l_xy is not None else '',
                'lidar_y': round(l_xy[1], 3) if l_xy is not None else '',
                'field_x': round(f_xy[0], 3) if f_xy is not None else '',
                'field_y': round(f_xy[1], 3) if f_xy is not None else '',
            })

    # 2. Comprehensive Match Report
    matched = [a for a in assignments if a['lidar_tree_id'] is not None and a['field_treeid'] is not None]
    unmatched_lidar = [a for a in assignments if a['lidar_tree_id'] is not None and a['field_treeid'] is None]
    matched_field_ids = {a['field_treeid'] for a in matched}
    unmatched_field = [ft for ft in field_trees if ft['field_treeid'] not in matched_field_ids]

    report_path = os.path.join(out_dir, 'match_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 75 + "\n")
        f.write("             LIDAR TO FIELD TREE ASSIGNMENT REPORT\n")
        f.write("=" * 75 + "\n\n")

        f.write("1. INVENTORY SUMMARY\n")
        f.write("-" * 35 + "\n")
        f.write(f"Total Field Trees Surveyed:  {len(field_trees)}\n")
        f.write(f"Total LiDAR Trees Extracted: {len(lidar_trees)}\n")
        f.write(f"Successfully Matched:        {len(matched)}\n")
        f.write(f"LiDAR Match Rate:            {len(matched)/max(len(lidar_trees), 1)*100:.1f}%\n")
        f.write(f"Field Match Rate:            {len(matched)/max(len(field_trees), 1)*100:.1f}%\n")
        f.write(f"Unmatched LiDAR Trees:       {len(unmatched_lidar)}\n")
        f.write(f"Unmatched Field Trees:       {len(unmatched_field)}\n\n")

        if matched:
            dists = [a['distance_m'] for a in matched if a['distance_m'] is not None]
            scores = [a['score'] for a in matched if a['score'] is not None]
            dbh_pairs = [(a['lidar_dbh_cm'], a['field_dbh_cm']) for a in matched
                         if a['lidar_dbh_cm'] is not None and a['field_dbh_cm'] is not None]
            
            f.write("2. MATCH QUALITY METRICS\n")
            f.write("-" * 35 + "\n")
            if dists:
                f.write(f"Mean Spatial Distance Error:    {np.mean(dists):.3f} m (Std: {np.std(dists):.3f} m)\n")
                f.write(f"Median Spatial Distance Error:  {np.median(dists):.3f} m\n")
            if scores:
                f.write(f"Mean Match Composite Score:     {np.mean(scores):.4f}\n")

            if dbh_pairs:
                l_dbhs = np.array([p[0] for p in dbh_pairs])
                f_dbhs = np.array([p[1] for p in dbh_pairs])
                dbh_diffs = l_dbhs - f_dbhs
                f.write(f"DBH Evaluation Count:           {len(dbh_pairs)} pairs\n")
                f.write(f"Mean DBH Error (LiDAR - Field): {np.mean(dbh_diffs):+.2f} cm\n")
                f.write(f"Mean Absolute DBH Error (MAE):  {np.mean(np.abs(dbh_diffs)):.2f} cm\n")
                f.write(f"Root Mean Square Error (RMSE):  {np.sqrt(np.mean(dbh_diffs**2)):.2f} cm\n")
                if len(dbh_pairs) > 2 and np.std(l_dbhs) > 1e-4 and np.std(f_dbhs) > 1e-4:
                    corr = np.corrcoef(l_dbhs, f_dbhs)[0, 1]
                    f.write(f"DBH Pearson Correlation (r):    {corr:.4f}\n")

            # Height Class Agreement Matrix
            f.write("\n3. HEIGHT CLASS AGREEMENT MATRIX\n")
            f.write("-" * 35 + "\n")
            f.write("Rows: Field Height Class, Cols: LiDAR Height Class\n")
            conf = defaultdict(lambda: defaultdict(int))
            for a in matched:
                conf[a['field_height_class']][a['lidar_height_class']] += 1

            all_classes = [1, 2, 3, 4, 5]
            header = "Field\\LiDAR\t" + "\t".join(f"C{c}" for c in all_classes)
            f.write(header + "\n")
            for fc in all_classes:
                row_str = f"Class {fc}\t" + "\t".join(str(conf[fc][lc]) for lc in all_classes)
                f.write(row_str + "\n")

            # Section 4: Detailed Matched Trees Breakdown
            f.write(f"\n4. DETAILED MATCHED TREES BREAKDOWN ({len(matched)} trees)\n")
            f.write("-" * 115 + "\n")
            f.write(f"{'LiDAR ID':<9s} | {'Field ID':<9s} | {'Dist(m)':<7s} | {'Score':<7s} | {'LiDAR DBH':<10s} | {'Field DBH':<10s} | {'DBH Diff':<9s} | {'LiDAR Ht':<9s} | {'LiDAR Cls':<10s} | {'Field Cls':<10s} | {'Species':<8s}\n")
            f.write("-" * 115 + "\n")
            for a in matched:
                l_dbh = f"{a['lidar_dbh_cm']:.1f} cm" if a['lidar_dbh_cm'] is not None else "N/A"
                f_dbh = f"{a['field_dbh_cm']:.1f} cm" if a['field_dbh_cm'] is not None else "N/A"
                diff = f"{(a['lidar_dbh_cm'] - a['field_dbh_cm']):+.1f} cm" if (a['lidar_dbh_cm'] is not None and a['field_dbh_cm'] is not None) else "N/A"
                l_ht = f"{a['lidar_height_m']:.2f}m" if a['lidar_height_m'] is not None else "N/A"
                l_cls = f"Class {a['lidar_height_class']}" if a['lidar_height_class'] else "N/A"
                f_cls = f"Class {a['field_height_class']}" if a['field_height_class'] else "N/A"
                sp = str(a['field_species'] or '-')
                dist = f"{a['distance_m']:.2f}m" if a['distance_m'] is not None else "N/A"
                score = f"{a['score']:.3f}" if a['score'] is not None else "N/A"
                f.write(f"{a['lidar_tree_id']:<9d} | {str(a['field_treeid']):<9s} | {dist:<7s} | {score:<7s} | {l_dbh:<10s} | {f_dbh:<10s} | {diff:<9s} | {l_ht:<9s} | {l_cls:<10s} | {f_cls:<10s} | {sp:<8s}\n")

        f.write(f"\n5. UNMATCHED LIDAR TREES ({len(unmatched_lidar)} trees)\n")
        f.write("-" * 35 + "\n")
        if unmatched_lidar:
            for a in unmatched_lidar:
                f.write(f"  LiDAR Tree ID {a['lidar_tree_id']:4d} | Height: {a['lidar_height_m'] or 0:.1f}m "
                        f"(Class {a['lidar_height_class']}) | DBH: {a['lidar_dbh_cm'] or 0:.1f}cm\n")
        else:
            f.write("  None (All LiDAR trees successfully matched!)\n")

        f.write(f"\n6. UNMATCHED FIELD TREES ({len(unmatched_field)} trees)\n")
        f.write("-" * 35 + "\n")
        if unmatched_field:
            for ft in unmatched_field:
                sp_str = f"Species: {ft['species']}" if ft['species'] else "Species: N/A"
                dbh_str = f"DBH: {ft['dbh_cm']:.1f}cm" if ft['dbh_cm'] is not None else "DBH: N/A"
                hc_str = f"Class {ft['height_class']} ({ft['height_range']})" if ft['height_class'] else "Class: N/A"
                xy_str = f"XY: ({ft['xy'][0]:.2f}, {ft['xy'][1]:.2f})" if ft['xy'] is not None else ""
                f.write(f"  Field Tree ID {str(ft['field_treeid']):>4s} | {hc_str:<18s} | {dbh_str:<13s} | {sp_str:<16s} | {xy_str}\n")
        else:
            f.write("  None (All field trees successfully matched!)\n")

    # 3. GeoJSON Spatial Export (WGS84 & Native CRS)
    if export_geojson:
        try:
            import json
            from pyproj import Transformer
            
            transformer = None
            if source_crs:
                try:
                    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
                except Exception as e:
                    print(f"  Note: CRS reprojection to WGS84 unavailable: {e}")

            features = []
            for a in matched:
                l_x, l_y = a['lidar_xy']
                f_x, f_y = a['field_xy']

                # Reproject to WGS84 [lon, lat] if possible for Leaflet
                if transformer:
                    try:
                        l_lon, l_lat = transformer.transform(l_x, l_y)
                        f_lon, f_lat = transformer.transform(f_x, f_y)
                        coords = [[float(l_lon), float(l_lat)], [float(f_lon), float(f_lat)]]
                    except Exception:
                        coords = [[float(l_x), float(l_y)], [float(f_x), float(f_y)]]
                else:
                    coords = [[float(l_x), float(l_y)], [float(f_x), float(f_y)]]

                geom = {
                    "type": "LineString",
                    "coordinates": coords
                }
                props = {
                    "lidar_id": a['lidar_tree_id'],
                    "field_id": str(a['field_treeid']),
                    "distance_m": round(a['distance_m'], 3),
                    "score": round(a['score'], 3),
                    "lidar_dbh": a['lidar_dbh_cm'],
                    "field_dbh": a['field_dbh_cm'],
                    "lidar_class": a['lidar_height_class'],
                    "field_class": a['field_height_class'],
                    "species": a['field_species'] or '',
                }
                features.append({"type": "Feature", "geometry": geom, "properties": props})

            geojson = {"type": "FeatureCollection", "features": features}
            geojson_path = os.path.join(out_dir, 'match_vectors.geojson')
            with open(geojson_path, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, indent=2)
            print(f"  Wrote GIS vectors: {geojson_path}")
        except Exception as e:
            print(f"  Note: Spatial vector export skipped ({e})")

    print(f"  Wrote CSV: {csv_path}")
    print(f"  Wrote Report: {report_path}")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Optimal Field Assignment for LiDAR trees based on shared attributes'
    )
    parser.add_argument('--gdb', required=True, help='Path to .gdb folder or vector dataset')
    parser.add_argument('--layer', default='TreePosition_LiDARGeom_Transect1stemCenter',
                        help='Field point layer name')
    parser.add_argument('--metrics', required=True,
                        help='Path to enhancer trunk_metrics CSV (LiDAR side)')
    parser.add_argument('--out', default='semantic_assignment_out', help='Output directory')
    parser.add_argument('--tolerance', type=float, default=2.5,
                        help='Max XY search distance in metres (default: 2.5m)')
    parser.add_argument('--weight-spatial', type=float, default=0.50,
                        help='Weight for spatial proximity (default: 0.50)')
    parser.add_argument('--weight-dbh', type=float, default=0.25,
                        help='Weight for DBH similarity (default: 0.25)')
    parser.add_argument('--weight-height', type=float, default=0.25,
                        help='Weight for Height / Height Class similarity (default: 0.25)')
    parser.add_argument('--dbh-scale', type=float, default=12.0,
                        help='DBH difference scaling constant in cm (default: 12.0)')
    parser.add_argument('--method', choices=['optimal', 'greedy'], default='optimal',
                        help='Matching solver: global "optimal" (Hungarian) or "greedy" (default: optimal)')
    parser.add_argument('--height-class-field', default='hightlevel',
                        help='Field survey column for height class')
    parser.add_argument('--dbh-field', default='dbh_cm',
                        help='Field survey column for DBH (cm)')

    args = parser.parse_args()
    t0 = time.time()

    print("\n--- Starting LiDAR to Field Tree Assignment ---")
    print(f"1. Reading field data from: {args.gdb} (Layer: {args.layer})...")
    field_trees = read_field_points(
        args.gdb, args.layer,
        height_class_field=args.height_class_field,
        dbh_field=args.dbh_field
    )
    print(f"   Found {len(field_trees)} field trees.")

    print(f"2. Reading LiDAR metrics from: {args.metrics}...")
    lidar_trees = read_lidar_metrics(args.metrics)
    print(f"   Found {len(lidar_trees)} LiDAR trees.")

    print(f"3. Matching trees using method='{args.method}' (Spatial Tolerance: {args.tolerance}m)...")
    print(f"   Weights -> Spatial: {args.weight_spatial:.2f}, DBH: {args.weight_dbh:.2f}, Height: {args.weight_height:.2f}")
    assignments = match_trees(
        field_trees=field_trees,
        lidar_trees=lidar_trees,
        tolerance_m=args.tolerance,
        weight_spatial=args.weight_spatial,
        weight_dbh=args.weight_dbh,
        weight_height=args.weight_height,
        dbh_scale_cm=args.dbh_scale,
        method=args.method,
    )

    print("4. Generating outputs...")
    write_outputs(assignments, lidar_trees, field_trees, args.out)

    print(f"--- Completed in {time.time() - t0:.2f}s ---\n")


if __name__ == '__main__':
    main()
