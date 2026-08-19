#!/usr/bin/env python3
"""
Extract and visualize tree components (trunk and branches) using a specified branching height.
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os
from sklearn.neighbors import KDTree
from sklearn.cluster import DBSCAN


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


def extract_components(points: np.ndarray, branching_height: float, assign_radius: float = 0.5,
                      vertical_window: float = 0.2, min_vertical_overlap: float = 0.1, use_nearest_neighbor: bool = False):
    """
    Extract tree components: trunk (below branching height) and branches (above, assigned to nearest cluster).

    Args:
        points: All stem points
        branching_height: Height where branching occurs (from base)
        assign_radius: Maximum horizontal distance for assigning points to branch centroids
        vertical_window: Vertical distance window for connectivity checks
        min_vertical_overlap: Minimum vertical overlap required for connectivity
    """
    min_z = np.min(points[:, 2])
    branching_z = min_z + branching_height

    # Separate points by height
    trunk_mask = points[:, 2] <= branching_z
    trunk_points = points[trunk_mask]
    branch_candidate_points = points[~trunk_mask]

    print(f"Branching height: {branching_height:.2f}m (Z = {branching_z:.2f}m)")
    print(f"Total points: {len(points)}")
    print(f"Trunk points: {len(trunk_points)}")
    print(f"Branch candidate points: {len(branch_candidate_points)}")

    # If no branch points, return just trunk
    if len(branch_candidate_points) == 0:
        return {
            'trunk': trunk_points,
            'branches': [],
            'unassigned': np.empty((0, 3))
        }

    # Get cluster centroids at branching height (simplified approach)
    # In a real implementation, you'd get this from the clustering analysis
    # For now, we'll use a simple approach: find the main clusters at branching height

    # Extract points at branching height for clustering
    height_window = 0.1  # 10cm window
    branch_plane_mask = (points[:, 2] >= branching_z - height_window/2) & \
                       (points[:, 2] <= branching_z + height_window/2)
    branch_plane_points = points[branch_plane_mask]

    if len(branch_plane_points) < 3:
        print("Warning: Insufficient points at branching height for clustering")
        return {
            'trunk': trunk_points,
            'branches': [branch_candidate_points],
            'unassigned': np.empty((0, 3))
        }

    # Simple clustering: find centroids of major clusters
    # This is a simplified version - in practice you'd use the same DBSCAN as branch_split_detection.py
    clustering = DBSCAN(eps=0.2, min_samples=3).fit(branch_plane_points[:, :2])
    labels = clustering.labels_

    centroids = []
    for label in set(labels):
        if label != -1:  # Skip noise
            cluster_points = branch_plane_points[labels == label]
            centroid = np.mean(cluster_points, axis=0)
            centroids.append(centroid)

    print(f"Found {len(centroids)} branch centroids at branching height")

    if len(centroids) == 0:
        return {
            'trunk': trunk_points,
            'branches': [branch_candidate_points],
            'unassigned': np.empty((0, 3))
        }

    # Simple nearest neighbor assignment (no radius constraint)
    centroids_2d = np.array([[c[0], c[1]] for c in centroids])
    kdtree = KDTree(centroids_2d)

    branch_assignments = []
    unassigned_points = []

    print(f"Using nearest neighbor assignment (no radius limit)")

    for point in branch_candidate_points:
        point_2d = point[:2]
        point_z = point[2]

        # Find nearest centroid only
        distances, indices = kdtree.query([point_2d], k=1)
        nearest_centroid_idx = indices[0][0]

        # Ensure we have enough branch lists
        if nearest_centroid_idx >= len(branch_assignments):
            branch_assignments.extend([[] for _ in range(nearest_centroid_idx - len(branch_assignments) + 1)])

        # Optional: Add vertical connectivity check
        if vertical_window > 0 and len(branch_assignments[nearest_centroid_idx]) > 0:
            branch_z_values = np.array(branch_assignments[nearest_centroid_idx])[:, 2]
            vertical_distances = np.abs(branch_z_values - point_z)

            # Point must be within vertical_window of at least one existing branch point
            min_vertical_dist = np.min(vertical_distances)
            if min_vertical_dist <= vertical_window:
                branch_assignments[nearest_centroid_idx].append(point)
            else:
                unassigned_points.append(point)
        else:
            # No vertical check or first point for this branch
            branch_assignments[nearest_centroid_idx].append(point)

    # Convert to numpy arrays
    branch_arrays = [np.array(branch_list) for branch_list in branch_assignments if len(branch_list) > 0]
    unassigned_array = np.array(unassigned_points) if unassigned_points else np.empty((0, 3))

    print(f"Assigned to {len(branch_arrays)} branches")
    print(f"Unassigned points: {len(unassigned_array)}")
    print(f"Connectivity parameters: vertical_window={vertical_window}m, min_overlap={min_vertical_overlap}m")

    return {
        'trunk': trunk_points,
        'branches': branch_arrays,
        'unassigned': unassigned_array,
        'centroids': centroids
    }


def visualize_components(components: dict, branching_height: float, centroids: list = [], points: np.ndarray = np.array([]), mode: str = 'sequence'):
    """
    Visualize tree components in different modes.
    """
    if mode == 'sequence':
        # Show all views in sequence
        print("Showing FULL TREE...")
        visualize_full_tree(points, branching_height)
        print("Showing TRUNK (below split)...")
        visualize_trunk(components, branching_height)
        print("Showing CROWN (above split)...")
        visualize_crown(components, branching_height, points)
        print("Showing CROWN MIDDLE SLICE...")
        visualize_crown_middle(components, branching_height, points)
    elif mode == 'full':
        visualize_full_tree(points, branching_height)
    elif mode == 'trunk':
        visualize_trunk(components, branching_height)
    elif mode == 'crown':
        visualize_crown(components, branching_height, points)
    elif mode == 'middle_slice':
        visualize_crown_middle(components, branching_height, points)
        visualize_crown_middle(components, branching_height, points)


def visualize_full_tree(points: np.ndarray, branching_height: float):
    """Visualize the complete tree with all points."""
    if len(points) == 0:
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    # Show all points
    tree_cloud = pv.PolyData(points)
    plotter.add_mesh(tree_cloud, color='blue', point_size=4, opacity=0.8,
                    label=f'Complete Tree ({len(points)} pts)', render_points_as_spheres=False)

    # Add bounding box
    bounds = tree_cloud.bounds
    bounding_box = pv.Cube(bounds=bounds)
    plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                    label='Bounding Box')

    # Add reference plane at branching height (estimated)
    if len(points) > 0:
        min_z = np.min(points[:, 2])
        branching_z = min_z + branching_height

        plane_bounds = [
            np.min(points[:, 0]) - 1, np.max(points[:, 0]) + 1,
            np.min(points[:, 1]) - 1, np.max(points[:, 1]) + 1,
            branching_z, branching_z
        ]

        reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                          float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                          float(branching_z)],
                                  i_size=plane_bounds[1]-plane_bounds[0],
                                  j_size=plane_bounds[3]-plane_bounds[2])
        plotter.add_mesh(reference_plane, color='red', opacity=0.4,
                        label=f'Branching Height: {branching_height:.1f}m')

    # Calculate dimensions
    width = bounds[1] - bounds[0]
    length = bounds[3] - bounds[2]
    height = bounds[5] - bounds[4]

    info_text = f"Complete Tree Visualization\n"
    info_text += f"Total points: {len(points)}\n"
    info_text += f"Dimensions: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Branching height: {branching_height:.2f}m"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    plotter.show()


def visualize_trunk(components: dict, branching_height: float):
    """Visualize only the trunk points below branching height."""
    trunk_points = components['trunk']
    if len(trunk_points) == 0:
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    # Show trunk points
    trunk_cloud = pv.PolyData(trunk_points)
    plotter.add_mesh(trunk_cloud, color='blue', point_size=6, opacity=0.9,
                    label=f'Main Trunk ({len(trunk_points)} pts)', render_points_as_spheres=False)

    # Add bounding box
    bounds = trunk_cloud.bounds
    bounding_box = pv.Cube(bounds=bounds)
    plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                    label='Trunk Bounding Box')

    # Add reference plane at branching height
    min_z = np.min(trunk_points[:, 2])
    branching_z = min_z + branching_height

    plane_bounds = [
        np.min(trunk_points[:, 0]) - 1, np.max(trunk_points[:, 0]) + 1,
        np.min(trunk_points[:, 1]) - 1, np.max(trunk_points[:, 1]) + 1,
        branching_z, branching_z
    ]

    reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                      float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                      float(branching_z)],
                              i_size=plane_bounds[1]-plane_bounds[0],
                              j_size=plane_bounds[3]-plane_bounds[2])
    plotter.add_mesh(reference_plane, color='red', opacity=0.4,
                    label=f'Branching Height: {branching_height:.1f}m')

    # Calculate dimensions
    width = bounds[1] - bounds[0]
    length = bounds[3] - bounds[2]
    height = bounds[5] - bounds[4]

    trunk_height = np.max(trunk_points[:, 2]) - np.min(trunk_points[:, 2])
    info_text = f"Tree Trunk Visualization\n"
    info_text += f"Trunk points: {len(trunk_points)}\n"
    info_text += f"Trunk height: {trunk_height:.2f}m\n"
    info_text += f"Bounding box: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Branching height: {branching_height:.2f}m"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    plotter.show()


def visualize_crown(components: dict, branching_height: float, points: np.ndarray):
    """Visualize points above the branching height (tree crown)."""
    trunk_points = components['trunk']
    if len(trunk_points) == 0 or len(points) == 0:
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    min_z = np.min(trunk_points[:, 2])
    branching_z = min_z + branching_height

    # Filter points above the branching height
    above_branching_mask = points[:, 2] > branching_z
    points_above = points[above_branching_mask]

    if len(points_above) > 0:
        crown_cloud = pv.PolyData(points_above)
        plotter.add_mesh(crown_cloud, color='green', point_size=5, opacity=0.8,
                        label=f'Tree Crown ({len(points_above)} pts)', render_points_as_spheres=False)

        # Add bounding box
        bounds = crown_cloud.bounds
        bounding_box = pv.Cube(bounds=bounds)
        plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                        label='Crown Bounding Box')

        # Calculate dimensions
        width = bounds[1] - bounds[0]
        length = bounds[3] - bounds[2]
        height = bounds[5] - bounds[4]

    # Add reference plane at branching height
    plane_bounds = [
        np.min(trunk_points[:, 0]) - 1, np.max(trunk_points[:, 0]) + 1,
        np.min(trunk_points[:, 1]) - 1, np.max(trunk_points[:, 1]) + 1,
        branching_z, branching_z
    ]

    reference_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                      float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                      float(branching_z)],
                              i_size=plane_bounds[1]-plane_bounds[0],
                              j_size=plane_bounds[3]-plane_bounds[2])
    plotter.add_mesh(reference_plane, color='red', opacity=0.4,
                    label=f'Branching Height: {branching_height:.1f}m')

    info_text = f"Tree Crown Visualization\n"
    info_text += f"Crown points: {len(points_above)}\n"
    if len(points_above) > 0:
        info_text += f"Crown dimensions: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Branching height: {branching_height:.2f}m"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    plotter.show()


def visualize_crown_middle(components: dict, branching_height: float, points: np.ndarray):
    """Visualize all crown points with a horizontal slice plane through the middle."""
    trunk_points = components['trunk']
    if len(trunk_points) == 0 or len(points) == 0:
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    min_z = np.min(trunk_points[:, 2])
    branching_z = min_z + branching_height

    # Filter points above the branching height
    above_branching_mask = points[:, 2] > branching_z
    points_above = points[above_branching_mask]

    if len(points_above) == 0:
        return

    # Show ALL crown points
    crown_cloud = pv.PolyData(points_above)
    plotter.add_mesh(crown_cloud, color='green', point_size=5, opacity=0.8,
                    label=f'All Crown Points ({len(points_above)} pts)', render_points_as_spheres=False)

    # Add bounding box for crown
    bounds = crown_cloud.bounds
    bounding_box = pv.Cube(bounds=bounds)
    plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                    label='Crown Bounding Box')

    # Calculate middle height of the crown
    crown_min_z = np.min(points_above[:, 2])
    crown_max_z = np.max(points_above[:, 2])
    middle_z = (crown_min_z + crown_max_z) / 2

    # Extract points near middle slice for clustering (within 0.1m tolerance)
    slice_tolerance = 0.1
    slice_mask = (points_above[:, 2] >= middle_z - slice_tolerance) & (points_above[:, 2] <= middle_z + slice_tolerance)
    slice_points = points_above[slice_mask]
    
    if len(slice_points) > 0:
        # Apply DBSCAN clustering to horizontal slice
        clustering = DBSCAN(eps=0.2, min_samples=3).fit(slice_points[:, :2])
        labels = clustering.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = list(labels).count(-1)
        
        # Color clusters alternately in red and blue
        colors = ['red', 'blue']
        for cluster_id in range(n_clusters):
            cluster_mask = labels == cluster_id
            cluster_points = slice_points[cluster_mask]
            if len(cluster_points) > 0:
                cluster_cloud = pv.PolyData(cluster_points)
                color = colors[cluster_id % 2]
                branch_name = "One" if cluster_id % 2 == 0 else "Two"
                plotter.add_mesh(cluster_cloud, color=color, point_size=8, 
                               label=f'Branch {branch_name} Cluster ({len(cluster_points)} pts)', 
                               render_points_as_spheres=True)
                
                # Calculate bounding circle for the cluster
                cluster_xy = cluster_points[:, :2]  # Only X,Y coordinates
                centroid = np.mean(cluster_xy, axis=0)
                distances = np.linalg.norm(cluster_xy - centroid, axis=1)
                radius = np.max(distances)
                
                # Create a circle at the middle slice height
                circle = pv.Circle(radius=radius, resolution=32)
                # Translate to the centroid position
                circle.translate([centroid[0], centroid[1], middle_z], inplace=True)
                plotter.add_mesh(circle, color=color, style='wireframe', line_width=3,
                               label=f'Branch {branch_name} Cluster boundary (r={radius:.2f}m)')

    # Extend Branch One clusters vertically using KDTree
    if n_clusters > 0:
        # Build KDTree for all crown points
        tree = KDTree(points_above)
        
        # For each Branch One cluster (red clusters, cluster_id % 2 == 0)
        for cluster_id in range(n_clusters):
            if cluster_id % 2 == 0:  # Branch One (red) clusters
                cluster_mask = labels == cluster_id
                cluster_points = slice_points[cluster_mask]
                
                if len(cluster_points) > 0:
                    # Find points above and below this cluster using KDTree
                    extended_points = []
                    horizontal_radius = 0.5  # 0.5m horizontal search radius
                    
                    for point in cluster_points:
                        # Find all crown points within horizontal radius (unlimited vertical)
                        horizontal_distances = np.sqrt((points_above[:, 0] - point[0])**2 + (points_above[:, 1] - point[1])**2)
                        nearby_mask = horizontal_distances <= horizontal_radius
                        nearby_points = points_above[nearby_mask]
                        
                        # Include all nearby points (remove vertical slice exclusion)
                        extended_points.extend(nearby_points)
                    
                    if len(extended_points) > 0:
                        extended_array = np.array(extended_points)
                        extended_cloud = pv.PolyData(extended_array)
                        plotter.add_mesh(extended_cloud, color='red', point_size=6, opacity=0.7,
                                       label=f'Branch One Extended ({len(extended_array)} pts)',
                                       render_points_as_spheres=True)

    # Add middle slice plane
    middle_plane_bounds = [
        np.min(points_above[:, 0]) - 1, np.max(points_above[:, 0]) + 1,
        np.min(points_above[:, 1]) - 1, np.max(points_above[:, 1]) + 1,
        middle_z, middle_z
    ]

    middle_plane = pv.Plane(center=[float(np.mean([middle_plane_bounds[0], middle_plane_bounds[1]])),
                                   float(np.mean([middle_plane_bounds[2], middle_plane_bounds[3]])),
                                   float(middle_z)],
                           i_size=middle_plane_bounds[1]-middle_plane_bounds[0],
                           j_size=middle_plane_bounds[3]-middle_plane_bounds[2])
    plotter.add_mesh(middle_plane, color='yellow', opacity=0.6,
                    label=f'Middle Slice Plane: {middle_z:.2f}m')

    # Add branching height reference plane
    plane_bounds = [
        np.min(trunk_points[:, 0]) - 1, np.max(trunk_points[:, 0]) + 1,
        np.min(trunk_points[:, 1]) - 1, np.max(trunk_points[:, 1]) + 1,
        branching_z, branching_z
    ]

    branching_plane = pv.Plane(center=[float(np.mean([plane_bounds[0], plane_bounds[1]])),
                                      float(np.mean([plane_bounds[2], plane_bounds[3]])),
                                      float(branching_z)],
                              i_size=plane_bounds[1]-plane_bounds[0],
                              j_size=plane_bounds[3]-plane_bounds[2])
    plotter.add_mesh(branching_plane, color='red', opacity=0.4,
                    label=f'Branching Height: {branching_height:.1f}m')

    # Calculate dimensions
    width = bounds[1] - bounds[0]
    length = bounds[3] - bounds[2]
    height = bounds[5] - bounds[4]
    crown_height = crown_max_z - branching_z

    info_text = f"Crown Middle Slice Visualization\n"
    info_text += f"All crown points: {len(points_above)}\n"
    info_text += f"Crown dimensions: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Crown height: {crown_height:.2f}m\n"
    info_text += f"Middle slice at: {middle_z:.2f}m\n"
    info_text += f"Branching height: {branching_height:.2f}m"
    
    # Add clustering information if slice points were found
    if len(slice_points) > 0:
        info_text += f"\nSlice points (±{slice_tolerance:.1f}m): {len(slice_points)}\n"
        info_text += f"DBSCAN clusters: {n_clusters}, noise: {n_noise}\n"
        info_text += f"DBSCAN eps=0.2m, min_samples=3"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30
    
    # Add legend
    plotter.add_legend()
    
    plotter.show()


def save_components_to_csv(components: dict, output_prefix: str):
    """
    Save extracted components to CSV files.

    Args:
        components: Dictionary with trunk, branches, and unassigned points
        output_prefix: Prefix for output filenames
    """
    # Save trunk
    if len(components['trunk']) > 0:
        np.savetxt(f"{output_prefix}_trunk.csv", components['trunk'],
                  delimiter=',', header='X,Y,Z', comments='')
        print(f"Saved trunk to {output_prefix}_trunk.csv")

    # Save branches
    for i, branch in enumerate(components['branches']):
        if len(branch) > 0:
            np.savetxt(f"{output_prefix}_branch_{i+1}.csv", branch,
                      delimiter=',', header='X,Y,Z', comments='')
            print(f"Saved branch {i+1} to {output_prefix}_branch_{i+1}.csv")

    # Save unassigned
    if len(components['unassigned']) > 0:
        np.savetxt(f"{output_prefix}_unassigned.csv", components['unassigned'],
                  delimiter=',', header='X,Y,Z', comments='')
        print(f"Saved unassigned to {output_prefix}_unassigned.csv")


def main():
    parser = argparse.ArgumentParser(description='Extract and visualize tree components (trunk and branches)')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--branching-height', '-b', type=float, required=True,
                       help='Height where branching occurs (meters from base)')
    parser.add_argument('--assign-radius', '-r', type=float, default=0.5,
                       help='Maximum horizontal distance for assigning points to branch centroids (meters)')
    parser.add_argument('--vertical-window', '-vw', type=float, default=0.2,
                       help='Vertical distance window for connectivity checks (meters)')
    parser.add_argument('--min-vertical-overlap', '-mvo', type=float, default=0.1,
                       help='Minimum vertical overlap required for connectivity (meters)')
    parser.add_argument('--visualize', '-v', action='store_true',
                       help='Show 3D visualization of components')
    parser.add_argument('--viz-mode', choices=['full', 'trunk', 'crown', 'middle_slice', 'sequence'],
                       default='sequence', help='Visualization mode: full tree, trunk only, crown only, middle slice, or show all in sequence')
    parser.add_argument('--output', '-o', help='Output prefix for CSV files')

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

        # Extract components
        components = extract_components(all_points, args.branching_height, args.assign_radius,
                                      args.vertical_window, args.min_vertical_overlap)

        # Save to CSV if requested
        if args.output:
            save_components_to_csv(components, args.output)

        # Visualize if requested
        if args.visualize:
            centroids = components.get('centroids', [])
            visualize_components(components, args.branching_height, centroids, all_points, args.viz_mode)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
