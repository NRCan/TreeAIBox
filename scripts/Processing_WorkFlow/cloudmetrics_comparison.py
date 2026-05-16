"""
Extent Comparison Script - RESULTS SUMMARY

This script compared bounding box/extent calculations between:
1. laspy method (from LL_grid_vs_cloud.py)
2. lasinfo method (from run_fusion_workflow.py)

KEY FINDINGS:
- Extents are essentially identical between methods
- Maximum difference: ~9.3e-10 units (far below 1cm threshold)
- Differences are within floating-point precision tolerance
- CloudMetrics differences must be due to other factors (flags, versions, processing)

This confirms that extent differences are NOT the cause of CloudMetrics variations.
"""

import subprocess
import os
import glob
import pandas as pd
import geopandas as gpd
import laspy
import json
from pathlib import Path

# Configuration
fusion_dir = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Fusion"
lastools_bin = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\LAStools\bin"
lasinfo_path = os.path.join(lastools_bin, 'lasinfo64.exe') if os.path.isfile(os.path.join(lastools_bin, 'lasinfo64.exe')) else os.path.join(lastools_bin, 'lasinfo.exe')

# Input files (same as other scripts)
las_file = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Input\20250422_LLR_L2_NoOverlap_Orthometric.las"
shp_file = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Plot_Polygon\Plot_Buffer_11m.shp"
ground_dtm = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output\Test Folder\ground_surface.dtm"

# Output directories for comparison
base_output_dir = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output"
extent_comparison_dir = os.path.join(base_output_dir, "Extent_Comparison")

# Create output directory
os.makedirs(extent_comparison_dir, exist_ok=True)

def get_extent_laspy(las_path):
    """Get bounding box using laspy (method from LL_grid_vs_cloud.py)"""
    try:
        with laspy.open(las_path) as f:
            hdr = f.header
            minx, miny, maxx, maxy = (*hdr.mins[:2], *hdr.maxs[:2])
            return {
                'minx': minx,
                'miny': miny,
                'maxx': maxx,
                'maxy': maxy,
                'method': 'laspy'
            }
    except Exception as e:
        print(f"❌ Error reading {las_path} with laspy: {e}")
        return None

def get_extent_lasinfo(las_path):
    """Get bounding box using lasinfo (method from run_fusion_workflow.py)"""
    try:
        lasinfo_cmd = f'& "{lasinfo_path}" -i "{las_path}" -json'
        result = subprocess.run(['powershell', '-Command', lasinfo_cmd], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ lasinfo failed for {las_path}: {result.stderr}")
            return None

        lasinfo_text = result.stdout.strip() or result.stderr.strip()
        if not lasinfo_text:
            print(f"❌ No output from lasinfo for {las_path}")
            return None

        info = json.loads(lasinfo_text)

        # Navigate to header (same logic as run_fusion_workflow.py)
        header = None
        if isinstance(info, dict) and 'lasinfo' in info and isinstance(info['lasinfo'], list) and info['lasinfo']:
            first = info['lasinfo'][0]
            if 'las_header_entries' in first:
                header = first['las_header_entries']
            elif 'header' in first:
                header = first['header']

        if not header:
            print(f"❌ Could not find LAS header in lasinfo output for {las_path}")
            return None

        min_x = float(header['min']['x'])
        min_y = float(header['min']['y'])
        max_x = float(header['max']['x'])
        max_y = float(header['max']['y'])

        return {
            'minx': min_x,
            'miny': min_y,
            'maxx': max_x,
            'maxy': max_y,
            'method': 'lasinfo'
        }
    except Exception as e:
        print(f"❌ Error reading {las_path} with lasinfo: {e}")
        return None

def compare_extents(las_path):
    """Compare extents from both methods for a single LAS file"""
    print(f"\n� Comparing extents for: {os.path.basename(las_path)}")

    # Get extents from both methods
    laspy_extent = get_extent_laspy(las_path)
    lasinfo_extent = get_extent_lasinfo(las_path)

    if not laspy_extent or not lasinfo_extent:
        print("❌ Could not get extents from both methods")
        return None

    # Calculate differences
    diff_minx = lasinfo_extent['minx'] - laspy_extent['minx']
    diff_miny = lasinfo_extent['miny'] - laspy_extent['miny']
    diff_maxx = lasinfo_extent['maxx'] - laspy_extent['maxx']
    diff_maxy = lasinfo_extent['maxy'] - laspy_extent['maxy']

    # Calculate areas
    area_laspy = (laspy_extent['maxx'] - laspy_extent['minx']) * (laspy_extent['maxy'] - laspy_extent['miny'])
    area_lasinfo = (lasinfo_extent['maxx'] - lasinfo_extent['minx']) * (lasinfo_extent['maxy'] - lasinfo_extent['miny'])
    area_diff = area_lasinfo - area_laspy

    comparison = {
        'file': os.path.basename(las_path),
        'laspy_minx': laspy_extent['minx'],
        'laspy_miny': laspy_extent['miny'],
        'laspy_maxx': laspy_extent['maxx'],
        'laspy_maxy': laspy_extent['maxy'],
        'laspy_area': area_laspy,
        'lasinfo_minx': lasinfo_extent['minx'],
        'lasinfo_miny': lasinfo_extent['miny'],
        'lasinfo_maxx': lasinfo_extent['maxx'],
        'lasinfo_maxy': lasinfo_extent['maxy'],
        'lasinfo_area': area_lasinfo,
        'diff_minx': diff_minx,
        'diff_miny': diff_miny,
        'diff_maxx': diff_maxx,
        'diff_maxy': diff_maxy,
        'diff_area': area_diff
    }

    print("  📐 laspy extent:")
    print("    {:.6f}, {:.6f}, {:.6f}, {:.6f}".format(
        laspy_extent['minx'], laspy_extent['miny'],
        laspy_extent['maxx'], laspy_extent['maxy']
    ))
    print("  📐 lasinfo extent:")
    print("    {:.6f}, {:.6f}, {:.6f}, {:.6f}".format(
        lasinfo_extent['minx'], lasinfo_extent['miny'],
        lasinfo_extent['maxx'], lasinfo_extent['maxy']
    ))
    print("  📊 Differences:")
    print("    minx: {:.6f}, miny: {:.6f}, maxx: {:.6f}, maxy: {:.6f}".format(
        diff_minx, diff_miny, diff_maxx, diff_maxy
    ))
    print("  📏 Area difference: {:.6f} sq units".format(area_diff))

    return comparison

def clip_las_to_plots():
    """Clip LAS to plots and return the clipped file paths"""
    print("=== STEP 1: Clipping LAS to Plots ===")

    # Create clipped folder
    clipped_folder = os.path.join(base_output_dir, "temp_clipped")
    os.makedirs(clipped_folder, exist_ok=True)

    # Load shapefile to get field info
    test_gdf = gpd.read_file(shp_file)
    field_names = test_gdf.columns.tolist()

    # Find plot ID field
    plot_id_field = None
    for field in ['plot', 'plot_id', 'id', 'name', 'fid']:
        if field in field_names:
            plot_id_field = field
            break

    if plot_id_field is None:
        for field in field_names:
            if field.lower() not in ['geometry']:
                plot_id_field = field
                break

    if plot_id_field is None:
        print("❌ Error: Could not find a suitable field for plot IDs in the shapefile")
        return []

    field_index = field_names.index(plot_id_field)

    # Run PolyClipData
    clip_cmd = [
        f'"{os.path.join(fusion_dir, "PolyClipData.exe")}"',
        "/multifile",
        f'/shape:{field_index},"*"',
        f'"{shp_file}"',
        f'"{os.path.join(clipped_folder, "clipped_")}"',
        f'"{las_file}"'
    ]

    print("Running PolyClipData...")
    result = subprocess.run(" ".join(clip_cmd), shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ PolyClipData failed: {result.stderr}")
        return []

    # Get clipped files
    clipped_files = glob.glob(os.path.join(clipped_folder, "*.las"))
    print(f"✅ Created {len(clipped_files)} clipped LAS files")

    return clipped_files

def main():
    """Main function to compare extents between laspy and lasinfo"""
    print("🚀 Starting Extent Comparison Script")
    print("=" * 50)

    # Check input files
    for file_path, name in [(las_file, "LAS file"), (shp_file, "Shapefile"), (ground_dtm, "DTM")]:
        if not os.path.exists(file_path):
            print(f"❌ {name} not found: {file_path}")
            return
        else:
            print(f"✅ {name}: {os.path.basename(file_path)}")

    print(f"\n📁 Output directory: {extent_comparison_dir}")

    # Step 1: Clip LAS to plots
    clipped_files = clip_las_to_plots()

    if not clipped_files:
        print("❌ No clipped files created. Exiting.")
        return

    # Step 2: Compare extents for each clipped file
    print("\n=== STEP 2: Comparing Extents ===")

    all_comparisons = []

    for las_path in clipped_files:
        if "_normalized" in las_path:  # Skip already normalized files
            continue

        comparison = compare_extents(las_path)
        if comparison:
            all_comparisons.append(comparison)

    # Step 3: Save comparison results
    if all_comparisons:
        comparison_df = pd.DataFrame(all_comparisons)

        # Save detailed comparison
        detailed_csv = os.path.join(extent_comparison_dir, "extent_comparison_detailed.csv")
        comparison_df.to_csv(detailed_csv, index=False)
        print(f"\n✅ Detailed comparison saved to: {detailed_csv}")

        # Save summary statistics
        summary_stats = comparison_df[['diff_minx', 'diff_miny', 'diff_maxx', 'diff_maxy', 'diff_area']].describe()
        summary_csv = os.path.join(extent_comparison_dir, "extent_comparison_summary.csv")
        summary_stats.to_csv(summary_csv)
        print(f"✅ Summary statistics saved to: {summary_csv}")

        # Print summary
        print("\n📈 Summary of Extent Differences:")
        print("=" * 40)
        print(summary_stats)

        # Check for significant differences
        max_diff = max(
            abs(comparison_df['diff_minx'].max()),
            abs(comparison_df['diff_miny'].max()),
            abs(comparison_df['diff_maxx'].max()),
            abs(comparison_df['diff_maxy'].max())
        )

        if max_diff > 0.01:  # More than 1cm difference
            print("⚠️  SIGNIFICANT DIFFERENCES DETECTED!")
            print(f"   Maximum difference: {max_diff:.4f} units")
        else:
            print("✅ Differences are within acceptable range (< 1cm)")
    else:
        print("❌ No comparison data generated")

    print("\n" + "=" * 50)
    print("🎉 Extent Comparison Complete!")
    print(f"   Files compared: {len(all_comparisons)}")
    print(f"   Results saved to: {extent_comparison_dir}")

if __name__ == "__main__":
    main()
