###
###  Comparing Gridmetrics and CLoudmetrics from Fusion using the forest plots at Tims house. 
###

import subprocess
import os
import glob
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from shapely.geometry import Point
import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin
# Set PROJ_LIB to the correct path for this environment
import os
os.environ["PROJ_LIB"] = os.path.join(os.path.dirname(rasterio.__file__), "proj_data")

# Import tkinter for file dialogs
import tkinter as tk
from tkinter import filedialog

def select_file(title, filetypes, initialdir=None):
    """Helper function to select a file using tkinter dialog"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    filename = filedialog.askopenfilename(title=title, filetypes=filetypes, initialdir=initialdir)
    return filename

def select_directory(title, initialdir=None):
    """Helper function to select a directory using tkinter dialog"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    dirname = filedialog.askdirectory(title=title, initialdir=initialdir)
    return dirname

# Configuration - Let user select files and directories
print("Please select the input files and output directory...")

# Select LAS file
default_las_file = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Input\20250422_LLR_L2_NoOverlap_Orthometric.las"
if os.path.exists(default_las_file):
    print(f"Using default LAS file: {default_las_file}")
    las_file = default_las_file
else:
    print("Default LAS file not found, please select manually...")
    las_file = select_file("Select LAS file", [("LAS files", "*.las"), ("All files", "*.*")])
    if not las_file:
        print("No LAS file selected. Exiting.")
        exit()

# Get the directory of the selected LAS file to use as default for other dialogs
las_dir = os.path.dirname(las_file)

# Select shapefile (default to LAS file directory)
default_shp_file = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Plot_Polygon\Plot_Buffer_11m.shp"
if os.path.exists(default_shp_file):
    print(f"Using default shapefile: {default_shp_file}")
    shp_file = default_shp_file
else:
    print("Default shapefile not found, please select manually...")
    shp_file = select_file("Select shapefile", [("Shapefiles", "*.shp"), ("All files", "*.*")], initialdir=las_dir)
    if not shp_file:
        print("No shapefile selected. Exiting.")
        exit()

# Check shapefile fields
print(f"\nChecking shapefile: {shp_file}")
try:
    test_gdf = gpd.read_file(shp_file)
    print("Available fields in shapefile:")
    for i, col in enumerate(test_gdf.columns):
        print(f"  {i}: {col}")
    print(f"First few rows of data:")
    print(test_gdf.head())
except Exception as e:
    print(f"Error reading shapefile: {e}")
    exit()

# Select output directory (default to LAS file directory)
default_output_dir = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output\Test Folder"
if os.path.exists(default_output_dir):
    print(f"Using default output directory: {default_output_dir}")
    output_dir = default_output_dir
else:
    print("Default output directory not found, please select manually...")
    output_dir = select_directory("Select output directory", initialdir=las_dir)
    if not output_dir:
        print("No output directory selected. Exiting.")
        exit()

print(f"Selected LAS file: {las_file}")
print(f"Selected shapefile: {shp_file}")
print(f"Selected output directory: {output_dir}")

# Configuration
fusion_dir = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Fusion"
cellsize = 5
epsg_code = "EPSG:2961"

os.makedirs(output_dir, exist_ok=True)

# Use existing DTM instead of creating new one
ground_dtm = r"c:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output\20250422_LLR_L2_NoOverlap_Orthometric\DTM\20250422_LLR_L2_NoOverlap_Orthometric.dtm"

# Check if DTM exists
if not os.path.exists(ground_dtm):
    print(f"❌ Error: DTM file not found: {ground_dtm}")
    print("Please ensure the DTM file exists at the specified location.")
    exit()
else:
    print(f"✅ Using existing DTM: {ground_dtm}")

# Skip DTM creation since we already have one
print("Skipping DTM creation - using existing file")


# Step 2: Run GridMetrics (5m) on Entire Point Cloud (Vegetation points only)
gridmetrics_output = os.path.join(output_dir, "full_area_gridmetrics.csv")
heightbreak = 2  # 2 meters, adjust as needed
gridmetrics_cmd = [
    f'"{os.path.join(fusion_dir, "GridMetrics64.exe")}"',
    "/class:1",                                    # Class 1 points (veg)
    f'"{ground_dtm}"',                             # Ground surface (DTM)
    str(heightbreak),                              # Height break for canopy cover
    str(cellsize),                                 # Cell size
    f'"{gridmetrics_output}"',                     # Output CSV file (basename)
    f'"{las_file}"'                                # Input LAS file
]
print("Running GridMetrics command:")
print(" ".join(gridmetrics_cmd))
result = subprocess.run(" ".join(gridmetrics_cmd), shell=True, capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ Error: GridMetrics failed with exit code {result.returncode}")
    print(f"STDERR: {result.stderr}")
    print(f"STDOUT: {result.stdout}")
    exit()

# Check if GridMetrics output exists
elev_csv = gridmetrics_output.replace('.csv', '_all_returns_elevation_stats.csv')
if not os.path.exists(elev_csv):
    print(f"❌ Error: GridMetrics output file not found: {elev_csv}")
    print("Please check that FUSION is properly installed and the paths are correct.")
    exit()
else:
    print(f"✅ GridMetrics completed successfully: {elev_csv}")


# Step 3a: Clip LAS files (one per forest plot) for CloudMetrics
clip_folder = os.path.join(output_dir, "clipped_las")
os.makedirs(clip_folder, exist_ok=True)

# Determine which field to use for naming (look for common plot ID fields)
field_names = test_gdf.columns.tolist()
plot_id_field = None

# Look for common plot ID field names
for field in ['plot', 'plot_id', 'id', 'name', 'fid']:
    if field in field_names:
        plot_id_field = field
        break

# If no common field found, use the first non-geometry field
if plot_id_field is None:
    for field in field_names:
        if field.lower() not in ['geometry']:
            plot_id_field = field
            break

if plot_id_field is None:
    print("❌ Error: Could not find a suitable field for plot IDs in the shapefile")
    exit()

print(f"Using field '{plot_id_field}' for plot identification")

# Get the field index for PolyClipData
field_index = field_names.index(plot_id_field)
print(f"Field index: {field_index}")

clip_cmd = [
    f'"{os.path.join(fusion_dir, "PolyClipData.exe")}"',
    "/multifile",                                    # multipart shapefile
    f'/shape:{field_index},"*"',                     # field id for naming layers
    f'"{shp_file}"',                                 # path to shapefile
    f'"{os.path.join(clip_folder, "clipped_")}"',    # output base name
    f'"{las_file}"'                                  # path to las
]
print("Running PolyClipData command:")
print(" ".join(clip_cmd))
result = subprocess.run(" ".join(clip_cmd), shell=True, capture_output=True, text=True)

if result.returncode != 0:
    print(f"❌ Error: PolyClipData failed with exit code {result.returncode}")
    print(f"STDERR: {result.stderr}")
    print(f"STDOUT: {result.stdout}")
    exit()

# Check if clipped LAS files were created
clipped_files = glob.glob(os.path.join(clip_folder, "*.las"))
if not clipped_files:
    print(f"❌ Error: No clipped LAS files found in {clip_folder}")
    print("Please check that the shapefile contains valid polygons and FUSION PolyClipData worked correctly.")
    exit()
else:
    print(f"✅ Created {len(clipped_files)} clipped LAS files")

# Step 3b – normalise each clipped LAS
normalized_folder = clip_folder  # Use same folder as clipped files

# First, let's check the DTM bounds
print("\n🔍 Checking DTM bounds...")
dtm_info_cmd = [
    f'"{os.path.join(fusion_dir, "DTMDescribe.exe")}"',
    f'"{ground_dtm}"',
    f'"{os.path.join(output_dir, "dtm_info.csv")}"'
]
print("DTM bounds command:")
print(" ".join(dtm_info_cmd))
dtm_result = subprocess.run(" ".join(dtm_info_cmd), shell=True, capture_output=True, text=True)
print("DTM Info:")
print("STDOUT:", dtm_result.stdout)
print("STDERR:", dtm_result.stderr)

for las in glob.glob(os.path.join(clip_folder, "*.las")):
    # Skip already normalized files
    if "_normalized" in las:
        continue
        
    print(f"\n🔍 Checking clipped LAS: {os.path.basename(las)}")
    
    fn   = os.path.basename(las)                             # get the file name
    norm = os.path.join(normalized_folder, fn.replace(".las", "_normalized.las")) # naming for outfile
    with laspy.open(las) as f:                        # get extent of las files from the LAS header
        hdr = f.header
        minx, miny, maxx, maxy = (*hdr.mins[:2], *hdr.maxs[:2])
        print(f"LAS bounds from header: minx={minx}, miny={miny}, maxx={maxx}, maxy={maxy}")
        print(f"LAS point count: {hdr.point_count}")
    
    # Construct paths manually with backslashes for FUSION compatibility
    input_path = str(las).replace('/', '\\')
    output_path = str(norm).replace('/', '\\')
    
    normalize_cmd = [                                 # normalize las using clip data function in fusion
        os.path.join(fusion_dir, "ClipData.exe"),
        "/height",                                    # to record metrics as height above ground (needs dtm)
        f'/dtm:{ground_dtm}',                         # dtm file with proper quoting
        input_path,                                   # input file path
        output_path,                                  # output file path
        f"{minx}", f"{miny}",                         # MinX MinY
        f"{maxx}", f"{maxy}"                          # MaxX MaxY
    ]
    print(f"Running ClipData command: {' '.join(normalize_cmd)}")
    cp = subprocess.run(normalize_cmd, shell=False, check=False, capture_output=True, text=True)
    
    if cp.returncode != 0:
        print(f"   ❌ ClipData exited with {cp.returncode}")
        print(f"   STDERR: {cp.stderr}")
        print(f"   STDOUT: {cp.stdout}")
        continue
    else:
        print(f"   ✅ Normalization successful for {os.path.basename(las)}")



# Check if normalized LAS files were created
normalized_files = glob.glob(os.path.join(normalized_folder, "*.las"))
if not normalized_files:
    print(f"❌ Error: No normalized LAS files found in {normalized_folder}")
    print("All ClipData normalization commands failed.")
    print("Please check the FUSION installation and DTM file.")
    exit()
else:
    print(f"✅ Created {len(normalized_files)} normalized LAS files")

# # Step 4: CloudMetrics on clipped LAS files
cloudmetrics_folder = os.path.join(output_dir, "cloudmetrics")
os.makedirs(cloudmetrics_folder, exist_ok=True)
all_las_files = glob.glob(os.path.join(normalized_folder, "*.las"))
clipped_las_files = [f for f in all_las_files if "_normalized" in f]  # Only process normalized files
for las in clipped_las_files:                                                               # go through normalized clipped las files
    plot_name = os.path.splitext(os.path.basename(las))[0]                                  # get the name of plot
    cloudmetrics_out = os.path.join(cloudmetrics_folder, f"{plot_name}_cloudmetrics.csv")   # path to save cloud metrics
    cloudmetrics_cmd = [                                                                    
        f'"{os.path.join(fusion_dir, "CloudMetrics.exe")}"',                                       # tool path
        f'"{las}"',                                                                                # path to normalized clipped las
        f'"{cloudmetrics_out}"'                                                                    # outfile
    ]
    print(f"Running CloudMetrics for: {plot_name}")
    print(" ".join(cloudmetrics_cmd))
    subprocess.run(" ".join(cloudmetrics_cmd), shell=True)


# Step 5a: find the grid cells that in each plot and compare them to the cloud metrics
elev_csv = gridmetrics_output.replace('.csv', '_all_returns_elevation_stats.csv')
grid_df = pd.read_csv(elev_csv)
grid_df['geometry'] = [Point(x, y) for x, y in zip(grid_df['center X'], grid_df['center Y'])]
grid_gdf = gpd.GeoDataFrame(grid_df, geometry='geometry', crs=epsg_code)

plots = gpd.read_file(shp_file).to_crs(epsg_code)
joined = gpd.sjoin(grid_gdf, plots, how="inner", predicate='within')

# Step 5b: aggregate the grid cell metrics for each plot
grid_plot_means = (
    joined.drop(columns='geometry')
    .groupby('index_right')
    .mean(numeric_only=True)
    .reset_index()
)
grid_plot_means['plot'] = (plots.iloc[grid_plot_means['index_right']].index + 1).astype(str)

# Step 5c: load the cloud metrics csv 
cloudmetrics_folder = os.path.join(output_dir, "cloudmetrics")
cloud_files = glob.glob(os.path.join(cloudmetrics_folder, "*_cloudmetrics.csv"))

if not cloud_files:
    print(f"❌ Error: No cloudmetrics CSV files found in {cloudmetrics_folder}")
    print("This is likely due to ClipData normalization failures.")
    print("Please check the ClipData commands and ensure FUSION is working correctly.")
    exit()

cloudmetrics_df = pd.DataFrame()
for file in cloud_files:
    plot_id = os.path.basename(file).replace("_cloudmetrics.csv", "")
    print(f"Processing cloudmetrics file: {os.path.basename(file)}")
    print(f"Extracted plot_id: '{plot_id}'")
    
    # Try to extract numeric ID, but also keep original as fallback
    plot_id_clean = ''.join(filter(str.isdigit, plot_id))
    if not plot_id_clean:
        # If no digits found, use the full plot_id
        plot_id_clean = plot_id
    
    print(f"Cleaned plot_id: '{plot_id_clean}'")
    
    df = pd.read_csv(file)
    df['plot'] = plot_id_clean
    cloudmetrics_df = pd.concat([cloudmetrics_df, df], ignore_index=True)

print(f"✅ Loaded cloudmetrics data from {len(cloud_files)} files")

# Debug: Show what we have
print("\nDEBUG: CloudMetrics plot IDs:")
print(cloudmetrics_df['plot'].unique() if 'plot' in cloudmetrics_df.columns else "No 'plot' column found")

print("\nDEBUG: GridMetrics plot IDs:")
print(grid_plot_means['plot'].unique() if 'plot' in grid_plot_means.columns else "No 'plot' column found")

grid_plot_means['plot'] = grid_plot_means['plot'].astype(str)
cloudmetrics_df['plot'] = cloudmetrics_df['plot'].astype(str)

common_cols = list(set(grid_plot_means.columns) & set(cloudmetrics_df.columns))
common_cols = [col for col in common_cols if col not in ['index_right', 'plot']]

if not common_cols:
    print("❌ No common columns found. CSV will not be created.")
    exit()

grid_flat = grid_plot_means[['plot'] + common_cols].copy()
grid_flat.insert(0, 'ID', 'grid ' + grid_flat['plot'])
cloud_flat = cloudmetrics_df[['plot'] + common_cols].copy()
cloud_flat.insert(0, 'ID', 'cloud ' + cloud_flat['plot'])
combined_df = pd.concat([cloud_flat, grid_flat], ignore_index=True)

output_path = os.path.join(output_dir, "grid_cloud_comparison.csv")
combined_df.drop(columns='plot').to_csv(output_path, index=False)
print("✅ CSV successfully written to:", output_path)

# Create a test raster to see the coverage in each plot
header_path = elev_csv.replace('.csv', '_ascii_header.txt')
with open(header_path, 'r') as f:
    header_vals = {k.lower(): float(v) for k, v in (line.strip().split() for line in f)}

nrows = int(header_vals["nrows"])
ncols = int(header_vals["ncols"])
xllcenter = header_vals["xllcenter"]
yllcenter = header_vals["yllcenter"]
cellsize = float(header_vals["cellsize"])
x_ul = xllcenter - (cellsize / 2)
y_ul = yllcenter + (nrows * cellsize) - (cellsize / 2)
transform = from_origin(x_ul, y_ul, cellsize, cellsize)

# --- Area overlap logic for "in plot" mask (≥1/3 overlap) ---
half = cellsize / 2
grid_df['cell_poly'] = [
    box(x - half, y - half, x + half, y + half)
    for x, y in zip(grid_df['center X'], grid_df['center Y'])
]
plots_union = plots.union_all()
cell_area = cellsize * cellsize
frac_thresh = 1/3

grid_df['in_plot_overlap'] = [
    (poly.intersection(plots_union).area / cell_area) >= frac_thresh
    for poly in grid_df['cell_poly']
]

# --- Write metric raster (showing metric ONLY for cells in plots by area overlap) ---
metric = "Elev mean"
metric_arr = np.full((nrows, ncols), np.nan, np.float32)
for _, row in grid_df.iterrows():
    row_idx = int(row['row'])
    col_idx = int(row['col'])
    if row['in_plot_overlap']:
        metric_arr[row_idx, col_idx] = row[metric]

metric_arr_flipped = np.flipud(metric_arr)
tif_path_metric = os.path.join(output_dir, f"test_{metric.replace(' ', '_')}_in_plot_overlap.tif")
with rasterio.open(
        tif_path_metric, "w", driver="GTiff",
        height=nrows, width=ncols, count=1,
        dtype=metric_arr.dtype, crs=epsg_code,
        transform=transform, nodata=np.nan) as dst:
    dst.write(metric_arr_flipped, 1)
print("🗺️  Test metric raster written →", tif_path_metric)

