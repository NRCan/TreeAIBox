#!/usr/bin/env python3
"""
Batch UAV Tree Segmentation for Clipped Plots using TreeAIBox (TreeisoNet)
Processes all .las files in D:\\LLR DATA\\Clipped_Plots
Outputs:
  - Segmented LAS with stemcls, stemoff, and itc scalar fields
  - Tree location coordinates CSV (X, Y, Z)
  - Individual Tree Crown statistics CSV (height, crown area, coordinates)
  - Combined multi-plot summary CSV
"""

import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import laspy
import torch
from scipy.spatial import ConvexHull

# Add workspace root to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.filter.componentFilter import filterPoints
from modules.treeisonet.treeLoc import treeLoc
from modules.treeisonet.stemCluster import shortestpath3D as stemClusterSP
from modules.treeisonet.crownCluster import init_cutpursuit, shortestpath3D as crownClusterSP
from modules.treeisonet.treeStat import treeStat


def process_plot(las_path, output_dir, configs):
    plot_name = os.path.splitext(os.path.basename(las_path))[0]
    print(f"\n{'='*70}")
    print(f" PROCESSING: {plot_name} ({las_path})")
    print(f"{'='*70}")
    t0 = time.time()

    # 1. Read LAS
    las = laspy.read(las_path)
    n_points = len(las.points)
    print(f"[*] Read {n_points:,} points from {plot_name}.las")
    pcd = np.transpose([las.x, las.y, las.z])
    pcd_min = np.min(pcd[:, :3], axis=0)
    pcd_rel = pcd - pcd_min

    # 2. Step 1: Stem Classification (StemCls)
    print(f"[*] Step 1/4: Running Stem Classification (StemCls)...")
    t_step = time.time()
    stemcls_raw = filterPoints(
        configs['stemcls_config'],
        pcd_rel,
        configs['stemcls_model'],
        if_bottom_only=False,
        use_cuda=configs['use_cuda']
    )
    stem_count = int(np.sum(stemcls_raw > 1))
    print(f"    -> Identified {stem_count:,} stem points ({100 * stem_count / n_points:.1f}%) in {time.time() - t_step:.1f}s")

    if stem_count < 20:
        print(f"[!] Warning: Very few stem points detected ({stem_count}). Proceeding with caution.")

    pcd_stem = pcd_rel[stemcls_raw > 1]

    # 3. Step 2: Tree Location Detection (TreeLoc)
    print(f"[*] Step 2/4: Detecting Tree Base Locations (TreeLoc)...")
    t_step = time.time()
    treelocs_rel = treeLoc(
        configs['treeloc_config'],
        pcd_stem,
        configs['treeloc_model'],
        use_cuda=configs['use_cuda'],
        if_stem=True,
        cutoff_thresh=configs['cutoff_thresh']
    )
    treelocs_abs = treelocs_rel + pcd_min
    n_trees = len(treelocs_abs)
    print(f"    -> Detected {n_trees} tree stem bases in {time.time() - t_step:.1f}s")

    if n_trees == 0:
        print(f"[!] Warning: No trees detected in {plot_name}. Skipping subsequent clustering.")
        return None

    # Save tree locations to CSV
    treeloc_file = os.path.join(output_dir, f"{plot_name}_treelocs.csv")
    df_locs = pd.DataFrame(treelocs_abs, columns=['x', 'y', 'z'])
    df_locs.insert(0, 'tree_id', np.arange(1, n_trees + 1))
    df_locs.to_csv(treeloc_file, index=False)
    print(f"    -> Saved tree locations to: {treeloc_file}")

    # 4. Step 3: Stem Instance Clustering (StemClusterSP)
    print(f"[*] Step 3/4: Clustering Stem Points (StemClusterSP)...")
    t_step = time.time()
    stemoff = stemClusterSP(
        pcd_rel,
        stemcls_raw,
        treelocs_rel,
        min_res=configs['stem_res'],
        max_isolated_distance=configs['stem_max_gap']
    )
    if stemoff is None:
        stemoff = np.zeros(n_points, dtype=np.int32)
    else:
        stemoff = stemoff.astype(np.int32)
    n_stem_trees = len(np.unique(stemoff[stemoff > 0]))
    print(f"    -> Clustered stems into {n_stem_trees} instances in {time.time() - t_step:.1f}s")

    # 5. Step 4: Crown / Canopy Segmentation (CrownClusterSP)
    print(f"[*] Step 4/4: Segmenting Full 3D Tree Crowns (CrownClusterSP)...")
    t_step = time.time()
    init_segs, n_segs = init_cutpursuit(
        pcd_rel,
        min_res=configs['crown_res'],
        K=configs['crown_K'],
        reg_strength=configs['crown_reg']
    )
    itc = crownClusterSP(
        pcd_rel,
        stemoff,
        init_segs,
        min_res=configs['crown_res'],
        max_isolated_distance=configs['crown_max_gap']
    )
    itc = itc.astype(np.int32)
    unique_itc = np.unique(itc[itc > 0])
    n_itc_trees = len(unique_itc)
    print(f"    -> Segmented {n_itc_trees} tree crowns ({np.sum(itc > 0):,} canopy points) in {time.time() - t_step:.1f}s")

    # 6. Save Segmented LAS
    out_las_path = os.path.join(output_dir, f"{plot_name}_segmented.las")
    print(f"[*] Writing segmented LAS file: {out_las_path}...")
    
    # Add extra dimensions
    try:
        las.add_extra_dim(laspy.ExtraBytesParams(name="stemcls", type="int32"))
    except Exception:
        pass
    las.stemcls = stemcls_raw.astype(np.int32)

    try:
        las.add_extra_dim(laspy.ExtraBytesParams(name="stemoff", type="int32"))
    except Exception:
        pass
    las.stemoff = stemoff

    try:
        las.add_extra_dim(laspy.ExtraBytesParams(name="itc", type="int32"))
    except Exception:
        pass
    las.itc = itc

    las.write(out_las_path)
    print(f"    -> Saved segmented LAS ({os.path.getsize(out_las_path) / 1024**2:.2f} MB)")

    # 7. Extract Individual Tree Statistics (TreeStat)
    print(f"[*] Computing individual tree metrics & crown geometry...")
    treestat_file = os.path.join(output_dir, f"{plot_name}_treestat.csv")
    treeStat(
        pcd_rel,
        itc,
        pcd_min=pcd_min,
        outpath=treestat_file,
        dtm_resolution=configs['dtm_resolution']
    )

    # Enhance treestat with diameter and filter out id=0
    df_stat = pd.read_csv(treestat_file, sep=r'\s+')
    # Remove itc_id == 0 and low-height false trees/stumps (< min_tree_height)
    min_h = configs.get('min_tree_height', 2.5)
    df_trees = df_stat[(df_stat['itc_id'] > 0) & (df_stat['height'] >= min_h)].copy()
    if len(df_trees) > 0:
        df_trees['crown_diameter_m'] = 2.0 * np.sqrt(df_trees['crown_area'] / np.pi)
        df_trees['crown_diameter_m'] = df_trees['crown_diameter_m'].round(2)
        df_trees['crown_area'] = df_trees['crown_area'].round(2)
        df_trees['height'] = df_trees['height'].round(2)
        df_trees['x'] = df_trees['x'].round(3)
        df_trees['y'] = df_trees['y'].round(3)
        df_trees['z'] = df_trees['z'].round(3)
        df_trees.to_csv(treestat_file, index=False)
        print(f"    -> Exported metrics for {len(df_trees)} trees to: {treestat_file}")
    
    elapsed = time.time() - t0
    print(f"[✓] {plot_name} complete in {elapsed:.1f}s\n")

    # Memory cleanup
    if configs['use_cuda']:
        torch.cuda.empty_cache()

    summary_entry = {
        'plot_name': plot_name,
        'total_points': n_points,
        'stem_points': stem_count,
        'detected_trees': len(df_trees),
        'mean_height_m': round(df_trees['height'].mean(), 2) if len(df_trees) > 0 else 0,
        'max_height_m': round(df_trees['height'].max(), 2) if len(df_trees) > 0 else 0,
        'total_crown_area_m2': round(df_trees['crown_area'].sum(), 2) if len(df_trees) > 0 else 0,
        'mean_crown_diameter_m': round(df_trees['crown_diameter_m'].mean(), 2) if len(df_trees) > 0 else 0,
        'processing_time_s': round(elapsed, 1)
    }
    return summary_entry


def main():
    plots_dir = r"D:\LLR DATA\Clipped_Plots"
    output_dir = os.path.join(plots_dir, "Segmented_Results")
    os.makedirs(output_dir, exist_ok=True)

    las_files = sorted(glob.glob(os.path.join(plots_dir, "plot_*.las")))
    print(f"Found {len(las_files)} plot files in {plots_dir}")

    configs = {
        'stemcls_config': os.path.join(PROJECT_ROOT, 'modules', 'treeisonet', 'treeisonet_uav_mixedwood_stemcls_esegformer3D_128_8cm(GPU3GB).json'),
        'stemcls_model': os.path.join(PROJECT_ROOT, 'models', 'treeisonet_uav_mixedwood_stemcls_esegformer3D_128_8cm(GPU3GB).pth'),
        'treeloc_config': os.path.join(PROJECT_ROOT, 'modules', 'treeisonet', 'treeisonet_uav_mixedwood_treeloc_esegformer3D_128_10cm(GPU3GB).json'),
        'treeloc_model': os.path.join(PROJECT_ROOT, 'models', 'treeisonet_uav_mixedwood_treeloc_esegformer3D_128_10cm(GPU3GB).pth'),
        'use_cuda': torch.cuda.is_available(),
        'cutoff_thresh': 0.20,      # Tuned for dense mixedwood UAV LiDAR
        'stem_res': 0.06,
        'stem_max_gap': 0.28,
        'crown_res': 0.15,
        'crown_K': 5,
        'crown_reg': 0.50,          # Reduced from 1.0 to prevent fusing adjacent crowns
        'crown_max_gap': 0.28,      # Tightened from 0.40 to prevent jumping across tree gaps
        'min_tree_height': 2.5,     # Filter out ground debris, understory shrubs, and stumps
        'min_tree_points': 120,
        'dtm_resolution': 1.0
    }

    print("CUDA Available:", configs['use_cuda'])
    if configs['use_cuda']:
        print("GPU Device:", torch.cuda.get_device_name(0))

    summaries = []
    total_start = time.time()

    for idx, las_path in enumerate(las_files):
        print(f"\n>>> [{idx+1}/{len(las_files)}] Processing {os.path.basename(las_path)}...")
        try:
            res = process_plot(las_path, output_dir, configs)
            if res:
                summaries.append(res)
        except Exception as e:
            print(f"[!] ERROR processing {las_path}: {e}")
            import traceback
            traceback.print_exc()

    if summaries:
        df_summary = pd.DataFrame(summaries)
        summary_path = os.path.join(output_dir, "all_plots_inventory_summary.csv")
        df_summary.to_csv(summary_path, index=False)
        print(f"\n{'='*70}")
        print(f" ALL PLOTS COMPLETED IN {time.time() - total_start:.1f}s")
        print(f" Master Summary saved to: {summary_path}")
        print(f"{'='*70}")
        print(df_summary.to_string(index=False))


if __name__ == "__main__":
    main()
