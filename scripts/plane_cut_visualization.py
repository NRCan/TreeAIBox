#!/usr/bin/env python3
"""
Extract and display points from a horizontal plane cut at a specified height from the bottom
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os
from typing import Optional, Tuple
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


def load_stem_points(las_path: str, z_threshold: Optional[float] = None):
    """
    Load stem points from LAS file.

    Args:
        las_path: Path to LAS file
        z_threshold: Optional height threshold to filter all points

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


def visualize_plane_cut(points: np.ndarray, plane_points: np.ndarray, target_z: float, method: str = 'ransac'):
    """
    Visualize the plane cut points and fit a circle to them.

    Args:
        points: All stem points
        plane_points: Points in the plane cut
        target_z: Z-height of the plane cut
        method: Circle fitting method ('ransac' or 'algebraic')
    """
    print(f"Visualizing plane cut with {len(plane_points)} points at Z = {target_z:.2f}m")

    # Fit circle to plane points (projected to XY plane)
    if len(plane_points) >= 3:
        points_2d = plane_points[:, :2]  # Extract X, Y coordinates
        try:
            cx, cy, radius = fit_circle_to_points(points_2d, method=method)
            print(f"Fitted circle ({method}): center=({cx:.2f}, {cy:.2f}), radius={radius:.3f}m")

            # Create circle mesh
            circle_mesh = create_circle_mesh(cx, cy, target_z, radius)
        except Exception as e:
            print(f"Circle fitting failed: {e}")
            circle_mesh = None
    else:
        print("Not enough points for circle fitting (need at least 3)")
        circle_mesh = None

    # Create PyVista point clouds
    all_points_cloud = pv.PolyData(points)
    plane_points_cloud = pv.PolyData(plane_points)

    # Create a plane surface at the cut height for reference
    center = [(np.min(points[:, 0]) + np.max(points[:, 0]))/2,
              (np.min(points[:, 1]) + np.max(points[:, 1]))/2,
              target_z]
    plane_size = max(np.max(points[:, 0]) - np.min(points[:, 0]),
                     np.max(points[:, 1]) - np.min(points[:, 1])) * 1.2
    plane_surface = pv.Plane(center=center, i_size=plane_size, j_size=plane_size)

    # Create plotter
    plotter = pv.Plotter()

    # Add all points (dimmed)
    plotter.add_mesh(all_points_cloud, color='lightgray', point_size=2, opacity=0.3, label='All Stem Points')

    # Add plane cut points (highlighted)
    plotter.add_mesh(plane_points_cloud, color='red', point_size=8, label='Plane Cut Points')

    # Add reference plane
    plotter.add_mesh(plane_surface, color='blue', opacity=0.1, label='Cut Plane')

    # Add fitted circle
    if circle_mesh is not None:
        plotter.add_mesh(circle_mesh, color='green', line_width=3, label='Fitted Circle')

        # Add circle center point
        center_point = pv.PolyData([[cx, cy, target_z]])
        plotter.add_mesh(center_point, color='green', point_size=10, label='Circle Center')

    # Add text
    info_text = f"Plane cut at {target_z:.2f}m\n{len(plane_points)} points"
    if circle_mesh is not None:
        info_text += f"\nRadius: {radius:.3f}m"
    plotter.add_text(info_text, position='upper_left', font_size=12, color='black')

    # Show the plot
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description='Extract and display points from a horizontal plane cut')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--height', type=float, default=3.0,
                       help='Height from bottom for plane cut (meters)')
    parser.add_argument('--thickness', '-t', type=float, default=0.1,
                       help='Thickness of plane cut (meters)')
    parser.add_argument('--method', '-m', choices=['ransac', 'algebraic'], default='ransac',
                       help='Circle fitting method: ransac (robust) or algebraic (fits all points)')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return

    try:
        # Load all stem points
        all_points = load_stem_points(args.input)

        if len(all_points) == 0:
            print("No points to process!")
            return

        # Extract plane cut
        plane_points, target_z = extract_plane_cut(all_points, args.height, args.thickness)

        if len(plane_points) == 0:
            print(f"No points found in plane cut at {args.height}m from bottom!")
            return

        # Visualize
        visualize_plane_cut(all_points, plane_points, target_z, method=args.method)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
