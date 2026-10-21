#!/usr/bin/env python3
"""
Automated Post-Processing Refiner for Clipped UAV Plots
Solves:
1. False tree removal (stumps, low understory shrubs < 2.5m, low point counts < 120)
2. Multi-stem cluster disentanglement (splits overlapping trees into distinct individual ITCs)
3. Crown re-partitioning via 3D nearest-stem trajectory Voronoi allocation
4. Recomputes clean tree statistics, tree locations, and multi-plot summary
"""

import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import laspy
from scipy.spatial import ConvexHull, KDTree
from sklearn.cluster import DBSCAN


def compute_crown_area_and_diam(xy_points):
    """Compute 2D convex hull crown area and equivalent diameter."""
    if len(xy_points) < 3:
        return 0.0, 0.0
    try:
        hull = ConvexHull(xy_points)
        area = float(hull.volume)  # In 2D, hull.volume is the 2D area
        diam = 2.0 * np.sqrt(area / np.pi)
        return round(area, 2), round(diam, 2)
    except Exception:
        # Fallback to bounding box area if points are collinear
        dx = np.ptp(xy_points[:, 0])
        dy = np.ptp(xy_points[:, 1])
        area = float(dx * dy * 0.75)
        diam = round(2.0 * np.sqrt(max(0.01, area) / np.pi), 2)
        return round(area, 2), diam


def extract_stem_trajectories(stem_points, stem_cluster_labels):
    """
    Given stem points and cluster labels, compute 3D trajectory centroids for each cluster.
    Returns: dict mapping cluster_idx -> array of (x, y, z) centroids along the height.
    """
    unique_clusters = sorted(set(stem_cluster_labels) - {-1})
    trajectories = {}
    
    for c_id in unique_clusters:
        pts = stem_points[stem_cluster_labels == c_id]
        if len(pts) == 0:
            continue
            
        z_min, z_max = np.min(pts[:, 2]), np.max(pts[:, 2])
        slice_thickness = 0.5  # 50cm vertical slices
        z_bins = np.arange(z_min, z_max + slice_thickness, slice_thickness)
        
        centroids = []
        for i in range(len(z_bins) - 1):
            z_low = z_bins[i]
            z_high = z_bins[i + 1]
            bin_mask = (pts[:, 2] >= z_low) & (pts[:, 2] < z_high)
            if np.sum(bin_mask) >= 3:
                cx = np.median(pts[bin_mask, 0])
                cy = np.median(pts[bin_mask, 1])
                cz = (z_low + z_high) / 2.0
                centroids.append([cx, cy, cz])
                
        if len(centroids) == 0:
            centroids.append([np.median(pts[:, 0]), np.median(pts[:, 1]), np.median(pts[:, 2])])
            
        trajectories[c_id] = np.array(centroids)
        
    return trajectories


def refine_plot(las_path, output_dir, min_height=2.5, min_pts=120, stem_eps=0.85, stem_min_samples=15):
    """
    Refine a single segmented LAS plot:
    - Filters false trees / low understory (< min_height or < min_pts)
    - Disentangles multi-stem trees into separate ITC IDs
    - Saves refined LAS, treestat CSV, and treelocs CSV
    """
    plot_name = os.path.splitext(os.path.basename(las_path))[0].replace('_segmented', '')
    print(f"\n{'='*70}")
    print(f" REFINING: {plot_name} ({las_path})")
    print(f"{'='*70}")
    
    las = laspy.read(las_path)
    n_points = len(las.points)
    coords = np.column_stack([las.x, las.y, las.z])
    
    has_stemcls = 'stemcls' in las.point_format.dimension_names
    has_itc = 'itc' in las.point_format.dimension_names
    
    if not has_itc:
        print(f"[!] Error: No 'itc' dimension found in {las_path}. Skipping.")
        return None
        
    itc_orig = np.array(las.itc, dtype=np.int32)
    stemcls = np.array(las.stemcls, dtype=np.int32) if has_stemcls else np.zeros(n_points, dtype=np.int32)
    stem_mask_all = (stemcls > 1)
    
    unique_itc = np.unique(itc_orig[itc_orig > 0])
    print(f"[*] Original state: {len(unique_itc)} ITC clusters ({np.sum(itc_orig > 0):,} canopy points)")
    
    itc_refined = np.zeros(n_points, dtype=np.int32)
    current_new_id = 1
    
    removed_false_trees = 0
    split_clusters = 0
    total_new_trees_from_splits = 0
    
    for itc_id in unique_itc:
        tree_idx = np.where(itc_orig == itc_id)[0]
        tree_coords = coords[tree_idx]
        pts_count = len(tree_idx)
        z_span = np.ptp(tree_coords[:, 2])
        
        # 1. Filter out false trees (stumps, ground debris, small understory brush)
        if z_span < min_height or pts_count < min_pts:
            # Mark as unassigned / ground noise (ITC = 0)
            itc_refined[tree_idx] = 0
            removed_false_trees += 1
            continue
            
        # 2. Check for multiple distinct stem cores within this cluster
        tree_stem_idx = np.where((itc_orig == itc_id) & stem_mask_all)[0]
        split_performed = False
        
        if len(tree_stem_idx) >= 20:
            tree_stem_coords = coords[tree_stem_idx]
            # Cluster in horizontal space
            db = DBSCAN(eps=stem_eps, min_samples=stem_min_samples).fit(tree_stem_coords[:, :2])
            stem_labels = db.labels_
            valid_clusters = sorted(set(stem_labels) - {-1})
            
            if len(valid_clusters) > 1:
                # We have multiple distinct stems! Disentangle them
                trajectories = extract_stem_trajectories(tree_stem_coords, stem_labels)
                
                # Check that at least 2 trajectories were formed with meaningful point counts
                if len(trajectories) > 1:
                    # Assign each point in the tree to the closest stem trajectory in 3D
                    # Build a combined KD-Tree of all trajectory points with cluster ownership
                    all_traj_points = []
                    all_traj_clusters = []
                    for c_id, traj in trajectories.items():
                        for pt in traj:
                            all_traj_points.append(pt)
                            all_traj_clusters.append(c_id)
                            
                    all_traj_points = np.array(all_traj_points)
                    all_traj_clusters = np.array(all_traj_clusters)
                    
                    traj_kdtree = KDTree(all_traj_points)
                    
                    # Query closest trajectory point for every point in the tree cluster
                    _, nearest_traj_idx = traj_kdtree.query(tree_coords)
                    assigned_stem_clusters = all_traj_clusters[nearest_traj_idx]
                    
                    # Allocate new unique ITC IDs for each sub-tree
                    valid_subtrees = 0
                    for c_id in sorted(set(assigned_stem_clusters)):
                        sub_mask = (assigned_stem_clusters == c_id)
                        sub_coords = tree_coords[sub_mask]
                        if len(sub_coords) >= min_pts and np.ptp(sub_coords[:, 2]) >= min_height:
                            sub_global_idx = tree_idx[sub_mask]
                            itc_refined[sub_global_idx] = current_new_id
                            current_new_id += 1
                            valid_subtrees += 1
                        else:
                            # Too small sub-component, set to 0
                            sub_global_idx = tree_idx[sub_mask]
                            itc_refined[sub_global_idx] = 0
                            
                    if valid_subtrees > 1:
                        split_clusters += 1
                        total_new_trees_from_splits += (valid_subtrees - 1)
                        split_performed = True
                        
        if not split_performed:
            # Single coherent tree, keep intact with new sequential ID
            itc_refined[tree_idx] = current_new_id
            current_new_id += 1

    # Update LAS data with refined ITC
    las.itc = itc_refined
    
    # Save refined LAS
    out_las_path = os.path.join(output_dir, f"{plot_name}_refined.las")
    las.write(out_las_path)
    print(f"[*] Saved refined LAS: {out_las_path}")
    print(f"    - Removed false trees/stumps: {removed_false_trees}")
    print(f"    - Overlapped clusters split: {split_clusters} (produced {total_new_trees_from_splits} extra trees)")
    
    # Extract updated tree statistics
    final_itc_ids = np.unique(itc_refined[itc_refined > 0])
    n_final_trees = len(final_itc_ids)
    print(f"    -> Final clean tree count: {n_final_trees} trees")
    
    treestats = []
    treelocs = []
    
    for new_id in final_itc_ids:
        t_mask = (itc_refined == new_id)
        t_coords = coords[t_mask]
        
        z_min = float(np.min(t_coords[:, 2]))
        z_max = float(np.max(t_coords[:, 2]))
        tree_height = round(z_max - z_min, 2)
        
        # Base location: median of lowest 10% of points
        lowest_thresh = z_min + max(0.5, 0.1 * tree_height)
        low_pts = t_coords[t_coords[:, 2] <= lowest_thresh]
        if len(low_pts) > 0:
            base_x = round(float(np.median(low_pts[:, 0])), 3)
            base_y = round(float(np.median(low_pts[:, 1])), 3)
            base_z = round(z_min, 3)
        else:
            base_x = round(float(np.median(t_coords[:, 0])), 3)
            base_y = round(float(np.median(t_coords[:, 1])), 3)
            base_z = round(z_min, 3)
            
        # Top location: highest point
        top_idx = np.argmax(t_coords[:, 2])
        top_x = round(float(t_coords[top_idx, 0]), 3)
        top_y = round(float(t_coords[top_idx, 1]), 3)
        top_z = round(z_max, 3)
        
        # Crown geometry
        crown_area, crown_diam = compute_crown_area_and_diam(t_coords[:, :2])
        
        treestats.append({
            'itc_id': int(new_id),
            'x': base_x,
            'y': base_y,
            'z': base_z,
            'top_x': top_x,
            'top_y': top_y,
            'top_z': top_z,
            'height': tree_height,
            'crown_area': crown_area,
            'crown_diameter_m': crown_diam,
            'point_count': int(np.sum(t_mask))
        })
        
        treelocs.append({
            'tree_id': int(new_id),
            'x': base_x,
            'y': base_y,
            'z': base_z
        })
        
    df_stat = pd.DataFrame(treestats)
    df_loc = pd.DataFrame(treelocs)
    
    out_stat_path = os.path.join(output_dir, f"{plot_name}_refined_treestat.csv")
    out_loc_path = os.path.join(output_dir, f"{plot_name}_refined_treelocs.csv")
    
    df_stat.to_csv(out_stat_path, index=False)
    df_loc.to_csv(out_loc_path, index=False)
    print(f"[*] Exported refined statistics: {out_stat_path}")
    
    summary = {
        'plot_name': plot_name,
        'initial_clusters': len(unique_itc),
        'removed_noise_stumps': removed_false_trees,
        'split_merged_clusters': split_clusters,
        'extra_trees_disentangled': total_new_trees_from_splits,
        'final_refined_trees': n_final_trees,
        'mean_height_m': round(df_stat['height'].mean(), 2) if len(df_stat) > 0 else 0,
        'max_height_m': round(df_stat['height'].max(), 2) if len(df_stat) > 0 else 0,
        'min_height_m': round(df_stat['height'].min(), 2) if len(df_stat) > 0 else 0,
        'mean_crown_area_m2': round(df_stat['crown_area'].mean(), 2) if len(df_stat) > 0 else 0,
        'mean_crown_diameter_m': round(df_stat['crown_diameter_m'].mean(), 2) if len(df_stat) > 0 else 0,
        'total_crown_area_m2': round(df_stat['crown_area'].sum(), 2) if len(df_stat) > 0 else 0
    }
    
    return summary


def main():
    input_dir = r"D:\LLR DATA\Clipped_Plots\Segmented_Results"
    output_dir = os.path.join(input_dir, "Refined")
    os.makedirs(output_dir, exist_ok=True)
    
    las_files = sorted(glob.glob(os.path.join(input_dir, "plot_*_segmented.las")))
    print(f"Found {len(las_files)} segmented plot files in {input_dir}")
    print(f"Refined results will be saved to: {output_dir}\n")
    
    t0 = time.time()
    summaries = []
    
    for las_path in las_files:
        try:
            summary = refine_plot(las_path, output_dir)
            if summary:
                summaries.append(summary)
        except Exception as e:
            print(f"[!] ERROR refining {las_path}: {e}")
            import traceback
            traceback.print_exc()
            
    if summaries:
        df_summary = pd.DataFrame(summaries)
        summary_path = os.path.join(output_dir, "all_plots_refined_inventory_summary.csv")
        df_summary.to_csv(summary_path, index=False)
        print(f"\n{'='*70}")
        print(f" ALL PLOTS REFINED SUCCESSFULLY IN {time.time() - t0:.1f}s")
        print(f" Master Refined Summary saved to: {summary_path}")
        print(f"{'='*70}")
        print(df_summary.to_string(index=False))


if __name__ == "__main__":
    main()
