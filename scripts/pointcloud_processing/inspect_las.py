#!/usr/bin/env python3
"""
Quick inspection script to see what scalar fields are available in a LAS/LAZ file.
Run this in your component_extraction environment to debug the GUI.
"""

import laspy
import sys

# Replace with your LAS file path
las_path = r"c:\Users\W0491597\Documents\Arun\TreeAIBox (2)\TreeAIBox\data\20250407_LLR_L2_AllPoints_Orthometric.las"

try:
    las = laspy.read(las_path)
    print(f"Loaded LAS file: {las_path}")
    print()

    # Check various ways to get dimension names
    print("=== Checking las.point_format.dimension_names ===")
    if hasattr(las, 'point_format') and hasattr(las.point_format, 'dimension_names'):
        dims = list(las.point_format.dimension_names)
        print(f"Found {len(dims)} dimensions: {dims}")
    else:
        print("Not available via las.point_format.dimension_names")

    print()
    print("=== Checking las.points.dtype.names ===")
    try:
        if hasattr(las, 'points') and hasattr(las.points, 'dtype') and hasattr(las.points.dtype, 'names'):
            names = list(las.points.dtype.names)
            print(f"Found {len(names)} names: {names}")
        else:
            print("Not available via las.points.dtype.names")
    except Exception as e:
        print(f"Error accessing las.points.dtype.names: {e}")

    print()
    print("=== Checking las.header.point_format.dimension_names ===")
    if hasattr(las, 'header') and hasattr(las.header, 'point_format') and hasattr(las.header.point_format, 'dimension_names'):
        header_dims = list(las.header.point_format.dimension_names)
        print(f"Found {len(header_dims)} dimensions: {header_dims}")
    else:
        print("Not available via las.header.point_format.dimension_names")

    print()
    print("=== All attributes on las object (first 20) ===")
    attrs = [attr for attr in dir(las) if not attr.startswith('_')]
    print(attrs[:20])

    print()
    print("=== Sample scalar values (first 5 points) ===")
    # Try to access some common scalars
    for field in ['intensity', 'classification', 'return_number', 'number_of_returns', 'treefilter', 'itc']:
        try:
            vals = las[field][:5]
            print(f"{field}: {vals}")
        except Exception as e:
            print(f"{field}: not available ({e})")

except Exception as e:
    print(f"Error loading LAS file: {e}")
    sys.exit(1)