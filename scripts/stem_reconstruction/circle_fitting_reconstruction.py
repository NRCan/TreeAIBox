#!/usr/bin/env python3
"""
Tree Stem Circle Fitting and Visualization Script for TreeAIBox

This script loads extracted stem points from LAS files processed by TreeAIBox,
fits circles to reconstruct the tree shape starting from the bottom, and
visualizes the results using PyVista.

Usage:
    python circle_fitting_reconstruction.py --input path/to/stem_points.las --visualize

Dependencies:
    - numpy
    - scipy
    - scikit-learn
    - laspy[lazrs]
    - pyvista
    - pandas
"""

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from sklearn.linear_model import RANSACRegressor
import pyvista as pv
import matplotlib.pyplot as plt
import argparse
import os
import sys
from typing import Tuple, List, Optional


class CircleFitter:
    """Robust circle fitting using algebraic and geometric methods."""

    def __init__(self):
        self.methods = {
            'algebraic': self._fit_circle_algebraic,
            'geometric': self._fit_circle_geometric,
            'ransac': self._fit_circle_ransac
        }

    def fit_circle(self, points: np.ndarray, method: str = 'ransac') -> Tuple[float, float, float]:
        """
        Fit a circle to 2D points.

        Args:
            points: Nx2 array of (x, y) coordinates
            method: Fitting method ('algebraic', 'geometric', 'ransac')

        Returns:
            Tuple of (center_x, center_y, radius)
        """
        if method not in self.methods:
            raise ValueError(f"Unknown method: {method}")

        return self.methods[method](points)

    def _fit_circle_algebraic(self, points: np.ndarray) -> Tuple[float, float, float]:
        """Algebraic circle fitting using least squares."""
        # Normalize points
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

        # Extract circle parameters
        a, b_param, c = params
        center_x = a + centroid[0]
        center_y = b_param + centroid[1]
        radius = np.sqrt(c + center_x**2 + center_y**2)

        return center_x, center_y, radius

    def _fit_circle_geometric(self, points: np.ndarray) -> Tuple[float, float, float]:
        """Geometric circle fitting using nonlinear least squares."""

        def circle_residuals(params, points):
            cx, cy, r = params
            distances = np.sqrt((points[:, 0] - cx)**2 + (points[:, 1] - cy)**2)
            return distances - r

        # Initial guess: centroid and average distance to centroid
        cx_init = np.mean(points[:, 0])
        cy_init = np.mean(points[:, 1])
        r_init = np.mean(np.sqrt((points[:, 0] - cx_init)**2 + (points[:, 1] - cy_init)**2))

        result = least_squares(circle_residuals, [cx_init, cy_init, r_init], args=(points,))

        return tuple(result.x)

    def _fit_circle_ransac(self, points: np.ndarray) -> Tuple[float, float, float]:
        """Robust circle fitting using RANSAC."""

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
            indices = np.random.choice(len(points), min_samples, replace=False)
            sample_points = points[indices]

            try:
                circle_params = circle_model(sample_points)

                # Count inliers
                distances = np.array([circle_distance(circle_params, point) for point in points])
                inliers = distances < residual_threshold
                num_inliers = np.sum(inliers)

                if num_inliers > len(best_inliers):
                    best_inliers = inliers
                    best_circle = circle_params

            except:
                continue

        if best_circle is None:
            # Fallback to algebraic method
            return self._fit_circle_algebraic(points)

        # Refine with all inliers
        inlier_points = points[best_inliers]
        if len(inlier_points) >= 3:
            return self._fit_circle_algebraic(inlier_points)
        else:
            return tuple(best_circle)


class TreeReconstructor:
    """Tree shape reconstruction from stem points using circle fitting."""

    def __init__(self, segment_height: float = 0.1, min_points_per_segment: int = 5):
        self.segment_height = segment_height
        self.min_points_per_segment = min_points_per_segment
        self.circle_fitter = CircleFitter()

    def load_stem_points(self, file_path: str) -> np.ndarray:
        """
        Load stem points from LAS file processed by TreeAIBox.

        Args:
            file_path: Path to LAS/LAZ file with stem classification

        Returns:
            Nx3 array of stem points (x, y, z)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            import laspy
        except ImportError:
            raise ImportError("laspy required for LAS/LAZ files. Install with: pip install laspy[lazrs]")

        # Load LAS file
        las = laspy.read(file_path)

        # Check for stem classification
        if 'stemcls' not in las.point_format.dimension_names:
            print("Warning: No 'stemcls' field found. Using all points.")
            stem_mask = np.ones(len(las.points), dtype=bool)
        else:
            stemcls = las['stemcls']
            # In TreeAIBox, stem points have stemcls == 2
            stem_mask = stemcls == 2
            print(f"Found {np.sum(stem_mask)} stem points out of {len(las.points)} total points")

        if np.sum(stem_mask) == 0:
            raise ValueError("No stem points found in the file. Check stem classification.")

        # Extract coordinates
        points = np.column_stack([
            np.array(las.x)[stem_mask],
            np.array(las.y)[stem_mask],
            np.array(las.z)[stem_mask]
        ])

        print(f"Loaded {len(points)} stem points from {file_path}")
        return points

    def sort_points_by_height(self, points: np.ndarray) -> np.ndarray:
        """Sort points from bottom to top (increasing z)."""
        sorted_indices = np.argsort(points[:, 2])
        return points[sorted_indices]

    def segment_stem(self, points: np.ndarray) -> List[np.ndarray]:
        """
        Divide stem into height-based segments.

        Args:
            points: Sorted stem points (Nx3)

        Returns:
            List of point arrays for each segment
        """
        if len(points) == 0:
            return []

        z_min, z_max = points[0, 2], points[-1, 2]
        segments = []

        current_z = z_min
        while current_z < z_max:
            next_z = current_z + self.segment_height

            # Find points in this segment
            mask = (points[:, 2] >= current_z) & (points[:, 2] < next_z)
            segment_points = points[mask]

            if len(segment_points) >= self.min_points_per_segment:
                segments.append(segment_points)

            current_z = next_z

        print(f"Created {len(segments)} stem segments")
        return segments

    def fit_circles_to_segments(self, segments: List[np.ndarray],
                               method: str = 'ransac') -> List[Tuple[float, float, float, float]]:
        """
        Fit circles to each stem segment.

        Args:
            segments: List of point arrays
            method: Circle fitting method

        Returns:
            List of (center_x, center_y, z_height, radius) tuples
        """
        circles = []

        for i, segment in enumerate(segments):
            try:
                # Project to horizontal plane (x, y)
                segment_2d = segment[:, :2]

                # Fit circle
                cx, cy, r = self.circle_fitter.fit_circle(segment_2d, method=method)

                # Use segment centroid as circle center (following TreeAIBox approach)
                center_x = np.mean(segment[:, 0])
                center_y = np.mean(segment[:, 1])
                z_height = np.mean(segment[:, 2])  # Use mean instead of median

                circles.append((center_x, center_y, z_height, r))

                if (i + 1) % 10 == 0:
                    print(f"Fitted circles to {i+1}/{len(segments)} segments")

            except Exception as e:
                print(f"Warning: Failed to fit circle to segment {i}: {e}")
                continue

        print(f"Successfully fitted {len(circles)} circles")
        return circles

    def create_visualization(self, stem_points: np.ndarray, circles: List[Tuple[float, float, float, float]],
                           output_path: Optional[str] = None):
        """
        Create 3D visualization of stem points and fitted circles.

        Args:
            stem_points: Original stem points
            circles: List of fitted circles
            output_path: Optional path to save visualization
        """
        # Create PyVista plotter
        plotter = pv.Plotter()

        # Add stem points
        point_cloud = pv.PolyData(stem_points)
        plotter.add_mesh(point_cloud, color='brown', point_size=3, label='Stem Points')

        # Add fitted circles
        for i, (cx, cy, z, r) in enumerate(circles):
            # Create circle geometry
            theta = np.linspace(0, 2*np.pi, 50)
            x_circle = cx + r * np.cos(theta)
            y_circle = cy + r * np.sin(theta)
            z_circle = np.full_like(theta, z)

            circle_points = np.column_stack([x_circle, y_circle, z_circle])
            circle_mesh = pv.PolyData(circle_points)
            lines = circle_mesh.lines = np.column_stack([
                np.full(50, 2, dtype=np.int32),  # number of points per line
                np.arange(50), np.roll(np.arange(50), -1)
            ])

            # Color based on height
            if len(circles) > 1:
                color_value = (z - circles[0][2]) / (circles[-1][2] - circles[0][2])
                color = plt.colormaps['viridis'](color_value)[:3]
            else:
                color = 'blue'

            plotter.add_mesh(circle_mesh, color=color, line_width=3)

        # Add center points of circles
        if circles:
            centers = np.array([[cx, cy, z] for cx, cy, z, r in circles])
            centers_cloud = pv.PolyData(centers)
            plotter.add_mesh(centers_cloud, color='red', point_size=5, label='Circle Centers')

        # Set up the scene
        # plotter.set_background('white')

        if output_path:
            # Create off-screen plotter for screenshot
            off_screen_plotter = pv.Plotter(off_screen=True)
            # Add the same meshes to off-screen plotter
            off_screen_plotter.add_mesh(point_cloud, color='brown', point_size=3)
            for i, (cx, cy, z, r) in enumerate(circles):
                theta = np.linspace(0, 2*np.pi, 50)
                x_circle = cx + r * np.cos(theta)
                y_circle = cy + r * np.sin(theta)
                z_circle = np.full_like(theta, z)
                circle_points = np.column_stack([x_circle, y_circle, z_circle])
                circle_mesh = pv.PolyData(circle_points)
                lines = circle_mesh.lines = np.column_stack([
                    np.full(50, 2, dtype=np.int32),
                    np.arange(50), np.roll(np.arange(50), -1)
                ])
                if len(circles) > 1:
                    color_value = (z - circles[0][2]) / (circles[-1][2] - circles[0][2])
                    color = plt.colormaps['viridis'](color_value)[:3]
                else:
                    color = 'blue'
                off_screen_plotter.add_mesh(circle_mesh, color=color, line_width=3)
            if circles:
                centers = np.array([[cx, cy, z] for cx, cy, z, r in circles])
                centers_cloud = pv.PolyData(centers)
                off_screen_plotter.add_mesh(centers_cloud, color='red', point_size=5)
            # off_screen_plotter.background_color = 'white'
            off_screen_plotter.screenshot(output_path)
            print(f"Visualization saved to: {output_path}")

        # Show interactive plot
        plotter.show()

    def reconstruct_tree(self, input_file: str, method: str = 'ransac',
                        visualize: bool = True, output_file: Optional[str] = None) -> List[Tuple[float, float, float, float]]:
        """
        Complete tree reconstruction pipeline.

        Args:
            input_file: Path to stem points file
            method: Circle fitting method
            visualize: Whether to show visualization
            output_file: Optional path to save results

        Returns:
            List of fitted circles
        """
        print("Starting tree reconstruction...")

        # Load and preprocess points
        points = self.load_stem_points(input_file)
        points_sorted = self.sort_points_by_height(points)

        # Segment stem
        segments = self.segment_stem(points_sorted)

        if not segments:
            raise ValueError("No valid segments found. Check segment parameters.")

        # Fit circles
        circles = self.fit_circles_to_segments(segments, method=method)

        if not circles:
            raise ValueError("Failed to fit any circles. Check point data quality.")

        # Save results
        if output_file:
            self.save_circles(circles, output_file)

        # Visualize
        if visualize:
            vis_output = output_file.replace('.csv', '_viz.png') if output_file else None
            self.create_visualization(points_sorted, circles, vis_output)

        print(f"Tree reconstruction complete! Fitted {len(circles)} circles.")
        return circles

    def save_circles(self, circles: List[Tuple[float, float, float, float]], output_file: str):
        """Save fitted circles to CSV file."""
        df = pd.DataFrame(circles, columns=['center_x', 'center_y', 'height', 'radius'])
        df.to_csv(output_file, index=False)
        print(f"Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Tree Stem Circle Fitting and Reconstruction')
    parser.add_argument('--input', '-i', required=True, help='Input stem points file (CSV or LAS/LAZ)')
    parser.add_argument('--output', '-o', help='Output CSV file for fitted circles')
    parser.add_argument('--segment_height', '-s', type=float, default=0.1,
                       help='Height of each stem segment (meters)')
    parser.add_argument('--method', '-m', choices=['algebraic', 'geometric', 'ransac'],
                       default='ransac', help='Circle fitting method')
    parser.add_argument('--visualize', '-v', action='store_true',
                       help='Show 3D visualization')
    parser.add_argument('--min_points', type=int, default=5,
                       help='Minimum points per segment')

    args = parser.parse_args()

    # Create reconstructor
    reconstructor = TreeReconstructor(
        segment_height=args.segment_height,
        min_points_per_segment=args.min_points
    )

    try:
        # Run reconstruction
        circles = reconstructor.reconstruct_tree(
            input_file=args.input,
            method=args.method,
            visualize=args.visualize,
            output_file=args.output
        )

        # Print summary
        print("\nReconstruction Summary:")
        print(f"Total circles fitted: {len(circles)}")
        if circles:
            radii = [r for _, _, _, r in circles]
            print(f"Mean radius: {np.mean(radii):.3f}m")
            print(f"Min radius: {np.min(radii):.3f}m")
            print(f"Max radius: {np.max(radii):.3f}m")

    except Exception as e:
        print(f"Error during reconstruction: {e}")
        sys.exit(1)


if __name__ == '__main__':
    # For testing without command line arguments
    if len(sys.argv) == 1:
        print("No arguments provided. Use --help for usage information.")
        print("\nExample usage:")
        print("python circle_fitting_reconstruction.py --input stem_points.las --visualize --output circles.csv")
    else:
        main()
