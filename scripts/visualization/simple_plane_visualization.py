#!/usr/bin/env python3
"""
Simple visualization of point cloud at a specific height plane.
"""

import numpy as np
import laspy
import pyvista as pv
import argparse
import os


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


def visualize_plane_at_height(points: np.ndarray, height: float, thickness: float = 0.1):
    """
    Visualize points at a specific height plane.

    Args:
        points: All stem points
        height: Height from bottom to visualize
        thickness: Plane cut thickness
    """
    min_z = np.min(points[:, 2])
    target_z = min_z + height

    # Extract plane cut
    lower_bound = target_z - thickness/2
    upper_bound = target_z + thickness/2

    mask = (points[:, 2] >= lower_bound) & (points[:, 2] <= upper_bound)
    plane_points = points[mask]

    print(f"Visualizing plane at {height:.1f}m from bottom (Z: {target_z:.2f}m)")
    print(f"Found {len(plane_points)} points in range [{lower_bound:.2f}, {upper_bound:.2f}]m")

    if len(plane_points) == 0:
        print("No points found at this height!")
        return

    # Create PyVista plotter
    plotter = pv.Plotter()

    # Add all points (dimmed background)
    all_points_cloud = pv.PolyData(points)
    plotter.add_mesh(all_points_cloud, color='lightgray', point_size=2, opacity=0.3,
                    label='All Stem Points')

    # Add plane cut points
    plane_cloud = pv.PolyData(plane_points)
    plotter.add_mesh(plane_cloud, color='red', point_size=8,
                    label=f'Plane points ({len(plane_points)} total)')

    # Add reference plane
    center = [(np.min(points[:, 0]) + np.max(points[:, 0]))/2,
              (np.min(points[:, 1]) + np.max(points[:, 1]))/2,
              target_z]
    plane_size = max(np.max(points[:, 0]) - np.min(points[:, 0]),
                     np.max(points[:, 1]) - np.min(points[:, 1])) * 1.2
    plane_surface = pv.Plane(center=center, i_size=plane_size, j_size=plane_size)
    plotter.add_mesh(plane_surface, color='lightblue', opacity=0.2,
                    label=f'Cut plane at {height:.1f}m')

    # Add info text
    info_text = f"Height: {height:.1f}m (Z: {target_z:.2f}m)\nPoints: {len(plane_points)}"
    plotter.add_text(info_text, position='upper_left', font_size=12, color='black')

    # Set camera
    plotter.camera.azimuth = 45
    plotter.camera.elevation = 30

    # Show the plot
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description='Visualize point cloud at a specific height plane')
    parser.add_argument('--input', '-i', required=True, help='Input LAS file')
    parser.add_argument('--height', type=float, default=8.0,
                       help='Height from bottom to visualize (meters)')
    parser.add_argument('--thickness', '-t', type=float, default=0.1,
                       help='Plane cut thickness (meters)')

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

        # Visualize the plane
        visualize_plane_at_height(all_points, args.height, args.thickness)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
