#!/usr/bin/env python3
"""
Simple PyVista visualization of stem points from LAS file
"""

from typing import Optional
import numpy as np
import laspy
import pyvista as pv
import argparse
import os


def load_stem_points(las_path: str, z_threshold: Optional[float] = None):
    """
    Load stem points from LAS file.

    Args:
        las_path: Path to LAS file
        z_threshold: Optional height threshold to filter points

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
    print(f"X range: {np.min(points[:, 0]):.2f} to {np.max(points[:, 0]):.2f}m")
    print(f"Y range: {np.min(points[:, 1]):.2f} to {np.max(points[:, 1]):.2f}m")

    return points


def visualize_stem_base(points: np.ndarray, base_height: Optional[float] = None):
    """
    Visualize stem points.

    Args:
        points: Nx3 array of stem points
        base_height: Optional height threshold for base points
    """
    if base_height is not None:
        # Filter to base points
        base_mask = points[:, 2] <= (np.min(points[:, 2]) + base_height)
        display_points = points[base_mask]
        print(f"Visualizing {len(display_points)} base points (bottom {base_height}m)")
    else:
        display_points = points
        print(f"Visualizing {len(display_points)} stem points (all)")

    # Calculate bounding box and tree height
    min_bounds = np.min(display_points, axis=0)
    max_bounds = np.max(display_points, axis=0)
    tree_height = max_bounds[2] - min_bounds[2]

    print(f"Tree height: {tree_height:.2f}m")
    print(f"Bounding box: X[{min_bounds[0]:.2f}, {max_bounds[0]:.2f}] Y[{min_bounds[1]:.2f}, {max_bounds[1]:.2f}] Z[{min_bounds[2]:.2f}, {max_bounds[2]:.2f}]")

    # Create PyVista point cloud
    point_cloud = pv.PolyData(display_points)

    # Create bounding box using outline
    bounds = [min_bounds[0], max_bounds[0], min_bounds[1], max_bounds[1], min_bounds[2], max_bounds[2]]
    bounding_box = pv.Cube(bounds=bounds).outline()

    # Create vertical markers every 1 meter
    vertical_lines = []
    z_levels = np.arange(min_bounds[2], max_bounds[2] + 1, 1.0)  # Every 1 meter

    for z in z_levels:
        # Create a small horizontal line at this height near the bounding box
        # Place it slightly outside the bounding box
        line_x = [min_bounds[0] - 0.5, min_bounds[0] - 0.5, max_bounds[0] + 0.5, max_bounds[0] + 0.5]
        line_y = [min_bounds[1] - 0.5, max_bounds[1] + 0.5, max_bounds[1] + 0.5, min_bounds[1] - 0.5]
        line_z = [z, z, z, z]

        # Create line points
        line_points = np.column_stack([line_x, line_y, line_z])
        line_mesh = pv.PolyData(line_points)
        lines = line_mesh.lines = np.array([5, 0, 1, 2, 3, 0])  # Closed rectangle
        vertical_lines.append(line_mesh)

    # Create plotter
    plotter = pv.Plotter()

    # Add points
    plotter.add_mesh(point_cloud, color='brown', point_size=3, label='Stem Points')

    # Add bounding box
    plotter.add_mesh(bounding_box, color='blue', line_width=2, label='Bounding Box')

    # Add vertical markers
    for i, line_mesh in enumerate(vertical_lines):
        z_height = z_levels[i]
        plotter.add_mesh(line_mesh, color='red', line_width=1, opacity=0.7)

    # Add text with tree height
    height_text = f"Tree Height: {tree_height:.2f}m"
    plotter.add_text(height_text, position='upper_left', font_size=12, color='black')

    # Add height markers text
    for i, z in enumerate(z_levels):
        if i % 2 == 0:  # Show every other marker to avoid clutter
            marker_text = f"{z:.1f}m"
            plotter.add_text(marker_text,
                           position=(min_bounds[0] - 1, min_bounds[1] - 1, z),
                           font_size=8, color='red')

    # Show the plot
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description='Visualize stem points from LAS file')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--base_height', '-b', type=float, default=None,
                       help='Height of base section to visualize (meters), if not specified shows all points')
    parser.add_argument('--z_threshold', '-z', type=float,
                       help='Optional height threshold to filter all points')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return

    try:
        # Load points
        points = load_stem_points(args.input, args.z_threshold)

        if len(points) == 0:
            print("No points to visualize!")
            return

        # Visualize
        if args.base_height is not None:
            visualize_stem_base(points, args.base_height)
        else:
            visualize_stem_base(points)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
