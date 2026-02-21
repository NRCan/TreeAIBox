#!/usr/bin/env python3
"""
Generate sample stem points for testing circle fitting reconstruction.

This script creates synthetic stem points that simulate a tapered tree trunk
with some noise and irregularities.
"""

import numpy as np
import pandas as pd
import argparse
import os


def generate_tree_stem_points(height: float = 5.0, base_radius: float = 0.3,
                            taper_factor: float = 0.7, noise_level: float = 0.02,
                            points_per_meter: int = 1000) -> np.ndarray:
    """
    Generate synthetic stem points for a tapered tree.

    Args:
        height: Total height of the stem
        base_radius: Radius at the base
        taper_factor: How much the radius decreases (0.7 = 30% taper)
        noise_level: Random noise to add
        points_per_meter: Number of points per meter height

    Returns:
        Nx3 array of (x, y, z) points
    """
    # Generate height values
    z_values = np.linspace(0, height, int(height * points_per_meter))

    all_points = []

    for z in z_values:
        # Calculate radius at this height (linear taper)
        radius = base_radius * (1 - taper_factor * (z / height))

        # Generate points around the circumference
        # Use more points for larger radii
        n_points = max(8, int(16 * radius / base_radius))

        angles = np.linspace(0, 2*np.pi, n_points, endpoint=False)

        for angle in angles:
            # Base position on circle
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)

            # Add noise
            x += np.random.normal(0, noise_level)
            y += np.random.normal(0, noise_level)
            z_noise = z + np.random.normal(0, noise_level * 0.5)

            all_points.append([x, y, z_noise])

    return np.array(all_points)


def add_stem_irregularities(points: np.ndarray, bend_factor: float = 0.1,
                          bulge_positions: List[float] = None) -> np.ndarray:
    """
    Add irregularities to make the stem more realistic.

    Args:
        points: Original stem points
        bend_factor: How much the stem bends
        bulge_positions: Heights where to add bulges

    Returns:
        Modified points
    """
    modified_points = points.copy()

    # Add a slight bend
    if bend_factor > 0:
        z_normalized = points[:, 2] / np.max(points[:, 2])
        bend_x = bend_factor * np.sin(z_normalized * np.pi) * points[:, 2]
        bend_y = bend_factor * np.cos(z_normalized * np.pi) * points[:, 2]
        modified_points[:, 0] += bend_x
        modified_points[:, 1] += bend_y

    # Add bulges at specified positions
    if bulge_positions:
        for bulge_z in bulge_positions:
            mask = np.abs(points[:, 2] - bulge_z) < 0.2  # Points near bulge height
            if np.any(mask):
                # Expand radius at bulge
                center = np.mean(modified_points[mask, :2], axis=0)
                vectors = modified_points[mask, :2] - center
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
                modified_points[mask, :2] = center + vectors * 1.2  # 20% bulge

    return modified_points


def save_points_to_csv(points: np.ndarray, filename: str):
    """Save points to CSV file."""
    df = pd.DataFrame(points, columns=['x', 'y', 'z'])
    df.to_csv(filename, index=False)
    print(f"Saved {len(points)} points to {filename}")


def main():
    parser = argparse.ArgumentParser(description='Generate sample stem points for testing')
    parser.add_argument('--output', '-o', default='sample_stem_points.csv',
                       help='Output CSV file')
    parser.add_argument('--height', type=float, default=5.0,
                       help='Stem height in meters')
    parser.add_argument('--base_radius', type=float, default=0.3,
                       help='Radius at base in meters')
    parser.add_argument('--taper', type=float, default=0.7,
                       help='Taper factor (0-1)')
    parser.add_argument('--noise', type=float, default=0.02,
                       help='Noise level')
    parser.add_argument('--density', type=int, default=1000,
                       help='Points per meter')
    parser.add_argument('--bend', type=float, default=0.05,
                       help='Stem bend factor')
    parser.add_argument('--bulges', nargs='*', type=float,
                       help='Heights for bulges')

    args = parser.parse_args()

    print("Generating sample stem points...")
    print(f"Height: {args.height}m, Base radius: {args.base_radius}m")
    print(f"Taper: {args.taper}, Noise: {args.noise}")

    # Generate basic stem
    points = generate_tree_stem_points(
        height=args.height,
        base_radius=args.base_radius,
        taper_factor=args.taper,
        noise_level=args.noise,
        points_per_meter=args.density
    )

    # Add irregularities
    points = add_stem_irregularities(
        points,
        bend_factor=args.bend,
        bulge_positions=args.bulges
    )

    # Save to file
    save_points_to_csv(points, args.output)

    # Print statistics
    print("
Statistics:")
    print(f"Total points: {len(points)}")
    print(".3f")
    print(".3f")
    print(".3f")
    print(".3f")


if __name__ == '__main__':
    main()
