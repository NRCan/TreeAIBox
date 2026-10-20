#!/usr/bin/env python3
"""
Simple visualization of point cloud at 8 meters height plane with DBSCAN clustering.
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os
from sklearn.cluster import DBSCAN


def analyze_height_range(points: np.ndarray, min_height: float = 0.0, max_height: float = 8.0, 
                        step: float = 1.0, thickness: float = 0.1, eps: float = 0.2, min_samples: int = 3):
    """
    Analyze clustering at multiple heights from min_height to max_height.
    
    Args:
        points: All stem points
        min_height: Starting height from base (meters)
        max_height: Ending height from base (meters)
        step: Height increment between analyses (meters)
        thickness: Plane cut thickness (meters)
        eps: DBSCAN eps parameter
        min_samples: DBSCAN min_samples parameter
    """
    print(f"Analyzing height range: {min_height:.1f}m to {max_height:.1f}m with step {step:.1f}m")
    
    heights = np.arange(min_height, max_height + step, step)
    results = []
    
    for height in heights:
        print(f"\n--- Analyzing height {height:.1f}m ---")
        
        min_z = np.min(points[:, 2])
        target_z = min_z + height
        
        # Extract plane cut
        lower_bound = target_z - thickness/2
        upper_bound = target_z + thickness/2
        
        mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
        plane_points = points[mask]
        
        print(f"Found {len(plane_points)} points in range [{lower_bound:.2f}, {upper_bound:.2f}]m")
        
        if len(plane_points) < min_samples:
            print(f"Insufficient points for clustering (need at least {min_samples})")
            results.append({
                'height': height,
                'n_points': len(plane_points),
                'n_clusters': 0,
                'n_noise': len(plane_points),
                'clusters': []
            })
            continue
        
        # Extract 2D coordinates for clustering
        plane_points_2d = plane_points[:, :2]
        
        # Apply DBSCAN clustering
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(plane_points_2d)
        labels = clustering.labels_
        
        # Count clusters (excluding noise labeled -1)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = list(labels).count(-1)
        
        # Get cluster sizes
        cluster_sizes = []
        for label in set(labels):
            if label != -1:
                cluster_sizes.append(np.sum(labels == label))
        
        print(f"DBSCAN found {n_clusters} clusters and {n_noise} noise points")
        if cluster_sizes:
            print(f"Cluster sizes: {cluster_sizes}")
        
        results.append({
            'height': height,
            'n_points': len(plane_points),
            'n_clusters': n_clusters,
            'n_noise': n_noise,
            'cluster_sizes': cluster_sizes
        })
    
    # Print summary
    print(f"\n{'='*50}")
    print("SUMMARY - Clustering Analysis Results")
    print(f"{'='*50}")
    print(f"{'Height':<8} {'Points':<8} {'Clusters':<10} {'Noise':<8} {'Sizes'}")
    print("-" * 60)
    
    for result in results:
        sizes_str = str(result.get('cluster_sizes', [])) if result.get('cluster_sizes') else 'N/A'
        print(f"{result['height']:<8.1f} {result['n_points']:<8} {result['n_clusters']:<10} {result['n_noise']:<8} {sizes_str}")
    
    return results


def visualize_height_clustering(points: np.ndarray, results: list, thickness: float = 0.1, 
                              eps: float = 0.2, min_samples: int = 3, use_height_offset: bool = True):
    """
    Visualize clustering results at all analyzed heights.
    
    Args:
        points: All stem points
        results: Clustering results from analyze_height_range
        thickness: Plane cut thickness
    """
    # Set light theme for white background
    pv.set_plot_theme("document")
    
    # Create PyVista plotter
    plotter = pv.Plotter()
    
    # Add all points (dimmed background)
    all_points_cloud = pv.PolyData(points)
    plotter.add_mesh(all_points_cloud, color='darkgray', point_size=3, opacity=0.1,
                    label='All Stem Points', render_points_as_spheres=False)
    
    colors = ['red', 'blue']
    height_offset = 0.0  # Offset to separate height visualizations
    
    for i, result in enumerate(results):
        height = result['height']
        n_clusters = result['n_clusters']
        
        if result['n_points'] < 3:  # Skip heights with insufficient points
            continue
            
        min_z = np.min(points[:, 2])
        target_z = min_z + height
        
        # Extract plane cut
        lower_bound = target_z - thickness/2
        upper_bound = target_z + thickness/2
        mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
        plane_points = points[mask]
        
        if len(plane_points) == 0:
            continue
            
        # Extract 2D coordinates and cluster
        plane_points_2d = plane_points[:, :2]
        clustering = DBSCAN(eps=0.2, min_samples=3).fit(plane_points_2d)
        labels = clustering.labels_
        
        # Visualize each cluster at this height with slight Z offset
        for j, label in enumerate(set(labels)):
            if label == -1:  # Skip noise points entirely
                continue
                
            cluster_points = plane_points[labels == label]
            
            # All remaining labels are valid clusters
            color = colors[j % len(colors)]
            point_size = 8
            
            # Offset points slightly in Z for visualization (optional)
            offset_points = cluster_points.copy()
            if use_height_offset:
                offset_points[:, 2] += height_offset
            
            if len(offset_points) > 0:
                cluster_cloud = pv.PolyData(offset_points)
                label_text = f'H{height:.1f}m_C{label}'
                plotter.add_mesh(cluster_cloud, color=color, point_size=point_size, 
                               label=label_text, render_points_as_spheres=False)
        
    height_offset += 0.05  # Small offset between heights
    
    # Mark the branching point (where clusters increase from 1 to 2+)
    branching_height = None
    for i, result in enumerate(results):
        if result['n_clusters'] >= 2 and (i == 0 or results[i-1]['n_clusters'] < 2):
            branching_height = result['height']
            break
    
    if branching_height is not None:
        min_z = np.min(points[:, 2])
        branch_z = min_z + branching_height
        
        # Create a highlighted ring at branching height
        center = [(np.min(points[:, 0]) + np.max(points[:, 0]))/2,
                 (np.min(points[:, 1]) + np.max(points[:, 1]))/2,
                 branch_z]
        
        # Create a cylinder to mark the branching point
        branch_marker = pv.Cylinder(center=center, direction=[0, 0, 1], 
                                  height=0.1, radius=0.3)
        plotter.add_mesh(branch_marker, color='yellow', opacity=0.8,
                        label=f'Branching Point: {branching_height:.1f}m')
        
        # Add text annotation
        plotter.add_text(f'BRANCHING STARTS: {branching_height:.1f}m', 
                        position='upper_right', font_size=12, color='red')
    
    # Add info text
    info_lines = ["Clustering Analysis Results:"]
    for result in results:
        if result['n_points'] >= 3:
            height = result['height']
            n_clusters = result['n_clusters']
            n_noise = result['n_noise']
            sizes = result.get('cluster_sizes', [])
            info_lines.append(f"H{height:.1f}m: {n_clusters} clusters, {n_noise} noise")
    
    info_text = "\n".join(info_lines[:10])  # Limit to first 10 lines
    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    
    # Set camera
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    
    # Improve point rendering quality
    plotter.enable_point_picking()
    
    # Show the plot
    plotter.show()


def visualize_clusters_overlay(points: np.ndarray, results: list, thickness: float = 0.1,
                               eps: float = 0.2, min_samples: int = 3):
    """
    Overlay detected cluster points on top of the raw point cloud with no z-offset
    so the user can verify that colored cluster points are actual points in the cloud.

    Args:
        points: All stem points
        results: Clustering results from analyze_height_range
    """
    pv.set_plot_theme("document")
    plotter = pv.Plotter()

    # Show the raw cloud with stronger opacity so points are visible under colored markers
    raw_cloud = pv.PolyData(points)
    plotter.add_mesh(raw_cloud, color='lightgray', point_size=3, opacity=0.6,
                    label='Raw Stem Points', render_points_as_spheres=False)

    colors = ['red', 'blue', 'green', 'orange', 'purple']

    for result in results:
        if result['n_points'] < 1:
            continue

        min_z = np.min(points[:, 2])
        target_z = min_z + result['height']

        lower_bound = target_z - thickness/2
        upper_bound = target_z + thickness/2
        mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
        plane_points = points[mask]
        if len(plane_points) == 0:
            continue

        # Cluster in 2D and then plot the actual 3D points at their real Z
        plane_points_2d = plane_points[:, :2]
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(plane_points_2d)
        labels = clustering.labels_

        for label in set(labels):
            if label == -1:
                continue
            cluster_points = plane_points[labels == label]
            # Plot cluster points at their real coordinates (no offset)
            cluster_cloud = pv.PolyData(cluster_points)
            color = colors[label % len(colors)]
            plotter.add_mesh(cluster_cloud, color=color, point_size=6, render_points_as_spheres=False,
                             label=f'H{result["height"]:.1f}m_C{label}')

    plotter.add_text('Overlay: detected clusters on raw cloud (no z-offset)', position='upper_left', font_size=10)
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    # Draw bounding box around the point cloud
    bounds = raw_cloud.bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)
    bbox = pv.Box(bounds=bounds)
    plotter.add_mesh(bbox, color='black', style='wireframe', line_width=1)

    # Determine branching height (first height where clusters >=2)
    branching_height = None
    for i, r in enumerate(results):
        if r.get('n_clusters', 0) >= 2 and (i == 0 or results[i-1].get('n_clusters', 0) < 2):
            branching_height = np.min(points[:, 2]) + r['height']
            break

    # If found, mark branching location on the bounding box (project to box center X,Y)
    if branching_height is not None:
        cx = (bounds[0] + bounds[1]) / 2.0
        cy = (bounds[2] + bounds[3]) / 2.0
        cz = branching_height
        # Small cylinder to mark split location
        branch_marker = pv.Cylinder(center=[float(cx), float(cy), float(cz)], direction=[0,0,1], height=0.2, radius=0.15)
        plotter.add_mesh(branch_marker, color='yellow', opacity=0.9)

    # Add info text: total height and DBSCAN params
    total_height = bounds[5] - bounds[4]
    params_text = f"Total height: {total_height:.2f}m\nDBSCAN eps={eps}m, min_samples={min_samples}\nThickness={thickness}m"
    if branching_height is not None:
        params_text = f"Branch start: {branching_height - np.min(points[:,2]):.2f}m above base\n" + params_text

    plotter.add_text(params_text, position='lower_left', font_size=10, color='black')
    plotter.enable_point_picking()
    plotter.show()


def visualize_raw_points(points: np.ndarray):
    """
    Visualize all stem points without any clustering or detection.
    
    Args:
        points: All stem points to visualize
    """
    # Set light theme for white background
    pv.set_plot_theme("document")
    
    # Create PyVista plotter
    plotter = pv.Plotter()
    
    # Add all points in a single color
    all_points_cloud = pv.PolyData(points)
    plotter.add_mesh(all_points_cloud, color='blue', point_size=5, opacity=0.8,
                    label='All Stem Points', render_points_as_spheres=False)
    
    # Add info text
    n_points = len(points)
    z_range = f"Z range: {np.min(points[:, 2]):.2f} to {np.max(points[:, 2]):.2f}m"
    
    info_text = f"Raw Point Cloud Visualization\n"
    info_text += f"Total points: {n_points}\n"
    info_text += f"{z_range}"
    
    plotter.add_text(info_text, position='upper_left', font_size=12, color='black')
    
    # Set camera
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    
    # Enable point picking for inspection
    plotter.enable_point_picking()
    
    # Show the plot
    plotter.show()


def analyze_single_height(points: np.ndarray, height: float, thickness: float = 0.1, 
                         eps: float = 0.2, min_samples: int = 3, visualize: bool = True):
    """
    Analyze clustering at a specific height with detailed output.
    
    Args:
        points: All stem points
        height: Height from base to analyze (meters)
        thickness: Plane cut thickness (meters)
        eps: DBSCAN eps parameter
        min_samples: DBSCAN min_samples parameter
        visualize: Whether to show visualization
    """
    print(f"\n{'='*60}")
    print(f"DETAILED ANALYSIS AT HEIGHT {height:.1f}m")
    print(f"{'='*60}")
    
    min_z = np.min(points[:, 2])
    target_z = min_z + height
    
    # Extract plane cut
    lower_bound = target_z - thickness/2
    upper_bound = target_z + thickness/2
    
    mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
    plane_points = points[mask]
    
    print(f"Height range: [{lower_bound:.3f}, {upper_bound:.3f}]m")
    print(f"Points found: {len(plane_points)}")
    
    if len(plane_points) == 0:
        print("No points found at this height!")
        return
    
    # Print all point coordinates
    print(f"\nPoint coordinates (X, Y, Z):")
    for i, point in enumerate(plane_points):
        print(f"  Point {i+1}: ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})")
    
    if len(plane_points) < min_samples:
        print(f"\nInsufficient points for clustering (need at least {min_samples})")
        return
    
    # Extract 2D coordinates for clustering
    plane_points_2d = plane_points[:, :2]
    
    # Print 2D coordinates used for clustering
    print(f"\n2D coordinates for clustering (X, Y):")
    for i, point_2d in enumerate(plane_points_2d):
        print(f"  Point {i+1}: ({point_2d[0]:.3f}, {point_2d[1]:.3f})")
    
    # Calculate pairwise distances
    print(f"\nPairwise distances between points:")
    for i in range(len(plane_points_2d)):
        for j in range(i+1, len(plane_points_2d)):
            dist = np.linalg.norm(plane_points_2d[i] - plane_points_2d[j])
            print(f"  Distance P{i+1}-P{j+1}: {dist:.3f}m")
    
    # Apply DBSCAN clustering
    print(f"\nApplying DBSCAN with eps={eps}m, min_samples={min_samples}")
    clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(plane_points_2d)
    labels = clustering.labels_
    
    # Count clusters (excluding noise labeled -1)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    
    print(f"\nClustering results:")
    print(f"  Total points: {len(plane_points)}")
    print(f"  Number of clusters: {n_clusters}")
    print(f"  Number of noise points: {n_noise}")
    
    # Analyze each cluster
    for label in set(labels):
        if label == -1:
            cluster_points = plane_points[labels == label]
            print(f"\n  Noise points ({len(cluster_points)} points):")
            for i, point in enumerate(cluster_points):
                idx = np.where((plane_points == point).all(axis=1))[0][0]
                print(f"    Point {idx+1}: ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})")
        else:
            cluster_points = plane_points[labels == label]
            print(f"\n  Cluster {label} ({len(cluster_points)} points):")
            for i, point in enumerate(cluster_points):
                idx = np.where((plane_points == point).all(axis=1))[0][0]
                print(f"    Point {idx+1}: ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})")
    
    # Analyze why clustering behaved this way
    print(f"\nAnalysis of clustering behavior:")
    if n_clusters == 1:
        print("  - All points formed a single cluster")
        print(f"  - Maximum distance between points: {np.max([np.linalg.norm(plane_points_2d[i] - plane_points_2d[j]) for i in range(len(plane_points_2d)) for j in range(i+1, len(plane_points_2d))]):.3f}m")
        print(f"  - DBSCAN eps parameter: {eps}m")
        if np.max([np.linalg.norm(plane_points_2d[i] - plane_points_2d[j]) for i in range(len(plane_points_2d)) for j in range(i+1, len(plane_points_2d))]) <= eps:
            print("  - All points are within eps distance of each other")
        else:
            print("  - Some points are farther than eps, but still formed one cluster (density-connected)")
    
    elif n_clusters > 1:
        print(f"  - Points split into {n_clusters} separate clusters")
        print("  - Clusters are not density-connected within eps distance")
    
    if n_noise > 0:
        print(f"  - {n_noise} points were classified as noise (not enough neighbors within eps)")
    
    if visualize:
        visualize_single_height(points, height, thickness, eps, min_samples)
        # Also show raw point cloud visualization
        visualize_raw_points(points)


def visualize_single_height(points: np.ndarray, height: float, thickness: float = 0.1,
                           eps: float = 0.2, min_samples: int = 3):
    """
    Visualize clustering at a specific height with detailed annotations.
    
    Args:
        points: All stem points
        height: Height to visualize
        thickness: Plane cut thickness
        eps: DBSCAN eps parameter
        min_samples: DBSCAN min_samples parameter
    """
    # Set light theme for white background
    pv.set_plot_theme("document")
    
    # Create PyVista plotter
    plotter = pv.Plotter()
    
    # Add all points (dimmed background)
    all_points_cloud = pv.PolyData(points)
    plotter.add_mesh(all_points_cloud, color='darkgray', point_size=3, opacity=0.1,
                    label='All Stem Points', render_points_as_spheres=False)
    
    min_z = np.min(points[:, 2])
    target_z = min_z + height
    
    # Extract plane cut
    lower_bound = target_z - thickness/2
    upper_bound = target_z + thickness/2
    mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
    plane_points = points[mask]
    
    if len(plane_points) == 0:
        plotter.add_text(f'No points found at {height:.1f}m', position='upper_right', 
                        font_size=14, color='red')
        plotter.show()
        return
    
    # Extract 2D coordinates and cluster
    plane_points_2d = plane_points[:, :2]
    clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(plane_points_2d)
    labels = clustering.labels_
    
    colors = ['red', 'blue', 'green', 'orange', 'purple']
    
    # Visualize each cluster
    for label in set(labels):
        if label == -1:
            # Noise points
            noise_points = plane_points[labels == label]
            if len(noise_points) > 0:
                noise_cloud = pv.PolyData(noise_points)
                plotter.add_mesh(noise_cloud, color='gray', point_size=8,
                               label=f'Noise ({len(noise_points)} pts)', 
                               render_points_as_spheres=False)
        else:
            # Valid clusters
            cluster_points = plane_points[labels == label]
            color = colors[label % len(colors)]
            cluster_cloud = pv.PolyData(cluster_points)
            plotter.add_mesh(cluster_cloud, color=color, point_size=8,
                           label=f'Cluster {label} ({len(cluster_points)} pts)',
                           render_points_as_spheres=False)
    
    # Add reference plane at the analyzed height
    plane_bounds = [
        np.min(points[:, 0]) - 1, np.max(points[:, 0]) + 1,
        np.min(points[:, 1]) - 1, np.max(points[:, 1]) + 1,
        target_z, target_z
    ]
    reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                      float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                      float(target_z)],
                              i_size=plane_bounds[1]-plane_bounds[0],
                              j_size=plane_bounds[3]-plane_bounds[2])
    plotter.add_mesh(reference_plane, color='lightblue', opacity=0.3,
                    label=f'Analysis Plane: {height:.1f}m')
    
    # Add info text
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    
    info_text = f"Height: {height:.1f}m\n"
    info_text += f"Points: {len(plane_points)}\n"
    info_text += f"Clusters: {n_clusters}\n"
    info_text += f"Noise: {n_noise}\n"
    info_text += f"DBSCAN: eps={eps}m, min_samples={min_samples}"
    
    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    
    # Set camera
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    
    # Enable point picking for inspection
    plotter.enable_point_picking()
    
    # Show the plot
    plotter.show()


def load_stem_points(las_path: str):
    """
    Load stem points from LAS file.

    Args:
        las_path: Path to LAS file

    Returns:
        Nx3 array of points
    """
    print(f"Loading LAS file: {las_path}")

    las = laspy.read(las_path)

    # Check for stem classification
    if 'stemcls' not in las.point_format.dimension_names:
        print("Warning: No 'stemcls' field found. Using all points.")
        stem_mask = np.ones(len(las.points), dtype=bool)
    else:
        stemcls = las['stemcls']
        stem_mask = stemcls == 2
        print(f"Found {np.sum(stem_mask)} stem points out of {len(las.points)} total points")

    # Extract coordinates
    points = np.column_stack([
        np.array(las.x)[stem_mask],
        np.array(las.y)[stem_mask],
        np.array(las.z)[stem_mask]
    ])

    print(f"Loaded {len(points)} points")
    print(f"Z range: {np.min(points[:, 2]):.2f} to {np.max(points[:, 2]):.2f}m")

    return points


def main():
    parser = argparse.ArgumentParser(description='Analyze stem point clustering from base to specified height')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--max-height', '-H', type=float, default=8.0,
                       help='Maximum height to analyze from base (meters)')
    parser.add_argument('--step', '-s', type=float, default=1.0,
                       help='Height step between analyses (meters)')
    parser.add_argument('--thickness', '-t', type=float, default=0.1,
                       help='Plane cut thickness (meters)')
    parser.add_argument('--eps', '-e', type=float, default=0.2,
                       help='DBSCAN eps parameter (maximum distance)')
    parser.add_argument('--min-samples', '-m', type=int, default=3,
                       help='DBSCAN min_samples parameter (minimum points per cluster)')
    parser.add_argument('--single-height', '-sh', type=float,
                       help='Analyze and visualize only a specific height (meters)')
    parser.add_argument('--visualize', '-v', action='store_true',
                       help='Show 3D visualization of clustering results')
    parser.add_argument('--no-offset', action='store_true',
                       help='Do not apply small Z offsets when plotting clusters (plot at real Z)')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return

    try:
        # Load stem points
        all_points = load_stem_points(args.input)

        if len(all_points) == 0:
            print("No points to process!")
            return

        # Analyze clustering
        if args.single_height is not None:
            # Analyze single height with detailed output
            analyze_single_height(all_points, args.single_height, args.thickness, 
                                args.eps, args.min_samples, args.visualize)
        else:
            # Analyze height range
            results = analyze_height_range(all_points, min_height=0.0, max_height=args.max_height,
                                         step=args.step, thickness=args.thickness, 
                                         eps=args.eps, min_samples=args.min_samples)
            
            # Visualize if requested
            if args.visualize:
                # Show only the overlay visualization (detected clusters on raw cloud)
                visualize_clusters_overlay(all_points, results, args.thickness, args.eps, args.min_samples)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()