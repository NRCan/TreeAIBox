#!/usr/bin/env python3
"""
Generate and display circles fitted to stem cross-sections at multiple heights
using RANSAC circle fitting.
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os
import subprocess
import sys
from typing import List, Tuple, Optional
from scipy.optimize import least_squares
from sklearn.linear_model import RANSACRegressor


class CircleFitter:
    """Robust circle fitting using RANSAC."""

    def fit_circle_ransac(self, points: np.ndarray) -> Tuple[float, float, float]:
        """
        Fit a circle to 2D points using RANSAC.

        Args:
            points: Nx2 array of (x, y) coordinates

        Returns:
            Tuple of (center_x, center_y, radius)
        """
        # Center points to avoid numerical issues with large coordinates
        centroid = np.mean(points, axis=0)
        points_centered = points - centroid

        def circle_model(points_subset):
            """Fit circle to a subset of points."""
            if len(points_subset) < 3:
                return np.array([0, 0, 1])  # Default circle

            # Use algebraic method for subset
            return np.array(self._fit_circle_algebraic(points_subset))

        def circle_distance(circle_params, point):
            """Distance from point to circle."""
            cx, cy, r = circle_params
            return abs(np.sqrt((point[0] - cx)**2 + (point[1] - cy)**2) - r)

        # RANSAC parameters
        min_samples = 3
        residual_threshold = 0.05  # 5cm threshold
        max_trials = 100

        best_circle = None
        best_inliers = []

        for _ in range(max_trials):
            # Random sample
            indices = np.random.choice(len(points_centered), min_samples, replace=False)
            sample_points = points_centered[indices]

            try:
                circle_params = circle_model(sample_points)

                # Count inliers
                distances = np.array([circle_distance(circle_params, pt) for pt in points_centered])
                inliers = distances < residual_threshold
                num_inliers = np.sum(inliers)

                if num_inliers > len(best_inliers):
                    best_inliers = inliers
                    best_circle = circle_params

            except:
                continue

        if best_circle is None:
            # Fallback to algebraic method
            cx_centered, cy_centered, radius = self._fit_circle_algebraic(points_centered)
        else:
            # Refine with all inliers
            inlier_points = points_centered[best_inliers]
            if len(inlier_points) >= 3:
                cx_centered, cy_centered, radius = self._fit_circle_algebraic(inlier_points)
            else:
                cx_centered, cy_centered, radius = best_circle

        # Transform back to original coordinate system
        cx = cx_centered + centroid[0]
        cy = cy_centered + centroid[1]

        return cx, cy, radius

    def _fit_circle_algebraic(self, points: np.ndarray) -> Tuple[float, float, float]:
        """Algebraic circle fitting using least squares."""
        # Center points to avoid numerical issues
        centroid = np.mean(points, axis=0)
        points_centered = points - centroid

        # Set up the design matrix
        A = np.column_stack([
            2 * points_centered[:, 0],
            2 * points_centered[:, 1],
            np.ones(len(points))
        ])

        b = points_centered[:, 0]**2 + points_centered[:, 1]**2

        # Solve for parameters
        params = np.linalg.lstsq(A, b, rcond=None)[0]

        # Extract circle parameters in centered coordinates
        a, b_param, c = params
        cx_centered = a
        cy_centered = b_param
        radius = np.sqrt(c + cx_centered**2 + cy_centered**2)

        # Transform back to original coordinate system
        cx = cx_centered + centroid[0]
        cy = cy_centered + centroid[1]

        return cx, cy, radius


def fit_circle_to_points(points_2d: np.ndarray, method: str = 'ransac') -> Tuple[float, float, float]:
    """
    Fit a circle to 2D points using different methods.

    Args:
        points_2d: Nx2 array of (x, y) coordinates
        method: 'ransac' for robust fitting or 'algebraic' for fitting all points

    Returns:
        Tuple of (center_x, center_y, radius)
    """
    if method == 'ransac':
        fitter = CircleFitter()
        return fitter.fit_circle_ransac(points_2d)
    elif method == 'algebraic':
        fitter = CircleFitter()
        return fitter._fit_circle_algebraic(points_2d)
    else:
        raise ValueError(f"Unknown method: {method}")


def create_circle_mesh(cx: float, cy: float, cz: float, radius: float, n_points: int = 50) -> pv.PolyData:
    """
    Create a PyVista mesh for a circle.

    Args:
        cx, cy, cz: Circle center coordinates
        radius: Circle radius
        n_points: Number of points to create the circle

    Returns:
        PyVista PolyData object representing the circle
    """
    theta = np.linspace(0, 2*np.pi, n_points)
    x_circle = cx + radius * np.cos(theta)
    y_circle = cy + radius * np.sin(theta)
    z_circle = np.full_like(theta, cz)

    circle_points = np.column_stack([x_circle, y_circle, z_circle])
    circle_mesh = pv.PolyData(circle_points)
    lines = circle_mesh.lines = np.column_stack([
        np.full(n_points, 2, dtype=np.int32),
        np.arange(n_points), np.roll(np.arange(n_points), -1)
    ])

    return circle_mesh


def load_stem_points(las_path: str, component_label: Optional[int] = None, z_threshold: Optional[float] = None):
    """
    Load stem points from LAS file, optionally filtering by component label.

    Args:
        las_path: Path to LAS file
        component_label: If specified, filter by tree_trunk_comp field (0=trunk, 1+=branches, 255=unassigned)
        z_threshold: Optional height threshold to filter points

    Returns:
        Nx3 array of points
    """
    print(f"Loading LAS file: {las_path}")

    las = laspy.read(las_path)

    # Check for stem classification - skip if we have component filtering
    if component_label is not None and 'tree_trunk_comp' in las.point_format.dimension_names:
        # When filtering by component, use all points (component filtering will handle classification)
        stem_mask = np.ones(len(las.points), dtype=bool)
        print(f"Using component filtering - processing all {len(las.points)} points")
    elif 'stemcls' not in las.point_format.dimension_names:
        print("Warning: No 'stemcls' field found. Using all points.")
        stem_mask = np.ones(len(las.points), dtype=bool)
    else:
        stemcls = las['stemcls']
        stem_mask = stemcls == 2
        print(f"Found {np.sum(stem_mask)} stem points out of {len(las.points)} total points")

    # Apply component filtering if specified
    if component_label is not None:
        if 'tree_trunk_comp' not in las.point_format.dimension_names:
            print(f"Warning: No 'tree_trunk_comp' field found. Cannot filter by component {component_label}.")
        else:
            comp_labels = las['tree_trunk_comp']
            comp_mask = comp_labels == component_label
            combined_mask = stem_mask & comp_mask
            print(f"Filtered to {np.sum(combined_mask)} points with component label {component_label}")
            stem_mask = combined_mask

    # Extract coordinates
    points = np.column_stack([
        np.array(las.x)[stem_mask],
        np.array(las.y)[stem_mask],
        np.array(las.z)[stem_mask]
    ])

    # Apply height filter if specified
    if z_threshold is not None:
        height_mask = points[:, 2] <= z_threshold
        points = points[height_mask]
        print(f"Filtered to {len(points)} points below {z_threshold}m height")

    print(f"Loaded {len(points)} points")
    print(f"Z range: {np.min(points[:, 2]):.2f} to {np.max(points[:, 2]):.2f}m")

    return points


def extract_plane_cut(points: np.ndarray, height_from_bottom: float, thickness: float = 0.1):
    """
    Extract points within a horizontal plane cut at specified height from bottom.

    Args:
        points: Nx3 array of stem points
        height_from_bottom: Height from the bottom of the tree (in meters)
        thickness: Thickness of the plane cut (in meters)

    Returns:
        Nx3 array of points within the plane cut
    """
    min_z = np.min(points[:, 2])
    max_z = np.max(points[:, 2])

    # Calculate the target height
    target_z = min_z + height_from_bottom

    # Extract points within the thickness range
    lower_bound = target_z - thickness/2
    upper_bound = target_z + thickness/2

    mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
    plane_points = points[mask]

    print(f"Plane cut at {height_from_bottom:.1f}m from bottom (Z: {target_z:.2f}m)")
    print(f"Extracted {len(plane_points)} points from Z range [{lower_bound:.2f}, {upper_bound:.2f}]m")
    print(f"Tree height range: {min_z:.2f} to {max_z:.2f}m")

    return plane_points, target_z


def visualize_multiple_circles(points: np.ndarray, height_results: List[Tuple[float, np.ndarray, float]], thickness: float, use_average_radius: bool = True, min_radius: float = 0.03, max_radius: float = 1.0):
    """
    Visualize multiple fitted circles at different heights.

    Args:
        points: All stem points
        height_results: List of (height, plane_points, target_z) tuples
        thickness: Thickness used for plane cuts
        use_average_radius: Whether to use average radius for all circles
    """
    print(f"Visualizing {len(height_results)} height levels")

    # First pass: fit circles and collect results
    circle_fits = []
    valid_heights = []

    for height, plane_points, target_z in height_results:
        if len(plane_points) >= 3:
            points_2d = plane_points[:, :2]
            try:
                cx, cy, radius = fit_circle_to_points(points_2d, method='ransac')
                # Skip radii outside reasonable bounds
                if radius < min_radius or radius > max_radius:
                    print(f"Warning: Skipping height {height:.1f}m due to radius {radius:.3f}m outside [{min_radius}, {max_radius}]m")
                    continue
                circle_fits.append((height, cx, cy, radius, target_z, plane_points))
                valid_heights.append(height)
                print(f"Height {height:.1f}m: center=({cx:.2f}, {cy:.2f}), radius={radius:.3f}m")
            except Exception as e:
                print(f"Circle fitting failed at {height:.1f}m: {e}")

    if not circle_fits:
        print("No valid circle fits found!")
        return

    # Find the section with the most points (most reliable centroid)
    max_points_section = max(circle_fits, key=lambda x: len(x[5]))  # x[5] is plane_points
    reference_centroid = np.array([max_points_section[1], max_points_section[2]])  # cx, cy
    max_points = len(max_points_section[5])
    reference_height = max_points_section[0]

    print(f"\nReference centroid from height {reference_height:.1f}m ({max_points} points): ({reference_centroid[0]:.2f}, {reference_centroid[1]:.2f})")

    # Calculate average radius for distance threshold
    radii = [fit[3] for fit in circle_fits if fit[3] <= 1.0]  # Filter large radii
    avg_radius = np.mean(radii) if radii else 0.2  # Default fallback
    max_centroid_distance = 0.2 * avg_radius  # 20% of average radius

    print(f"Average radius: {avg_radius:.3f}m, Max centroid distance allowed: {max_centroid_distance:.3f}m")

    # Adjust centroids to be within 20% of reference
    adjusted_circle_fits = []
    for fit in circle_fits:
        height, cx, cy, radius, target_z, plane_points = fit
        current_centroid = np.array([cx, cy])

        # Calculate distance from reference centroid
        distance = np.linalg.norm(current_centroid - reference_centroid)

        if distance > max_centroid_distance:
            # Move centroid closer to reference (within the allowed distance)
            direction = current_centroid - reference_centroid
            if np.linalg.norm(direction) > 0:
                direction_normalized = direction / np.linalg.norm(direction)
                new_centroid = reference_centroid + direction_normalized * max_centroid_distance
                cx, cy = new_centroid[0], new_centroid[1]
                print(f"Adjusted centroid at {height:.1f}m: moved from ({current_centroid[0]:.2f}, {current_centroid[1]:.2f}) to ({cx:.2f}, {cy:.2f}) [distance was {distance:.3f}m]")

        adjusted_circle_fits.append((height, cx, cy, radius, target_z, plane_points))

    circle_fits = adjusted_circle_fits

    # Calculate average radius if requested
    if use_average_radius and len(circle_fits) > 0:
        radii = [fit[3] for fit in circle_fits]  # radius is at index 3

        # Filter radii using provided bounds
        filtered_radii = [r for r in radii if (r >= min_radius and r <= max_radius)]

        if len(filtered_radii) == 0:
            print("Warning: No radii within bounds, using individual radii instead")
            avg_radius = None
        else:
            avg_radius = np.mean(filtered_radii)
            print(f"\nUsing average radius: {avg_radius:.3f}m (from {len(filtered_radii)} circles, filtered out {len(circle_fits) - len(filtered_radii)} circles)")
            print(f"Radius range: {min(filtered_radii):.3f}m to {max(filtered_radii):.3f}m")
    else:
        avg_radius = None

    # Create PyVista point clouds
    all_points_cloud = pv.PolyData(points)

    # Create plotter
    plotter = pv.Plotter()

    # Add all points (dimmed)
    plotter.add_mesh(all_points_cloud, color='lightgray', point_size=2, opacity=0.3, label='All Stem Points')

    # Colors for different heights
    colors = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown', 'gray', 'cyan', 'magenta']

    circle_meshes = []
    info_lines = []

    for i, (height, cx, cy, original_radius, target_z, plane_points) in enumerate(circle_fits):
        color = colors[i % len(colors)]

        # Filter out unreasonably large radii
        max_reasonable_radius = 1.0  # 1 meter max for tree trunks
        if original_radius > max_reasonable_radius:
            print(f"Warning: Skipping height {height:.1f}m due to unreasonably large radius ({original_radius:.3f}m)")
            continue

        # Use average radius if requested, otherwise use original
        radius = avg_radius if avg_radius is not None else original_radius

        # Create circle mesh with the chosen radius
        circle_mesh = create_circle_mesh(cx, cy, target_z, float(radius))
        circle_meshes.append(circle_mesh)

        # Add to plotter
        radius_label = f"r={radius:.3f}m" if avg_radius else f"r={original_radius:.3f}m"
        plotter.add_mesh(circle_mesh, color=color, line_width=3,
                       label=f'Circle at {height:.1f}m ({radius_label})')

        # Add circle center
        center_point = pv.PolyData([[cx, cy, target_z]])
        plotter.add_mesh(center_point, color=color, point_size=8,
                       label=f'Center at {height:.1f}m')

        # Add plane cut points
        plane_points_cloud = pv.PolyData(plane_points)
        plotter.add_mesh(plane_points_cloud, color=color, point_size=6,
                       label=f'Points at {height:.1f}m')

        info_lines.append(f"{height:.1f}m: {len(plane_points)} pts, {radius_label}")

    # Add reference plane at the middle height
    if circle_fits:
        mid_target_z = circle_fits[len(circle_fits)//2][4]  # target_z of middle result
        center = [(np.min(points[:, 0]) + np.max(points[:, 0]))/2,
                  (np.min(points[:, 1]) + np.max(points[:, 1]))/2,
                  mid_target_z]
        plane_size = max(np.max(points[:, 0]) - np.min(points[:, 0]),
                         np.max(points[:, 1]) - np.min(points[:, 1])) * 1.2
        plane_surface = pv.Plane(center=center, i_size=plane_size, j_size=plane_size)
        plotter.add_mesh(plane_surface, color='lightblue', opacity=0.1, label='Reference Plane')

    # Add comprehensive info text
    mode_text = "Average Radius Mode" if avg_radius else "Individual Radii Mode"
    info_text = f"Stem Cross-Sections (RANSAC fitting)\n{mode_text} - Centroids Adjusted\n" + "\n".join(info_lines)
    if avg_radius:
        info_text += f"\n\nAverage radius: {avg_radius:.3f}m"
    info_text += f"\nReference centroid: height {reference_height:.1f}m ({max_points} pts)"
    plotter.add_text(info_text, position='upper_left', font_size=10, color='black')

    # Set up the camera for a good view
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30

    # Show the plot
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description='Generate circles at multiple heights using RANSAC')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--component', '-c', type=int, choices=[0, 1, 2, 3, 4, 5, 255],
                       help='Component label to filter by (0=trunk, 1-5=branches, 255=unassigned)')
    parser.add_argument('--thickness', '-t', type=float, default=0.1,
                       help='Thickness of plane cut (meters)')
    parser.add_argument('--max_height', type=float, default=1.0,
                       help='Maximum height from bottom (meters)')
    parser.add_argument('--step', type=float, default=0.1,
                       help='Height increment (meters)')
    parser.add_argument('--average_radius', action='store_true',
                       help='Use average radius for all circles instead of individual radii')
    parser.add_argument('--min-radius', type=float, default=0.03,
                       help='Minimum reasonable radius to accept (meters)')
    parser.add_argument('--max-radius', type=float, default=1.0,
                       help='Maximum reasonable radius to accept (meters)')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return

    try:
        # Load stem points, optionally filtered by component
        all_points = load_stem_points(args.input, args.component)

        if len(all_points) == 0:
            print("No points to process!")
            return

        # Generate heights from 0 to max_height in steps
        heights = np.arange(0, args.max_height + args.step, args.step)
        print(f"Processing {len(heights)} height levels: {list(heights)}")

        height_results = []

        for height in heights:
            try:
                plane_points, target_z = extract_plane_cut(all_points, height, args.thickness)
                height_results.append((height, plane_points, target_z))
            except Exception as e:
                print(f"Error processing height {height}: {e}")
                continue

        if not height_results:
            print("No valid height cuts found!")
            return

        # Visualize all circles together
        visualize_multiple_circles(all_points, height_results, args.thickness, args.average_radius, min_radius=args.min_radius, max_radius=args.max_radius)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
