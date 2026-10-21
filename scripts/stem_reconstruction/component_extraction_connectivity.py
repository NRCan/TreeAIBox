#!/usr/bin/env python3
"""
Extract and visualize tree components (trunk and branches) using a specified branching height.
Connectivity-based approach for branch extension.
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os
from typing import Optional
from sklearn.neighbors import KDTree
from sklearn.cluster import DBSCAN
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


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

    # Use middle slice clustering for branch identification (same as visualization)
    # Calculate middle height of the crown
    if len(branch_candidate_points) > 0:
        crown_min_z = np.min(branch_candidate_points[:, 2])
        crown_max_z = np.max(branch_candidate_points[:, 2])
        middle_z = (crown_min_z + crown_max_z) / 2

        # Extract points near middle slice for clustering (within 0.1m tolerance)
        slice_tolerance = 0.1
        slice_mask = (branch_candidate_points[:, 2] >= middle_z - slice_tolerance) & (branch_candidate_points[:, 2] <= middle_z + slice_tolerance)
        slice_points = branch_candidate_points[slice_mask]

        centroids = []
        if len(slice_points) >= 3:
            # Apply DBSCAN clustering to horizontal slice (same as visualization)
            clustering = DBSCAN(eps=0.2, min_samples=3).fit(slice_points[:, :2])
            labels = clustering.labels_
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

            print(f"Found {n_clusters} branch clusters at middle slice (Z = {middle_z:.2f}m)")

            # Get centroids for each cluster
            for cluster_id in range(n_clusters):
                cluster_mask = labels == cluster_id
                cluster_points = slice_points[cluster_mask]
                if len(cluster_points) > 0:
                    centroid = np.mean(cluster_points, axis=0)
                    centroids.append(centroid)
        else:
            print("Warning: Insufficient points at middle slice for clustering")
            centroids = []

    if len(centroids) == 0:
        return {
            'trunk': trunk_points,
            'branches': [branch_candidate_points],
            'unassigned': np.empty((0, 3))
        }

    # Use connectivity-based approach (same as visualization)
    # Build connectivity graph for all branch candidate points
    horizontal_radius = 0.2  # 20cm horizontal connectivity radius
    vertical_radius = 0.5    # 50cm vertical connectivity radius

    print(f"Building connectivity graph with {len(branch_candidate_points)} branch candidate points...")
    print(f"Connectivity: horizontal={horizontal_radius}m, vertical={vertical_radius}m")
    n_points = len(branch_candidate_points)

    # Create adjacency matrix for 3D connectivity (horizontal + vertical)
    # Points are connected if within BOTH horizontal AND vertical radius
    rows = []
    cols = []

    for i in range(n_points):
        for j in range(i+1, n_points):
            # Check horizontal distance
            dist_xy = np.sqrt((branch_candidate_points[i, 0] - branch_candidate_points[j, 0])**2 +
                            (branch_candidate_points[i, 1] - branch_candidate_points[j, 1])**2)
            # Check vertical distance
            dist_z = abs(branch_candidate_points[i, 2] - branch_candidate_points[j, 2])
            
            if dist_xy <= horizontal_radius and dist_z <= vertical_radius:
                rows.extend([i, j])
                cols.extend([j, i])

    branch_arrays = []
    unassigned_points = []

    if len(rows) > 0:
        # Create sparse adjacency matrix
        adjacency = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_points, n_points))

        # Find connected components
        n_components, connectivity_labels = connected_components(csgraph=adjacency, directed=False, return_labels=True)

        print(f"Found {n_components} connected components in crown (3D connectivity)")

        # For each cluster from middle slice, find connected components containing cluster points
        for cluster_id in range(len(centroids)):
            cluster_mask = labels == cluster_id
            cluster_points = slice_points[cluster_mask]
            
            if len(cluster_points) > 0:
                # Find indices of cluster points in the full branch_candidate_points array
                cluster_indices = []
                for cluster_point in cluster_points:
                    # Find this point in the full branch candidate array
                    diffs = branch_candidate_points - cluster_point
                    distances = np.linalg.norm(diffs, axis=1)
                    idx = np.argmin(distances)
                    if distances[idx] < 0.01:  # Very close match
                        cluster_indices.append(idx)
                
                if len(cluster_indices) > 0:
                    # Get the component labels for these cluster points
                    cluster_component_labels = set(connectivity_labels[idx] for idx in cluster_indices)
                    
                    # Collect all points in these connected components
                    branch_points = []
                    for comp_label in cluster_component_labels:
                        component_mask = connectivity_labels == comp_label
                        component_points = branch_candidate_points[component_mask]
                        branch_points.extend(component_points)
                    
                    if len(branch_points) > 0:
                        branch_arrays.append(np.array(branch_points))

        # Find unassigned points (not in any branch's connected components)
        assigned_indices = set()
        for branch in branch_arrays:
            for branch_point in branch:
                # Find index of this point in branch_candidate_points
                diffs = branch_candidate_points - branch_point
                distances = np.linalg.norm(diffs, axis=1)
                idx = np.argmin(distances)
                if distances[idx] < 0.01:
                    assigned_indices.add(idx)
        
        unassigned_indices = [i for i in range(len(branch_candidate_points)) if i not in assigned_indices]
        if len(unassigned_indices) > 0:
            unassigned_points = branch_candidate_points[unassigned_indices]
        else:
            unassigned_points = np.empty((0, 3))
    else:
        # No connectivity found, assign all to first branch
        branch_arrays = [branch_candidate_points]
        unassigned_points = np.empty((0, 3))

    unassigned_array = np.array(unassigned_points) if len(unassigned_points) > 0 else np.empty((0, 3))

    print(f"Assigned to {len(branch_arrays)} branches")
    print(f"Unassigned points: {len(unassigned_array)}")
    print(f"Connectivity parameters: horizontal={horizontal_radius}m, vertical={vertical_radius}m")

    return {
        'trunk': trunk_points,
        'branches': branch_arrays,
        'unassigned': unassigned_array,
        'centroids': centroids
    }


def visualize_components(components: dict, branching_height: float, centroids: list, all_points: np.ndarray, viz_mode: str = 'sequence'):
    """
    Visualize tree components based on the specified mode.

    Args:
        components: Dictionary with trunk, branches, and unassigned points
        branching_height: Height where branching occurs
        centroids: List of branch centroids
        all_points: All original points
        viz_mode: Visualization mode ('full', 'trunk', 'crown', 'middle_slice', 'sequence', 'components_circles')
    """
    if viz_mode == 'components_circles':
        # Visualize all components merged in a single plot
        trunk_points = components['trunk']
        branches = components['branches']

        plotter = pv.Plotter()
        pv.set_plot_theme("document")

        # Visualize trunk
        if len(trunk_points) > 0:
            visualize_component_circles_merged(plotter, trunk_points, "TRUNK", color='brown')

        # Visualize branches
        branch_colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan']
        for i, branch_points in enumerate(branches):
            if len(branch_points) > 0:
                color = branch_colors[i % len(branch_colors)]
                visualize_component_circles_merged(plotter, branch_points, f"BRANCH {i+1}", color=color)

        # Add overall bounding box
        all_points = np.vstack([trunk_points] + branches)
        if len(all_points) > 0:
            bounds = [np.min(all_points[:, 0]), np.max(all_points[:, 0]),
                     np.min(all_points[:, 1]), np.max(all_points[:, 1]),
                     np.min(all_points[:, 2]), np.max(all_points[:, 2])]
            bounding_box = pv.Cube(bounds=bounds)
            plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=2,
                            label='Overall Bounding Box')

        # Add summary info
        total_points = len(trunk_points) + sum(len(branch) for branch in branches)
        info_text = f"Tree Components Visualization\n"
        info_text += f"Total points: {total_points}\n"
        info_text += f"Components: Trunk + {len([b for b in branches if len(b) > 0])} branches\n"
        info_text += f"Branching height: {branching_height:.1f}m"

        plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
        plotter.camera.azimuth = 45
        plotter.camera.elevation = 30

        # Add lighting for better 3D visualization
        light = pv.Light(position=(1, 1, 1), focal_point=(0, 0, 0), intensity=0.5)
        plotter.add_light(light)

        # Add legend
        plotter.add_legend()

        plotter.show()

    elif viz_mode == 'center_trajectories':
        # Visualize only center trajectories for each component
        trunk_points = components['trunk']
        branches = components['branches']

        # Visualize trunk centers
        if len(trunk_points) > 0:
            visualize_component_centers(trunk_points, "TRUNK", color='brown')

        # Visualize branch centers
        branch_colors = ['blue', 'red', 'green', 'orange', 'purple', 'cyan']
        for i, branch_points in enumerate(branches):
            if len(branch_points) > 0:
                color = branch_colors[i % len(branch_colors)]
                visualize_component_centers(branch_points, f"BRANCH {i+1}", color=color)

    else:
        print(f"Visualization mode '{viz_mode}' not implemented. Use 'components_circles' for circle trajectory visualization.")
        return


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
    plotter.add_mesh(trunk_cloud, color='blue', point_size=4, opacity=0.9,
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
        plotter.add_mesh(crown_cloud, color='green', point_size=4, opacity=0.8,
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


def visualize_component_circles(component_points: np.ndarray, component_name: str, color: str = 'blue', step: float = 0.1):
    """
    Visualize a single component with both the original points and center trajectory points.

    Args:
        component_points: Nx3 array of points for this component
        component_name: Name of the component (e.g., "Trunk", "Branch 1")
        color: Color for the points and trajectory
        step: Height step for circle fitting (meters)
    """
    if len(component_points) == 0:
        print(f"No points for {component_name}")
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    # Show component points
    component_cloud = pv.PolyData(component_points)
    plotter.add_mesh(component_cloud, color=color, point_size=4, opacity=0.6,
                    label=f'{component_name} Points ({len(component_points)} pts)', render_points_as_spheres=False)

    # Get height range
    min_z = np.min(component_points[:, 2])
    max_z = np.max(component_points[:, 2])
    height_range = max_z - min_z

    print(f"{component_name}: Z range {min_z:.2f} to {max_z:.2f}m (height: {height_range:.2f}m)")

    # Calculate circle centers (trajectory points)
    circle_centers = []
    circle_radii = []
    current_z = min_z

    while current_z <= max_z:
        # Extract points within thickness around current height
        thickness = 0.1  # 10cm thickness
        height_mask = (component_points[:, 2] >= current_z - thickness/2) & \
                     (component_points[:, 2] <= current_z + thickness/2)
        height_points = component_points[height_mask]

        if len(height_points) >= 3:  # Need at least 3 points for a meaningful circle
            # Calculate bounding circle (same method as middle slice)
            cluster_xy = height_points[:, :2]  # Only X,Y coordinates
            centroid = np.mean(cluster_xy, axis=0)
            distances = np.linalg.norm(cluster_xy - centroid, axis=1)
            radius = np.max(distances)

            # Only include circles within reasonable radius bounds
            if 0.03 <= radius <= 1.0:  # Same bounds as multi_height_circle_fitting.py
                circle_centers.append([centroid[0], centroid[1], current_z])
                circle_radii.append(radius)
                print(f"{component_name}: Added center at Z={current_z:.2f}, center=({centroid[0]:.3f}, {centroid[1]:.3f}), radius={radius:.3f}")

        current_z += step

    # Display the center trajectory points
    if len(circle_centers) > 0:
        centers_array = np.array(circle_centers)
        centers_cloud = pv.PolyData(centers_array)
        
        # Use a lighter/different shade for trajectory points
        trajectory_color = 'white' if color != 'white' else 'yellow'
        plotter.add_mesh(centers_cloud, color=trajectory_color, point_size=10,
                        render_points_as_spheres=True, opacity=1.0,
                        label=f'{component_name} Trajectory ({len(circle_centers)} pts)')

        # Display the circles at each height level
        for i, (center, radius) in enumerate(zip(circle_centers, circle_radii)):
            # Create a circle at this height
            circle = pv.Circle(radius=radius, resolution=32)
            # Translate to the center position
            circle.translate([center[0], center[1], center[2]], inplace=True)
            plotter.add_mesh(circle, color=color, style='wireframe', line_width=2,
                           label=f'{component_name} Circle Z={center[2]:.1f}m (r={radius:.2f}m)')

        # Calculate and display average radius circles at each height
        if len(circle_radii) > 0:
            avg_radius = np.mean(circle_radii)
            for center in circle_centers:
                # Create average circle at this center position
                avg_circle = pv.Circle(radius=float(avg_radius), resolution=32)
                avg_circle.translate([center[0], center[1], center[2]], inplace=True)
                plotter.add_mesh(avg_circle, color='yellow', style='wireframe', line_width=4,
                               label=f'{component_name} Avg Circle Z={center[2]:.1f}m (r={avg_radius:.2f}m)')
            
            print(f"{component_name}: Average radius = {avg_radius:.3f}m (from {len(circle_radii)} circles)")

    # Add bounding box for the component
    bounds = component_cloud.bounds
    bounding_box = pv.Cube(bounds=bounds)
    plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=1,
                    label='Component Bounding Box')

    # Calculate dimensions
    width = bounds[1] - bounds[0]
    length = bounds[3] - bounds[2]
    height = bounds[5] - bounds[4]

    info_text = f"{component_name} Visualization\n"
    info_text += f"Points: {len(component_points)}\n"
    if len(circle_centers) > 0:
        info_text += f"Trajectory points: {len(circle_centers)}\n"
    info_text += f"Height range: {height_range:.2f}m\n"
    info_text += f"Dimensions: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Step size: {step:.1f}m, Thickness: {thickness:.1f}m"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30

    # Add lighting for better 3D visualization
    light = pv.Light(position=(1, 1, 1), focal_point=(0, 0, 0), intensity=0.5)
    plotter.add_light(light)

    # Add legend
    plotter.add_legend()

    plotter.show()


def visualize_component_circles_merged(plotter: pv.Plotter, component_points: np.ndarray, component_name: str, color: str = 'blue', step: float = 0.1):
    """
    Add a single component visualization to an existing plotter.

    Args:
        plotter: Existing PyVista plotter to add to
        component_points: Nx3 array of points for this component
        component_name: Name of the component (e.g., "Trunk", "Branch 1")
        color: Color for the points and trajectory
        step: Height step for circle fitting (meters)
    """
    if len(component_points) == 0:
        print(f"No points for {component_name}")
        return

    # Show component points
    component_cloud = pv.PolyData(component_points)
    plotter.add_mesh(component_cloud, color=color, point_size=4, opacity=0.6,
                    label=f'{component_name} Points ({len(component_points)} pts)', render_points_as_spheres=False)

    # Get height range
    min_z = np.min(component_points[:, 2])
    max_z = np.max(component_points[:, 2])
    height_range = max_z - min_z

    print(f"{component_name}: Z range {min_z:.2f} to {max_z:.2f}m (height: {height_range:.2f}m)")

    # Calculate circle centers (trajectory points)
    circle_centers = []
    circle_radii = []
    current_z = min_z

    while current_z <= max_z:
        # Extract points within thickness around current height
        thickness = 0.1  # 10cm thickness
        height_mask = (component_points[:, 2] >= current_z - thickness/2) & \
                     (component_points[:, 2] <= current_z + thickness/2)
        height_points = component_points[height_mask]

        if len(height_points) >= 3:  # Need at least 3 points for a meaningful circle
            # Calculate bounding circle (same method as middle slice)
            cluster_xy = height_points[:, :2]  # Only X,Y coordinates
            centroid = np.mean(cluster_xy, axis=0)
            distances = np.linalg.norm(cluster_xy - centroid, axis=1)
            radius = np.max(distances)

            # Only include circles within reasonable radius bounds
            if 0.03 <= radius <= 1.0:  # Same bounds as multi_height_circle_fitting.py
                circle_centers.append([centroid[0], centroid[1], current_z])
                circle_radii.append(radius)
                print(f"{component_name}: Added center at Z={current_z:.2f}, center=({centroid[0]:.3f}, {centroid[1]:.3f}), radius={radius:.3f}")

        current_z += step

    # Display the center trajectory points
    if len(circle_centers) > 0:
        centers_array = np.array(circle_centers)
        centers_cloud = pv.PolyData(centers_array)

        # Use a lighter/different shade for trajectory points
        trajectory_color = 'white' if color != 'white' else 'yellow'
        plotter.add_mesh(centers_cloud, color=trajectory_color, point_size=10,
                        render_points_as_spheres=True, opacity=1.0,
                        label=f'{component_name} Trajectory ({len(circle_centers)} pts)')

        # Display the circles at each height level
        for i, (center, radius) in enumerate(zip(circle_centers, circle_radii)):
            # Create a circle at this height
            circle = pv.Circle(radius=radius, resolution=32)
            # Translate to the center position
            circle.translate([center[0], center[1], center[2]], inplace=True)
            plotter.add_mesh(circle, color=color, style='wireframe', line_width=2,
                           label=f'{component_name} Circle Z={center[2]:.1f}m (r={radius:.2f}m)')

        # Calculate and display average radius circles at each height
        if len(circle_radii) > 0:
            avg_radius = np.mean(circle_radii)
            for center in circle_centers:
                # Create average circle at this center position
                avg_circle = pv.Circle(radius=float(avg_radius), resolution=32)
                avg_circle.translate([center[0], center[1], center[2]], inplace=True)
                plotter.add_mesh(avg_circle, color='yellow', style='wireframe', line_width=4,
                               label=f'{component_name} Avg Circle Z={center[2]:.1f}m (r={avg_radius:.2f}m)')
            
            print(f"{component_name}: Average radius = {avg_radius:.3f}m (from {len(circle_radii)} circles)")

def visualize_component_centers(component_points: np.ndarray, component_name: str, color: str = 'blue', step: float = 0.1):
    """
    Visualize only the center trajectory points for a single component.

    Args:
        component_points: Nx3 array of points for this component
        component_name: Name of the component (e.g., "Trunk", "Branch 1")
        color: Color for the trajectory points
        step: Height step for center calculation (meters)
    """
    if len(component_points) == 0:
        print(f"No points for {component_name}")
        return

    plotter = pv.Plotter()
    pv.set_plot_theme("document")

    # Get height range
    min_z = np.min(component_points[:, 2])
    max_z = np.max(component_points[:, 2])
    height_range = max_z - min_z

    print(f"{component_name}: Z range {min_z:.2f} to {max_z:.2f}m (height: {height_range:.2f}m)")

    # Calculate circle centers (trajectory points)
    circle_centers = []
    circle_radii = []
    current_z = min_z

    while current_z <= max_z:
        # Extract points within thickness around current height
        thickness = 0.1  # 10cm thickness
        height_mask = (component_points[:, 2] >= current_z - thickness/2) & \
                     (component_points[:, 2] <= current_z + thickness/2)
        height_points = component_points[height_mask]

        if len(height_points) >= 3:  # Need at least 3 points for a meaningful circle
            # Calculate bounding circle (same method as middle slice)
            cluster_xy = height_points[:, :2]  # Only X,Y coordinates
            centroid = np.mean(cluster_xy, axis=0)
            distances = np.linalg.norm(cluster_xy - centroid, axis=1)
            radius = np.max(distances)

            # Only include circles within reasonable radius bounds
            if 0.03 <= radius <= 1.0:  # Same bounds as multi_height_circle_fitting.py
                circle_centers.append([centroid[0], centroid[1], current_z])
                circle_radii.append(radius)
                print(f"{component_name}: Added center at Z={current_z:.2f}, center=({centroid[0]:.3f}, {centroid[1]:.3f}), radius={radius:.3f}")

        current_z += step

    # Filter out center points that are too far from the main trajectory
    if len(circle_centers) >= 3:
        filtered_centers = []
        filtered_radii = []
        
        # Use first and last points to define the main trajectory
        start_point = np.array(circle_centers[0])
        end_point = np.array(circle_centers[-1])
        
        # Vector along the trajectory
        trajectory_vector = end_point - start_point
        trajectory_length = np.linalg.norm(trajectory_vector)
        
        if trajectory_length > 0:
            # Normalize the trajectory vector
            trajectory_unit = trajectory_vector / trajectory_length
            
            # Distance threshold for filtering (meters)
            distance_threshold = 0.5  # 50cm threshold
            
            for i, center in enumerate(circle_centers):
                center_array = np.array(center)
                
                # Vector from start to current point
                point_vector = center_array - start_point
                
                # Project onto trajectory
                projection_length = np.dot(point_vector, trajectory_unit)
                
                # Clamp projection to trajectory bounds
                projection_length = np.clip(projection_length, 0, trajectory_length)
                
                # Projected point on trajectory
                projected_point = start_point + projection_length * trajectory_unit
                
                # Perpendicular distance from center to trajectory
                distance_to_trajectory = np.linalg.norm(center_array - projected_point)
                
                # Keep point if within threshold
                if distance_to_trajectory <= distance_threshold:
                    filtered_centers.append(center)
                    filtered_radii.append(circle_radii[i])
                    print(f"{component_name}: Kept center at Z={center[2]:.2f}, distance={distance_to_trajectory:.3f}m")
                else:
                    print(f"{component_name}: Filtered out center at Z={center[2]:.2f}, distance={distance_to_trajectory:.3f}m (> {distance_threshold:.1f}m)")
            
            # Update the centers and radii with filtered versions
            circle_centers = filtered_centers
            circle_radii = filtered_radii
            
            print(f"{component_name}: Filtered centers: {len(circle_centers)} remaining")

    # Display the center trajectory points
    if len(circle_centers) > 0:
        centers_array = np.array(circle_centers)
        centers_cloud = pv.PolyData(centers_array)
        
        plotter.add_mesh(centers_cloud, color=color, point_size=12,
                        render_points_as_spheres=True, opacity=1.0,
                        label=f'{component_name} Centers ({len(circle_centers)} pts)')

        # Calculate and display average radius circles at each height
        if len(circle_radii) > 0:
            avg_radius = np.mean(circle_radii)
            for center in circle_centers:
                # Create average circle at this center position
                avg_circle = pv.Circle(radius=float(avg_radius), resolution=32)
                avg_circle.translate([center[0], center[1], center[2]], inplace=True)
                plotter.add_mesh(avg_circle, color='yellow', style='wireframe', line_width=4,
                               label=f'{component_name} Avg Circle Z={center[2]:.1f}m (r={avg_radius:.2f}m)')
            
            print(f"{component_name}: Average radius = {avg_radius:.3f}m (from {len(circle_radii)} circles)")

    # Add bounding box for the component centers
    if len(circle_centers) > 0:
        centers_array = np.array(circle_centers)
        bounds = [
            np.min(centers_array[:, 0]), np.max(centers_array[:, 0]),
            np.min(centers_array[:, 1]), np.max(centers_array[:, 1]),
            np.min(centers_array[:, 2]), np.max(centers_array[:, 2])
        ]
        bounding_box = pv.Cube(bounds=bounds)
        plotter.add_mesh(bounding_box, color='black', style='wireframe', line_width=1,
                        label='Centers Bounding Box')

    # Calculate dimensions
    if len(circle_centers) > 0:
        centers_array = np.array(circle_centers)
        width = np.max(centers_array[:, 0]) - np.min(centers_array[:, 0])
        length = np.max(centers_array[:, 1]) - np.min(centers_array[:, 1])
        height = np.max(centers_array[:, 2]) - np.min(centers_array[:, 2])
    else:
        width = length = height = 0

    info_text = f"{component_name} Center Trajectories\n"
    info_text += f"Trajectory points: {len(circle_centers)}\n"
    info_text += f"Height range: {height_range:.2f}m\n"
    info_text += f"Trajectory span: {width:.2f}m W × {length:.2f}m L × {height:.2f}m H\n"
    info_text += f"Step size: {step:.1f}m, Thickness: {thickness:.1f}m"

    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30

    # Add lighting for better 3D visualization
    light = pv.Light(position=(1, 1, 1), focal_point=(0, 0, 0), intensity=0.5)
    plotter.add_light(light)

    # Add legend
    plotter.add_legend()

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

    # Show ALL crown points (background)
    crown_cloud = pv.PolyData(points_above)
    plotter.add_mesh(crown_cloud, color='green', point_size=3, opacity=0.3,
                    label=f'All Crown Points ({len(points_above)} pts)', render_points_as_spheres=False)

    # Show trunk points below branching height
    trunk_cloud = pv.PolyData(trunk_points)
    plotter.add_mesh(trunk_cloud, color='brown', point_size=4, opacity=0.9,
                    label=f'Trunk ({len(trunk_points)} pts)', render_points_as_spheres=True)

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
                plotter.add_mesh(cluster_cloud, color=color, point_size=4,
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

    # Extend Branch One clusters vertically using connectivity-based approach
    if n_clusters > 0:
        # Build connectivity graph for all crown points
        horizontal_radius = 0.2  # 50cm horizontal connectivity radius
        vertical_radius = 0.5    # 30cm vertical connectivity radius

        print(f"Building connectivity graph with {len(points_above)} crown points...")
        print(f"Connectivity: horizontal={horizontal_radius}m, vertical={vertical_radius}m")
        n_points = len(points_above)

        # Create adjacency matrix for 3D connectivity (horizontal + vertical)
        # Points are connected if within BOTH horizontal AND vertical radius
        rows = []
        cols = []

        for i in range(n_points):
            for j in range(i+1, n_points):
                # Check horizontal distance
                dist_xy = np.sqrt((points_above[i, 0] - points_above[j, 0])**2 +
                                (points_above[i, 1] - points_above[j, 1])**2)
                # Check vertical distance
                dist_z = abs(points_above[i, 2] - points_above[j, 2])
                
                if dist_xy <= horizontal_radius and dist_z <= vertical_radius:
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Create sparse adjacency matrix
        if len(rows) > 0:
            adjacency = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_points, n_points))

            # Find connected components
            n_components, connectivity_labels = connected_components(csgraph=adjacency, directed=False, return_labels=True)

            print(f"Found {n_components} connected components in crown (3D connectivity)")

            # For each cluster (both Branch One and Branch Two)
            for cluster_id in range(n_clusters):
                cluster_mask = labels == cluster_id
                cluster_points = slice_points[cluster_mask]
                color = colors[cluster_id % 2]
                branch_name = "One" if cluster_id % 2 == 0 else "Two"
                
                if len(cluster_points) > 0:
                    # Find which crown points belong to the same connected components as cluster points
                    extended_points = []
                    
                    # Get indices of cluster points in the full crown point array
                    cluster_indices = []
                    for cluster_point in cluster_points:
                        # Find this point in the full crown array
                        diffs = points_above - cluster_point
                        distances = np.linalg.norm(diffs, axis=1)
                        idx = np.argmin(distances)
                        if distances[idx] < 0.01:  # Very close match
                            cluster_indices.append(idx)
                    
                    if len(cluster_indices) > 0:
                        # Get the component labels for these cluster points
                        cluster_component_labels = set(connectivity_labels[idx] for idx in cluster_indices)
                        
                        # Find all points in the same connected components
                        for comp_label in cluster_component_labels:
                            component_mask = connectivity_labels == comp_label
                            component_points = points_above[component_mask]
                            extended_points.extend(component_points)
                    
                    if len(extended_points) > 0:
                        extended_array = np.array(extended_points)
                        extended_cloud = pv.PolyData(extended_array)
                        
                        # Use different colors for extended branches (orange and purple)
                        extended_colors = ['orange', 'purple']
                        extended_color = extended_colors[cluster_id % 2]
                        
                        plotter.add_mesh(extended_cloud, color=extended_color, point_size=4, opacity=0.8,
                                       label=f'Branch {branch_name} Extended ({len(extended_array)} pts)',
                                       render_points_as_spheres=True)    # Add middle slice plane
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


def save_components_to_las(components: dict, output_prefix: str, original_las_path: Optional[str] = None):
    """
    Save extracted components to a single LAS file with tree_trunk_comp scalar field.

    Args:
        components: Dictionary with trunk, branches, and unassigned points
        output_prefix: Prefix for output filename
        original_las_path: Path to original LAS file to copy header information
    """
    # Load original LAS file to get header information if provided
    header = None
    if original_las_path and os.path.exists(original_las_path):
        original_las = laspy.read(original_las_path)
        header = laspy.LasHeader(point_format=original_las.point_format, version=original_las.header.version)
        # Add tree_trunk_comp field
        header.add_extra_dim(laspy.ExtraBytesParams(name="tree_trunk_comp", type=np.uint8))
    else:
        # Create default header
        header = laspy.LasHeader(point_format=3, version="1.2")
        header.add_extra_dim(laspy.ExtraBytesParams(name="tree_trunk_comp", type=np.uint8))

    # Collect all points and their component labels
    all_points = []
    all_labels = []

    # Add trunk points (label 0)
    if len(components['trunk']) > 0:
        trunk_points = components['trunk']
        all_points.append(trunk_points)
        all_labels.append(np.zeros(len(trunk_points), dtype=np.uint8))

    # Add branch points (labels 1, 2, 3, etc.)
    for i, branch in enumerate(components['branches']):
        if len(branch) > 0:
            branch_points = branch
            all_points.append(branch_points)
            all_labels.append(np.full(len(branch_points), i + 1, dtype=np.uint8))

    # Add unassigned points (label 255 for unassigned)
    if len(components['unassigned']) > 0:
        unassigned_points = components['unassigned']
        all_points.append(unassigned_points)
        all_labels.append(np.full(len(unassigned_points), 255, dtype=np.uint8))

    # Combine all points and labels
    if len(all_points) > 0:
        combined_points = np.vstack(all_points)
        combined_labels = np.concatenate(all_labels)

        # Create LAS file
        las_combined = laspy.LasData(header)
        las_combined.x = combined_points[:, 0]
        las_combined.y = combined_points[:, 1]
        las_combined.z = combined_points[:, 2]
        las_combined.tree_trunk_comp = combined_labels

        output_filename = f"{output_prefix}_components.las"
        las_combined.write(output_filename)

        # Print summary
        print(f"Saved all components to {output_filename}")
        print(f"Total points: {len(combined_points)}")
        if len(components['trunk']) > 0:
            print(f"  Trunk (label 0): {len(components['trunk'])} points")
        for i, branch in enumerate(components['branches']):
            if len(branch) > 0:
                print(f"  Branch {i+1} (label {i+1}): {len(branch)} points")
        if len(components['unassigned']) > 0:
            print(f"  Unassigned (label 255): {len(components['unassigned'])} points")


def main():
    parser = argparse.ArgumentParser(description='Extract and visualize tree components (trunk and branches) - Connectivity-based approach')
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
    parser.add_argument('--viz-mode', choices=['full', 'trunk', 'crown', 'middle_slice', 'sequence', 'components_circles', 'center_trajectories'],
                       default='sequence', help='Visualization mode: full tree, trunk only, crown only, middle slice, sequence, components with circles, or center trajectories only')
    parser.add_argument('--output', '-o', help='Output prefix for LAS file with tree_trunk_comp scalar field')

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

        # Save to LAS if requested
        if args.output:
            save_components_to_las(components, args.output, args.input)

        # Visualize if requested
        if args.visualize:
            centroids = components.get('centroids', [])
            visualize_components(components, args.branching_height, centroids, all_points, args.viz_mode)

        # Print final component summary report
        print("\n" + "="*50)
        print("TREE COMPONENT ANALYSIS REPORT")
        print("="*50)
        print(f"Total stem points analyzed: {len(all_points)}")
        print()

        # Trunk points (under the split)
        trunk_points = components['trunk']
        print(f"Points under the split (trunk): {len(trunk_points)}")

        # Branch points
        branches = components['branches']
        total_branch_points = 0
        for i, branch in enumerate(branches):
            branch_points = len(branch)
            total_branch_points += branch_points
            print(f"Branch {i+1} points: {branch_points}")

        # Unassigned points (neither trunk nor branches)
        unassigned_points = components['unassigned']
        print(f"Unassigned points (neither trunk nor branches): {len(unassigned_points)}")
        print()

        # Verification
        total_accounted = len(trunk_points) + total_branch_points + len(unassigned_points)
        print(f"Verification - Total accounted points: {total_accounted}")
        if total_accounted == len(all_points):
            print("✓ All points properly categorized")
        else:
            print("⚠ Point count mismatch - some points may be missing")
        print("="*50)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
