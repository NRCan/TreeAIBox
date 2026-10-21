import json
import os
import subprocess
import glob
import re

"""
FUSION Workflow Script

Common Parameters:
    fusion_dir      : Path to FUSION main directory (where .exe files are located)
    las_file_path   : Path to input LAS file (LiDAR point cloud)
    output_root     : Directory for output files (used by GroundFilter)
    output_prefix   : Output prefix (used by PolyClipData)
    overwrite       : Whether to overwrite existing output files (True/False)

PolyClipData-Specific:
    shapefile_path  : Path to input shapefile (polygon boundaries)
    field_name      : Name of field in shapefile for naming output files
    multifile       : Output one LAS per polygon (True) or a single file (False)
    verbose         : Print detailed output (True/False)

GroundFilter-Specific:
    cell_size       : Cell size for ground filtering grid
    gparam          : Optional ground parameter
    wparam          : Optional window parameter
    iterations      : Number of filtering iterations
"""

# === COMMON PARAMETERS ===
# Path to Fusion main directory
fusion_dir = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Fusion"
# Path to LAStools bin directory
lastools_bin = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\LAStools\bin"
# Main output root directory
output_root = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Output"
lasinfo_path = os.path.join(lastools_bin, 'lasinfo64.exe') if os.path.isfile(os.path.join(lastools_bin, 'lasinfo64.exe')) else os.path.join(lastools_bin, 'lasinfo.exe')
overwrite = False
# === END COMMON PARAMETERS ===


def run_gridmetrics(
    normalized_folder,
    gridmetrics_exe=None,
    output_root=None,
    ground_model='*',
    height_break='0.0',
    cell_size='5.0',
    raster_metrics='mean,cover,p90',
    overwrite=False,
    print_info=True
):
    """
    Run GridMetrics on all normalized LAS files in normalized_folder.
    Output ASCII/CSV files are placed in <las_base_name>/gridmetrics under output_root.
    """
    if not gridmetrics_exe:
        exe64 = os.path.join(fusion_dir, 'GridMetrics64.exe')
        exe32 = os.path.join(fusion_dir, 'GridMetrics.exe')
        if os.path.isfile(exe64):
            gridmetrics_exe = exe64
        elif os.path.isfile(exe32):
            gridmetrics_exe = exe32
        else:
            if print_info:
                print('[ERROR] GridMetrics executable not found in Fusion folder.')
            return []
    # Use module-level output_root if caller did not provide one
    if not output_root:
        output_root = globals().get('output_root', os.getcwd())
    if not os.path.isdir(normalized_folder):
        if print_info:
            print(f'[ERROR] Normalized LAS folder does not exist: {normalized_folder}')
        return []
    las_files = [f for f in os.listdir(normalized_folder) if f.lower().endswith('.las')]
    if not las_files:
        if print_info:
            print(f'[SKIP] No normalized LAS files found in: {normalized_folder}')
        return []
    las_base_name = os.path.basename(os.path.dirname(normalized_folder))
    las_folder = os.path.join(output_root, las_base_name)
    gridmetrics_output_folder = os.path.join(las_folder, 'gridmetrics')
    os.makedirs(gridmetrics_output_folder, exist_ok=True)
    output_files = []
    for las_name in las_files:
        las_path = os.path.join(normalized_folder, las_name)
        out_base = os.path.join(gridmetrics_output_folder, las_name.replace('.las', '_gridmetrics'))
        out_ascii = out_base + '.asc'
        # Overwrite protection
        if os.path.isfile(out_ascii) and not overwrite:
            if print_info:
                print(f'[SKIP] GridMetrics output already exists: {out_ascii}. Skipping.')
            output_files.append(out_ascii)
            continue
        raster_part = f'/raster:{raster_metrics} ' if raster_metrics else ''
        cmd = (
            f'& "{gridmetrics_exe}" {raster_part}/ascii /minht:{height_break} /verbose '
            f'"{ground_model}" {height_break} {cell_size} "{out_base}" "{las_path}"'
        )
        if print_info:
            print(f'Running GridMetrics for {las_name}...')
            print(f'  Input LAS: {las_path}')
            print(f'  Output ASCII: {out_ascii}')
            print(f'  PowerShell command: {cmd}')
        # Run GridMetrics and capture stdout/stderr for debugging
        result = subprocess.run(['powershell', '-Command', cmd], capture_output=True, text=True)
        if print_info:
            print('Return code:', result.returncode)
            try:
                if result.stdout:
                    print(result.stdout.strip())
                if result.stderr:
                    print('stderr:', result.stderr.strip())
            except Exception:
                pass

        # GridMetrics frequently produces multiple outputs with extended names
        # (e.g. *_all_returns_all_metrics_elevation_mean.asc, *_all_returns_elevation_stats.csv, etc.).
        # Accept any produced file that starts with out_base as success.
        produced = glob.glob(out_base + '*')
        if produced:
            if print_info:
                print(f'  [OK] GridMetrics produced files: {produced}')
            output_files.extend(produced)
        else:
            if print_info:
                print(f'  [ERROR] GridMetrics failed for {las_name}')
    return output_files
def run_cloudmetrics(
    normalized_folder,
    cloudmetrics_exe=None,
    output_root=None,
    overwrite=False,
    print_info=True
):
    """
    Run CloudMetrics on all normalized LAS files in normalized_folder.
    Output CSVs are placed in <las_base_name>/cloudmetrics under output_root.
    """
    if not cloudmetrics_exe:
        # Try to auto-detect CloudMetrics.exe in fusion_dir
        exe64 = os.path.join(fusion_dir, 'CloudMetrics64.exe')
        exe32 = os.path.join(fusion_dir, 'CloudMetrics.exe')
        if os.path.isfile(exe64):
            cloudmetrics_exe = exe64
        elif os.path.isfile(exe32):
            cloudmetrics_exe = exe32
        else:
            if print_info:
                print('[ERROR] CloudMetrics executable not found in Fusion folder.')
            return []
    # Use module-level output_root if caller did not provide one
    if not output_root:
        output_root = globals().get('output_root', os.getcwd())
    if not os.path.isdir(normalized_folder):
        if print_info:
            print(f'[ERROR] Normalized LAS folder does not exist: {normalized_folder}')
        return []
    las_files = [f for f in os.listdir(normalized_folder) if f.lower().endswith('.las')]
    if not las_files:
        if print_info:
            print(f'[SKIP] No normalized LAS files found in: {normalized_folder}')
        return []
    # Determine las_base_name from normalized_folder's parent (should be output_root/<las_base_name>/normalized)
    las_base_name = os.path.basename(os.path.dirname(normalized_folder))
    las_folder = os.path.join(output_root, las_base_name)
    cloudmetrics_output_folder = os.path.join(las_folder, 'cloudmetrics')
    os.makedirs(cloudmetrics_output_folder, exist_ok=True)
    output_files = []
    for las_name in las_files:
        las_path = os.path.join(normalized_folder, las_name)
        out_csv = os.path.join(cloudmetrics_output_folder, las_name.replace('.las', '_metrics.csv'))
        if os.path.isfile(out_csv) and not overwrite:
            if print_info:
                print(f'[SKIP] CloudMetrics output already exists: {out_csv}. Skipping.')
            output_files.append(out_csv)
            continue
        cmd = f'& "{cloudmetrics_exe}" /new /id /verbose "{las_path}" "{out_csv}"'
        if print_info:
            print(f'Running CloudMetrics for {las_name}...')
            print(f'  Input LAS: {las_path}')
            print(f'  Output CSV: {out_csv}')
            print(f'  PowerShell command: {cmd}')
        result = subprocess.run(['powershell', '-Command', cmd])
        if result.returncode == 0 and os.path.isfile(out_csv):
            if print_info:
                print(f'  [OK] Output file created: {out_csv}')
            output_files.append(out_csv)
        else:
            if print_info:
                print(f'  [ERROR] CloudMetrics failed for {las_name}')
    return output_files

def normalize_las_files(
    input_folder,
    ground_dtm,
    clipdata_path=None,
    overwrite=False,
    print_info=True
):
    """
    Normalize all LAS files in input_folder using FUSION's clipdata64.exe and lasinfo64.exe.
    Output is placed in <las_base_name>/normalized under output_root.
    """
    # Set up clipdata_path from Fusion directory by default
    if not clipdata_path:
        clipdata64_candidate = os.path.join(fusion_dir, 'clipdata64.exe')
        clipdata_candidate = os.path.join(fusion_dir, 'clipdata.exe')
        print(f'[DEBUG] Checking for clipdata64.exe at: {clipdata64_candidate}')
        print(f'[DEBUG] Checking for clipdata.exe at: {clipdata_candidate}')
        if os.path.isfile(clipdata64_candidate):
            clipdata_path = clipdata64_candidate
        elif os.path.isfile(clipdata_candidate):
            clipdata_path = clipdata_candidate
        else:
            clipdata_path = None
    print(f'[DEBUG] Using lasinfo_path: {lasinfo_path}')
    print(f'[DEBUG] Using clipdata_path: {clipdata_path}')
    if not clipdata_path or not os.path.isfile(clipdata_path):
        print(f'[ERROR] clipdata executable not found at expected locations.')
        return []
    if not os.path.isfile(lasinfo_path):
        print(f'[ERROR] lasinfo executable not found at expected location: {lasinfo_path}')
        return []
    if not os.path.isdir(input_folder):
        print(f'[ERROR] Input folder does not exist: {input_folder}')
        return []
    if not os.path.isfile(ground_dtm):
        print(f'[ERROR] Ground DTM file not found: {ground_dtm}')
        return []
    las_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.las')]
    if not las_files:
        print(f'[SKIP] No LAS files found in input folder: {input_folder}')
        return []
    # Save normalized output in output_root/<las_base_name>/normalized/
    # Determine las_base_name from input_folder's parent (should be output_root/<las_base_name>/clipped_to_polygon)
    las_base_name = os.path.basename(os.path.dirname(input_folder))
    las_folder = os.path.join(output_root, las_base_name)
    normalized_output_folder = os.path.join(las_folder, 'normalized')
    os.makedirs(normalized_output_folder, exist_ok=True)
    output_files = []
    for las_name in las_files:
        las_path = os.path.join(input_folder, las_name)
        base, ext = os.path.splitext(las_name)
        out_name = f'{base}_normalized{ext}'
        out_path = os.path.join(normalized_output_folder, out_name)
        # Overwrite protection
        if os.path.isfile(out_path) and not overwrite:
            if print_info:
                print(f'[SKIP] Normalized LAS already exists: {out_path}. Skipping normalization for this file.')
            output_files.append(out_path)
            continue
        # Get bounding box using lasinfo64.exe
        lasinfo_cmd = f'& "{lasinfo_path}" -i "{las_path}" -json'
        try:
            result = subprocess.run(['powershell', '-Command', lasinfo_cmd], capture_output=True, text=True)
            # lasinfo typically writes JSON to stdout; fall back to stderr if stdout is empty
            lasinfo_text = result.stdout.strip() or result.stderr.strip()
            if not lasinfo_text:
                raise RuntimeError('lasinfo produced no output')
            info = json.loads(lasinfo_text)
            # Expecting structure with lasinfo -> list -> las_header_entries
            header = None
            if isinstance(info, dict) and 'lasinfo' in info and isinstance(info['lasinfo'], list) and info['lasinfo']:
                first = info['lasinfo'][0]
                # older/newer lasinfo structures may vary; try a couple of common keys
                if 'las_header_entries' in first:
                    header = first['las_header_entries']
                elif 'header' in first:
                    header = first['header']
            if not header:
                raise KeyError('Could not find LAS header entries in lasinfo output')
            min_x = str(header['min']['x'])
            min_y = str(header['min']['y'])
            max_x = str(header['max']['x'])
            max_y = str(header['max']['y'])
        except Exception as e:
            if print_info:
                print(f'[ERROR] Could not extract bounding box for {las_name}: {e}')
                # optionally show raw lasinfo output for debugging
                try:
                    print('lasinfo stdout:', result.stdout)
                    print('lasinfo stderr:', result.stderr)
                except Exception:
                    pass
            continue
        # Run clipdata64.exe with bounding box
        cmd = f'& "{clipdata_path}" /height /dtm:"{ground_dtm}" "{las_path}" "{out_path}" {min_x} {min_y} {max_x} {max_y}'
        if print_info:
            print(f'Normalizing {las_name}...')
            print(f'  Input LAS: {las_path}')
            print(f'  Output:    {out_path}')
            print(f'  DTM:       {ground_dtm}')
            print(f'  Bounding box: {min_x} {min_y} {max_x} {max_y}')
            print(f'  PowerShell command: {cmd}')
        result = subprocess.run(['powershell', '-Command', cmd])
        if result.returncode == 0 and os.path.isfile(out_path):
            if print_info:
                print(f'  [OK] Output file created: {out_path}')
            output_files.append(out_path)
        else:
            if print_info:
                print(f'  [ERROR] Normalization failed for {las_name}')
    return output_files

def polyclip(
    las_file_path,
    shapefile_path,
    field_name,
    multifile=True,
    verbose=True,
    print_info=True,
    overwrite=None
):
    # PolyClipData output goes in <las_base_name>/clipped_to_polygon subfolder under output_root
    las_base_name = os.path.splitext(os.path.basename(las_file_path))[0]
    las_folder = os.path.join(output_root, las_base_name)
    polyclip_output_folder = os.path.join(las_folder, "clipped_to_polygon")
    os.makedirs(polyclip_output_folder, exist_ok=True)
    # Use LAS base name in the prefix so outputs are named like <LASNAME>_clipped
    output_prefix = os.path.join(polyclip_output_folder, f"{las_base_name}_clipped")
    # Check for existing output files (multifile: any .las starting with the new prefix, single file: <LASNAME>_clipped.las)
    output_exists = False
    if multifile:
        for fname in os.listdir(polyclip_output_folder):
            if fname.startswith(f"{las_base_name}_clipped") and fname.endswith(".las"):
                output_exists = True
                break
    else:
        single_out = output_prefix + ".las"
        if os.path.isfile(single_out):
            output_exists = True
    # Resolve overwrite: function param overrides global, otherwise use global variable
    if overwrite is None:
        overwrite = globals().get('overwrite', False)
    if output_exists and not overwrite:
        print(f'[SKIP] PolyClipData output already exists in: {polyclip_output_folder}. Skipping PolyClipData step.')
        return
    # Select executable (64-bit preferred)
    exe_path = os.path.join(fusion_dir, 'PolyClipData64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'PolyClipData.exe')
    if not os.path.isfile(exe_path):
        print(f'[ERROR] PolyClipData.exe not found in Fusion folder: {fusion_dir}')
        return
    # Build command options as a string (PowerShell style)
    options = []
    if verbose:
        options.append('/verbose')
    if multifile:
        options.append('/multifile')
    # Always include /shape:2,* for multifile; for single file, you may want to adjust this
    options.append('/shape:2,*')
    options_str = ' '.join(options)
    cmd = (
        f'& "{exe_path}" {options_str} "{shapefile_path}" "{output_prefix}" "{las_file_path}"'
    )
    if print_info:
        print('Running PolyClipData with the following parameters:')
        print(f'  Fusion directory: {fusion_dir}')
        print(f'  PolyClipData exe: {exe_path}')
        print(f'  Shapefile:       {shapefile_path}')
        print(f'  LAS file:        {las_file_path}')
        print(f'  Output root:     {output_root}')
        print(f'  Output folder:   {polyclip_output_folder}')
        print(f'  Output prefix:   {output_prefix}')
        print(f'  Field name:      {field_name}')
        print(f'  Multifile:       {multifile}')
        print(f'  Verbose:         {verbose}')
        print(f'  Overwrite:       {overwrite}')
        print('\nPowerShell command:')
        print(cmd)
    result = subprocess.run(['powershell', '-Command', cmd])
    if print_info:
        print('Return code:', result.returncode)
    # If requested, post-process PolyClipData outputs to append the shapefile field value
    try:
        import shapefile as pyshp
    except Exception:
        pyshp = None

    def _sanitize(s):
        if s is None:
            return 'null'
        s = str(s)
        s = s.strip()
        # Replace spaces with underscore
        s = re.sub(r"\s+", "_", s)
        # Remove characters other than alnum, dash, underscore, dot
        s = re.sub(r"[^A-Za-z0-9_\-\.]+", "", s)
        # Truncate to reasonable length
        return s[:120]

    # Attempt to read attribute values from shapefile if pyshp is available
    if pyshp and os.path.isfile(shapefile_path):
        try:
            sf = pyshp.Reader(shapefile_path)
            # fields: first entry may be DeletionFlag — fields list contains tuples
            fields = [f[0] for f in sf.fields if f[0] != 'DeletionFlag']
            if field_name not in fields:
                if print_info:
                    print(f'[WARN] Field "{field_name}" not found in shapefile. Skipping attribute-based renaming.')
                attr_values = []
            else:
                # field index in records corresponds to fields list
                idx = fields.index(field_name)
                records = sf.records()
                attr_values = [records[i][idx] if idx < len(records[i]) else None for i in range(len(records))]
        except Exception as e:
            if print_info:
                print(f'[WARN] Could not read shapefile attributes: {e}. Skipping attribute-based renaming.')
            attr_values = []
    else:
        attr_values = []

    # Helper to attempt safe rename without overwriting unless overwrite is True
    def _safe_rename(src, dst):
        if not os.path.isfile(src):
            return False
        if os.path.isfile(dst) and not overwrite:
            if print_info:
                print(f'[SKIP] Target exists and overwrite=False: {dst}')
            return False
        try:
            os.replace(src, dst)
            if print_info:
                print(f'  Renamed: {src} -> {dst}')
            return True
        except Exception as e:
            if print_info:
                print(f'  [WARN] Failed to rename {src} -> {dst}: {e}')
            return False

    # Rename logic for multifile outputs
    if multifile:
        # List produced LAS files that start with the prefix
        produced = sorted([f for f in os.listdir(polyclip_output_folder) if f.startswith(f"{las_base_name}_clipped") and f.lower().endswith('.las')])
        if produced and attr_values:
            # If counts match, map 1:1 by order
            if len(produced) == len(attr_values):
                for i, fname in enumerate(produced):
                    src = os.path.join(polyclip_output_folder, fname)
                    value = _sanitize(attr_values[i])
                    dst_name = f"{las_base_name}_clipped_{value}.las"
                    dst = os.path.join(polyclip_output_folder, dst_name)
                    _safe_rename(src, dst)
            else:
                # Try to match numeric suffixes in produced filenames to record indices
                matched = 0
                for fname in produced:
                    m = re.search(r"(\d+)(?=\.las$)", fname)
                    if m:
                        idx = int(m.group(1)) - 1  # PolyClipData often numbers polygons starting at 1
                        if 0 <= idx < len(attr_values):
                            src = os.path.join(polyclip_output_folder, fname)
                            value = _sanitize(attr_values[idx])
                            dst = os.path.join(polyclip_output_folder, f"{las_base_name}_clipped_{value}.las")
                            if _safe_rename(src, dst):
                                matched += 1
                if matched == 0:
                    if print_info:
                        print('[WARN] Could not confidently map produced polyclip files to shapefile records; leaving original names.')
        else:
            if print_info:
                print('[INFO] No attribute values found or no produced polyclip files to rename.')
    else:
        # Single-file mode: rename single output to include attribute(s)
        single_out = output_prefix + ".las"
        if os.path.isfile(single_out):
            if attr_values:
                unique_vals = sorted(set([_sanitize(v) for v in attr_values if v is not None]))
                if len(unique_vals) == 1:
                    suffix = unique_vals[0]
                else:
                    # multiple attribute values: join first few or fall back to shapefile basename
                    shp_base = os.path.splitext(os.path.basename(shapefile_path))[0]
                    joined = "+".join(unique_vals[:5])
                    suffix = joined if len(joined) <= 60 else shp_base
            else:
                suffix = os.path.splitext(os.path.basename(shapefile_path))[0]
            dst = os.path.join(polyclip_output_folder, f"{las_base_name}_clipped_{suffix}.las")
            _safe_rename(single_out, dst)
        else:
            if print_info:
                print(f'[INFO] Expected single PolyClipData output not found: {single_out}')

def groundfilter(
    las_file_path,
    cell_size=5.0,
    gparam=None,
    wparam=None,
    iterations=8,
    print_info=True
):
    exe_path = os.path.join(fusion_dir, 'GroundFilter64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'GroundFilter.exe')
    if not os.path.isfile(exe_path):
        print(f'[ERROR] GroundFilter.exe not found in Fusion folder: {fusion_dir}')
        return None
    # Prepare output path
    las_base_name = os.path.splitext(os.path.basename(las_file_path))[0]
    # GroundFilter output goes in <las_base_name>/ground points subfolder under output_root
    las_folder = os.path.join(output_root, las_base_name)
    ground_points_output_folder = os.path.join(las_folder, 'ground points')
    os.makedirs(ground_points_output_folder, exist_ok=True)
    out_path = os.path.join(ground_points_output_folder, f'{las_base_name}_ground.las')
    if os.path.isfile(out_path) and not overwrite:
        print(f'[SKIP] Ground points LAS already exists: {out_path}. Skipping GroundFilter step.')
        return out_path
    # Build command options as a string (PowerShell style)
    options = []
    if gparam:
        options.append(f'/gparam:{gparam}')
    if wparam:
        options.append(f'/wparam:{wparam}')
    if iterations:
        options.append(f'/iterations:{iterations}')
    options_str = ' '.join(options)
    cmd = (
        f'& "{exe_path}" {options_str} "{out_path}" "{cell_size}" "{las_file_path}"'
    )
    if print_info:
        print('Running GroundFilter with the following parameters:')
        print(f'  Fusion directory: {fusion_dir}')
        print(f'  GroundFilter exe: {exe_path}')
        print(f'  Input LAS:        {las_file_path}')
        print(f'  Output root:      {output_root}')
        print(f'  Output folder:    {ground_points_output_folder}')
        print(f'  Cell size:        {cell_size}')
        print(f'  gparam:           {gparam}')
        print(f'  wparam:           {wparam}')
        print(f'  iterations:       {iterations}')
        print(f'  Overwrite:        {overwrite}')
        print('\nPowerShell command:')
        print(cmd)
    result = subprocess.run(['powershell', '-Command', cmd])
    if print_info:
        print('Return code:', result.returncode)
        if result.returncode == 0:
            print('Ground points LAS created:', out_path)
        else:
            print('[ERROR] GroundFilter failed.')
    if result.returncode == 0:
        return out_path
    else:
        return None

def generate_dtm(
    ground_las_path,
    cell_size=5.0,
    xyunits='M',
    zunits='M',
    coordsys=1,
    zone=20,
    horizdatum=2,
    vertdatum=2,
    extra_params=None,
    print_info=True,
    generate_tif=False,
    overwrite=False
):
    """
    Generate a DTM from a ground points LAS file using FUSION's GridSurfaceCreate.
    Output is placed in a DTM subfolder under the LAS folder in output_root.
    """
    if not os.path.isfile(ground_las_path):
        print(f'[ERROR] Ground points LAS file not found: {ground_las_path}')
        return
    exe_path = os.path.join(fusion_dir, 'GridSurfaceCreate64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'GridSurfaceCreate.exe')
    if not os.path.isfile(exe_path):
        print(f'[ERROR] GridSurfaceCreate.exe not found in Fusion folder: {fusion_dir}')
        return
    las_base_name = os.path.splitext(os.path.basename(ground_las_path))[0].replace('_ground', '')
    las_folder = os.path.join(output_root, las_base_name)
    dtm_output_folder = os.path.join(las_folder, 'DTM')
    os.makedirs(dtm_output_folder, exist_ok=True)
    out_dtm = os.path.join(dtm_output_folder, f'{las_base_name}.dtm')
    # Check for existing output DTM file
    if os.path.isfile(out_dtm) and not overwrite:
        print(f'[SKIP] DTM file already exists: {out_dtm}. Skipping DTM generation step.')
        # If generate_tif is requested, check for TIF as well
        if generate_tif:
            tif_path = out_dtm.replace('.dtm', '.tif')
            if os.path.isfile(tif_path) and not overwrite:
                print(f'[SKIP] TIF file already exists: {tif_path}. Skipping TIF generation step.')
                return out_dtm
            else:
                _generate_tif_from_dtm(out_dtm, print_info, overwrite)
        return out_dtm
    options = []
    if extra_params:
        options.extend(extra_params.split())
    options_str = ' '.join(options)
    cmd = (
        f'& "{exe_path}" {options_str} "{out_dtm}" "{cell_size}" "{xyunits}" "{zunits}" "{coordsys}" "{zone}" "{horizdatum}" "{vertdatum}" "{ground_las_path}"'
    )
    if print_info:
        print('Running GridSurfaceCreate with the following parameters:')
        print(f'  Fusion directory: {fusion_dir}')
        print(f'  GridSurfaceCreate exe: {exe_path}')
        print(f'  Ground LAS:      {ground_las_path}')
        print(f'  Output root:     {output_root}')
        print(f'  Output folder:   {dtm_output_folder}')
        print(f'  Output DTM:      {out_dtm}')
        print(f'  Cell size:       {cell_size}')
        print(f'  XY units:        {xyunits}')
        print(f'  Z units:         {zunits}')
        print(f'  CoordSys:        {coordsys}')
        print(f'  Zone:            {zone}')
        print(f'  HorizDatum:      {horizdatum}')
        print(f'  VertDatum:       {vertdatum}')
        print(f'  Extra params:    {extra_params}')
        print(f'  Overwrite:       {overwrite}')
        print(f'  Generate TIF:    {generate_tif}')
        print('\nPowerShell command:')
        print(cmd)
    result = subprocess.run(['powershell', '-Command', cmd])
    if print_info:
        print('Return code:', result.returncode)
        if result.returncode == 0:
            print('DTM file created:', out_dtm)
        else:
            print('[ERROR] DTM generation failed.')
    if result.returncode == 0:
        if generate_tif:
            _generate_tif_from_dtm(out_dtm, print_info, overwrite)
        return out_dtm
    else:
        return None

def _generate_tif_from_dtm(dtm_path, print_info, overwrite):
    exe_path = os.path.join(fusion_dir, 'DTM2TIF64.exe')
    if not os.path.isfile(exe_path):
        exe_path = os.path.join(fusion_dir, 'DTM2TIF.exe')
    if not os.path.isfile(exe_path):
        if print_info:
            print('[ERROR] DTM2TIF executable not found in Fusion folder.')
        return
    tif_path = dtm_path.replace('.dtm', '.tif')
    if os.path.isfile(tif_path) and not overwrite:
        if print_info:
            print(f'[SKIP] TIF file already exists: {tif_path}. Skipping TIF generation step.')
        return
    cmd = f'& "{exe_path}" "{dtm_path}"'
    if print_info:
        print('Running DTM2TIF with the following parameters:')
        print(f'  DTM2TIF exe: {exe_path}')
        print(f'  Input DTM:   {dtm_path}')
        print(f'  Output TIF:  {tif_path}')
        print(f'  PowerShell command: {cmd}')
    result = subprocess.run(['powershell', '-Command', cmd])
    if result.returncode == 0 and os.path.isfile(tif_path):
        if print_info:
            print(f'  [OK] TIF file created: {tif_path}')
    else:
        if print_info:
            print(f'  [ERROR] TIF generation failed for {dtm_path}')


def process_single_las(
    las_file_path,
    shapefile_path,
    field_name,
    output_root,
    fusion_dir,
    overwrite=False
):
    print(f'\n=== Processing LAS file: {las_file_path} ===')
    # Set global for polyclip/groundfilter
    globals()['fusion_dir'] = fusion_dir
    # Ensure polyclip and other functions use the caller-provided output_root
    globals()['output_root'] = output_root
    # PolyClipData
    polyclip(
        las_file_path=las_file_path,
        shapefile_path=shapefile_path,
        field_name=field_name,
        multifile=True,
        verbose=True,
        print_info=True
    )
    ground_las = groundfilter(
        las_file_path=las_file_path,
        cell_size=10.0,
        gparam=None,
        wparam=None,
        iterations=8,
        print_info=True
    )
    if ground_las:
        generate_dtm(
            ground_las_path=ground_las,
            cell_size=10.0,
            xyunits='M',
            zunits='M',
            coordsys=1,
            zone=20,
            horizdatum=2,
            vertdatum=2,
            extra_params=None,
            print_info=True,
            generate_tif=True,
            overwrite=overwrite
        )
        las_base_name = os.path.splitext(os.path.basename(las_file_path))[0]
        las_folder = os.path.join(output_root, las_base_name)
        clipped_folder = os.path.join(las_folder, "clipped_to_polygon")
        dtm_folder = os.path.join(las_folder, "DTM")
        dtm_file = os.path.join(dtm_folder, f"{las_base_name}.dtm")
        normalized_files = normalize_las_files(
            input_folder=clipped_folder,
            ground_dtm=dtm_file,
            overwrite=overwrite,
            print_info=True
        )
        # Run CloudMetrics on normalized LAS files
        normalized_folder = os.path.join(las_folder, 'normalized')
        run_cloudmetrics(
            normalized_folder=normalized_folder,
            output_root=output_root,
            overwrite=overwrite,
            print_info=True
        )
        # Run GridMetrics on normalized LAS files
        run_gridmetrics(
            normalized_folder=normalized_folder,
            output_root=output_root,
            overwrite=overwrite,
            print_info=True
        )
    print(f'=== Finished processing: {las_file_path} ===\n')

if __name__ == "__main__":
    # User: set this to your input folder containing LAS files
    input_las_folder = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Airborne\Input"  # CHANGE THIS as needed
    shapefile_path = r"C:\Users\W0491597\Documents\Arun\Enhanced Forest Inventory\Data\Plot_Polygon\Plot_Buffer_11m.shp"
    field_name = "NAME"
    # Find all LAS files in input_las_folder
    las_files = [os.path.join(input_las_folder, f) for f in os.listdir(input_las_folder) if f.lower().endswith('.las')]
    print(f'Found {len(las_files)} LAS files in {input_las_folder}')
    for las_file in las_files:
        process_single_las(
            las_file_path=las_file,
            shapefile_path=shapefile_path,
            field_name=field_name,
            output_root=output_root,
            fusion_dir=fusion_dir,
            overwrite=overwrite
        )