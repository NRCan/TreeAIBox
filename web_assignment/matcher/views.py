import os
import sys
import json
import traceback
from pathlib import Path
from collections import defaultdict
import numpy as np

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from semantic_field_assignment import (
    resolve_gdb_path,
    read_field_points,
    read_lidar_metrics,
    match_trees,
    write_outputs,
    class_to_height_range,
    class_to_midpoint_height,
    clip_lidar_to_boundary,
    build_field_boundary,
    HEIGHT_CLASS_RANGES,
    HEIGHT_CLASS_MIDPOINTS
)


def index(request):
    """Render main SPA dashboard."""
    default_gdb = "C:/Users/arunb/Downloads/Field Data.gdb"
    
    # Auto-detect default metrics CSV if available
    export_dir = Path("C:/Users/arunb/Downloads/DataPack/export")
    default_metrics = ""
    if export_dir.exists():
        csvs = list(export_dir.glob("*trunk_metrics.csv")) + list(export_dir.glob("*.csv"))
        if csvs:
            default_metrics = str(csvs[0])
    if not default_metrics:
        default_metrics = "C:/Users/arunb/Downloads/DataPack/export/clipped_1_20260424_LLR_L3_treefilter_crownoff_normalized_trunk_metrics.csv"

    default_out = str(Path(default_metrics).parent / "field_assignment_out") if default_metrics else "C:/Users/arunb/Downloads/DataPack/export/field_assignment_out"

    context = {
        'default_gdb': default_gdb,
        'default_metrics': default_metrics,
        'default_out': default_out,
    }
    return render(request, 'matcher/index.html', context)


@csrf_exempt
def list_layers(request):
    """API to inspect GDB / GeoPackage / vector file and list available layers."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        raw_path = data.get('gdb_path', '').strip()
        if not raw_path:
            return JsonResponse({'status': 'error', 'message': 'gdb_path is required'}, status=400)

        resolved_path = resolve_gdb_path(raw_path)
        if not os.path.exists(resolved_path):
            return JsonResponse({'status': 'error', 'message': f'Path not found: {raw_path}'}, status=404)

        import pyogrio
        layers_info = pyogrio.list_layers(resolved_path)
        layer_names = [l[0] for l in layers_info] if len(layers_info) > 0 and isinstance(layers_info[0], (list, tuple, np.ndarray)) else list(layers_info)
        layer_names = [str(n) for n in layer_names]

        # Suggest best default layer
        default_layer = layer_names[0] if layer_names else ""
        for name in layer_names:
            nl = name.lower()
            if 'stemcenter' in nl or 'field_points' in nl or 'tree' in nl:
                default_layer = name
                break

        return JsonResponse({
            'status': 'ok',
            'resolved_path': resolved_path,
            'layers': layer_names,
            'default_layer': default_layer
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def scan_csvs(request):
    """API to inspect a directory or path and return all LiDAR CSV files."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        raw_path = data.get('folder_path', '').strip()
        if not raw_path:
            return JsonResponse({'status': 'error', 'message': 'folder_path is required'}, status=400)

        target_dir = Path(raw_path)
        if target_dir.is_file():
            target_dir = target_dir.parent

        if not target_dir.exists():
            return JsonResponse({'status': 'error', 'message': f'Directory not found: {raw_path}'}, status=404)

        found_files = []
        # Scan folder for .csv files
        for p in sorted(target_dir.glob("*.csv")):
            fname = p.name
            # Skip generated output files if they exist in same folder
            if fname.lower().startswith('field_assignment') or fname.lower().startswith('match_report'):
                continue
            
            size_kb = round(p.stat().st_size / 1024, 1)
            is_metrics = ('metric' in fname.lower() or 'trunk' in fname.lower() or 'tree' in fname.lower())
            
            found_files.append({
                'filename': fname,
                'path': str(p).replace('\\', '/'),
                'size_kb': size_kb,
                'is_metrics': is_metrics
            })

        # Also search one level of subdirectories if shallow search returned few
        if len(found_files) == 0:
            for p in sorted(target_dir.rglob("*.csv")):
                fname = p.name
                if fname.lower().startswith('field_assignment'):
                    continue
                found_files.append({
                    'filename': fname,
                    'path': str(p).replace('\\', '/'),
                    'size_kb': round(p.stat().st_size / 1024, 1),
                    'is_metrics': ('metric' in fname.lower() or 'trunk' in fname.lower())
                })

        return JsonResponse({
            'status': 'ok',
            'target_dir': str(target_dir).replace('\\', '/'),
            'files': found_files
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def pick_path(request):
    """API to trigger native desktop OS file/folder picker dialog."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body) if request.body else {}
        target_type = data.get('type', 'file')  # 'gdb', 'metrics', 'folder', 'file'
        initial_dir = data.get('initial_dir', '').strip()

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        selected_path = ""
        init_path = initial_dir if (initial_dir and os.path.exists(initial_dir)) else None

        if target_type == 'gdb':
            # GDB directory or vector file (.shp / .gpkg)
            selected_path = filedialog.askdirectory(title="Select Field Survey .gdb Directory", initialdir=init_path)
            if not selected_path:
                selected_path = filedialog.askopenfilename(
                    title="Or Select Field Survey File (.shp, .gpkg, .gdb)",
                    filetypes=[("Vector / GDB Files", "*.gdb *.shp *.gpkg *.geojson"), ("All Files", "*.*")],
                    initialdir=init_path
                )
        elif target_type == 'folder':
            selected_path = filedialog.askdirectory(title="Select Output Directory", initialdir=init_path)
        elif target_type == 'metrics':
            selected_path = filedialog.askopenfilename(
                title="Select LiDAR Metrics CSV File",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                initialdir=init_path
            )
            if not selected_path:
                selected_path = filedialog.askdirectory(title="Or Select Folder Containing Metrics CSVs", initialdir=init_path)
        else:
            selected_path = filedialog.askopenfilename(title="Select File", initialdir=init_path)

        root.destroy()

        if selected_path:
            selected_path = os.path.normpath(selected_path).replace("\\", "/")

        return JsonResponse({
            'status': 'ok',
            'path': selected_path
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def run_match(request):
    """Run tree assignment (single or batch multi-CSV) with dynamic exclusion filters and GeoJSON."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)

        gdb_path = data.get('gdb_path', '').strip()
        layer = data.get('layer', '').strip()
        metrics_path = data.get('metrics_path', '').strip()
        metrics_paths = data.get('metrics_paths', [])
        out_dir = data.get('out_dir', 'field_assignment_out').strip()

        tolerance = float(data.get('tolerance', 2.5))
        w_spatial = float(data.get('weight_spatial', 0.50))
        w_dbh = float(data.get('weight_dbh', 0.25))
        w_height = float(data.get('weight_height', 0.25))
        dbh_scale = float(data.get('dbh_scale', 12.0))
        method = data.get('method', 'optimal')

        # Boundary Filter (convex hull + buffer around field points, like Step 1)
        boundary_enabled = bool(data.get('boundary_enabled', True))
        boundary_buffer_m = float(data.get('boundary_buffer_m', 5.0))

        # Exclusion Filters
        min_hc = data.get('min_height_class')
        min_hc = int(min_hc) if min_hc is not None and str(min_hc).strip() != '' else 1

        max_hc = data.get('max_height_class')
        max_hc = int(max_hc) if max_hc is not None and str(max_hc).strip() != '' else 5

        min_dbh = data.get('min_dbh')
        min_dbh = float(min_dbh) if min_dbh is not None and str(min_dbh).strip() != '' else None

        max_dbh = data.get('max_dbh')
        max_dbh = float(max_dbh) if max_dbh is not None and str(max_dbh).strip() != '' else None

        species_filter = data.get('species_filter')

        # Resolve list of CSV files to process
        csv_list = []
        if metrics_paths and isinstance(metrics_paths, list):
            csv_list = [p for p in metrics_paths if os.path.exists(p)]
        elif metrics_path:
            p_obj = Path(metrics_path)
            if p_obj.is_dir():
                csv_list = [str(f) for f in p_obj.glob("*.csv") if not f.name.startswith("field_assignment")]
            elif p_obj.is_file():
                csv_list = [str(p_obj)]

        if not csv_list:
            return JsonResponse({'status': 'error', 'message': f'No valid LiDAR metrics CSV files found.'}, status=400)

        # Validate Field GDB
        if not gdb_path or not os.path.exists(resolve_gdb_path(gdb_path)):
            return JsonResponse({'status': 'error', 'message': f'Field data path invalid or not found: {gdb_path}'}, status=400)

        # 1. Read Field Data with Exclusion Filtering (once for all batch CSVs)
        field_trees = read_field_points(
            gdb_path=gdb_path,
            layer=layer if layer else None,
            min_height_class=min_hc,
            max_height_class=max_hc,
            min_dbh=min_dbh,
            max_dbh=max_dbh,
            species_filter=species_filter
        )
        if not field_trees:
            return JsonResponse({'status': 'error', 'message': 'No field trees found matching the specified filters.'}, status=400)

        datasets = {}
        batch_summary_list = []

        is_multi = len(csv_list) > 1

        for idx, single_csv in enumerate(csv_list):
            csv_name = Path(single_csv).name
            file_id = f"ds_{idx}_{Path(single_csv).stem[:20]}"
            
            # Create subfolder for each dataset if running batch
            target_out_dir = os.path.join(out_dir, f"batch_{Path(single_csv).stem}") if is_multi else out_dir

            # Read LiDAR metrics
            lidar_trees = read_lidar_metrics(metrics_path=single_csv)
            if not lidar_trees:
                continue

            # ------------------------------------------------------------------
            # Boundary Filter: clip LiDAR to buffered field-survey boundary
            # (convex hull of field points + buffer, mirrors Step-1 boundary_polygon)
            # ------------------------------------------------------------------
            n_lidar_raw = len(lidar_trees)
            boundary_geom = None

            if boundary_enabled:
                try:
                    lidar_trees, boundary_geom = clip_lidar_to_boundary(
                        lidar_trees, field_trees, buffer_m=boundary_buffer_m
                    )
                except Exception as hull_err:
                    # Non-fatal: fall back to unclipped LiDAR
                    print(f"[WARN] Boundary clipping failed: {hull_err}")

            n_lidar_clipped = n_lidar_raw - len(lidar_trees)

            # Match
            assignments = match_trees(
                field_trees=field_trees,
                lidar_trees=lidar_trees,
                tolerance_m=tolerance,
                weight_spatial=w_spatial,
                weight_dbh=w_dbh,
                weight_height=w_height,
                dbh_scale_cm=dbh_scale,
                method=method
            )

            # Write outputs
            write_outputs(
                assignments=assignments,
                lidar_trees=lidar_trees,
                field_trees=field_trees,
                out_dir=target_out_dir,
                export_geojson=True
            )

            # Read report
            report_file = os.path.join(target_out_dir, 'match_report.txt')
            report_text = ""
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_text = f.read()

            # GeoJSON
            geojson_data = build_leaflet_geojson(assignments, lidar_trees, field_trees)

            # Append boundary polygon as a GeoJSON feature (projected metres → WGS84)
            if boundary_geom is not None and boundary_geom.get('polygon') is not None:
                try:
                    from pyproj import Transformer as _T
                    src_crs = boundary_geom.get('crs') or (field_trees[0].get('crs') if field_trees else None)
                    _xf = _T.from_crs(src_crs, 'EPSG:4326', always_xy=True) if src_crs else None

                    def _proj(x, y):
                        if _xf:
                            lon, lat = _xf.transform(float(x), float(y))
                            return [float(lon), float(lat)]
                        return [float(x), float(y)]

                    ext = list(boundary_geom['polygon'].exterior.coords)
                    ring_wgs84 = [_proj(p[0], p[1]) for p in ext]

                    geojson_data['features'].append({
                        'type': 'Feature',
                        'geometry': {'type': 'Polygon', 'coordinates': [ring_wgs84]},
                        'properties': {
                            'type': 'field_boundary',
                            'label': 'Field Boundary (%sm buffer)' % boundary_geom['buffer_m'],
                            'lidar_raw': n_lidar_raw,
                            'lidar_after_clip': len(lidar_trees),
                            'lidar_clipped_out': n_lidar_clipped
                        }
                    })
                except Exception:
                    pass

            # Metrics
            matched = [a for a in assignments if a.get('lidar_tree_id') is not None and a.get('field_treeid') is not None]
            unmatched_lidar = [a for a in assignments if a.get('lidar_tree_id') is not None and a.get('field_treeid') is None]
            unmatched_field = [a for a in assignments if a.get('lidar_tree_id') is None and a.get('field_treeid') is not None]

            n_matched = len(matched)
            n_lidar = len(lidar_trees)
            n_field = len(field_trees)

            dists = [a['distance_m'] for a in matched if a.get('distance_m') is not None]
            scores = [a['score'] for a in matched if a.get('score') is not None]
            dbh_pairs = [(a['lidar_dbh_cm'], a['field_dbh_cm']) for a in matched
                         if a.get('lidar_dbh_cm') is not None and a.get('field_dbh_cm') is not None]

            dbh_mae = None
            dbh_rmse = None
            dbh_corr = None
            if dbh_pairs:
                l_dbhs = np.array([p[0] for p in dbh_pairs])
                f_dbhs = np.array([p[1] for p in dbh_pairs])
                diffs = l_dbhs - f_dbhs
                dbh_mae = float(np.mean(np.abs(diffs)))
                dbh_rmse = float(np.sqrt(np.mean(diffs**2)))
                if len(dbh_pairs) > 2 and np.std(l_dbhs) > 1e-4 and np.std(f_dbhs) > 1e-4:
                    dbh_corr = float(np.corrcoef(l_dbhs, f_dbhs)[0, 1])

            # Confusion Matrix
            conf = defaultdict(lambda: defaultdict(int))
            for a in matched:
                fc = a.get('field_height_class')
                lc = a.get('lidar_height_class')
                if fc and lc and 1 <= fc <= 5 and 1 <= lc <= 5:
                    conf[fc][lc] += 1
            conf_matrix = [[conf[r][c] for c in range(1, 6)] for r in range(1, 6)]

            # Table rows
            table_rows = []
            for a in assignments:
                tid = a.get('lidar_tree_id')
                fid = a.get('field_treeid')
                dist = a.get('distance_m')
                score = a.get('score')
                l_dbh = a.get('lidar_dbh_cm')
                f_dbh = a.get('field_dbh_cm')
                dbh_diff = (l_dbh - f_dbh) if (l_dbh is not None and f_dbh is not None) else None
                l_ht = a.get('lidar_height_m')
                l_hc = a.get('lidar_height_class')
                f_hc = a.get('field_height_class')
                sp = a.get('field_species')

                table_rows.append({
                    'dataset_id': file_id,
                    'dataset_filename': csv_name,
                    'lidar_id': tid if tid is not None else None,
                    'field_id': fid if fid is not None else None,
                    'distance_m': round(dist, 2) if dist is not None else None,
                    'score': round(score, 3) if score is not None else None,
                    'lidar_dbh_cm': round(l_dbh, 1) if l_dbh is not None else None,
                    'field_dbh_cm': round(f_dbh, 1) if f_dbh is not None else None,
                    'dbh_diff_cm': round(dbh_diff, 1) if dbh_diff is not None else None,
                    'lidar_height_m': round(l_ht, 2) if l_ht is not None else None,
                    'lidar_height_class': l_hc if l_hc else None,
                    'field_height_class': f_hc if f_hc else None,
                    'lidar_height_range': class_to_height_range(l_hc) if l_hc else None,
                    'field_height_range': class_to_height_range(f_hc) if f_hc else None,
                    'species': sp or "-",
                    'status': 'matched' if (tid is not None and fid is not None) else ('unmatched_lidar' if fid is None else 'unmatched_field')
                })

            n_lidar = len(lidar_trees)  # post-clip count used for all rate calculations

            summary = {
                'filename': csv_name,
                'path': single_csv,
                'total_field': n_field,
                'total_lidar': n_lidar,
                'total_lidar_raw': n_lidar_raw,
                'lidar_clipped_out': n_lidar_clipped,
                'boundary_buffer_m': boundary_buffer_m,
                'boundary_enabled': boundary_enabled,
                'matched_count': n_matched,
                'lidar_match_rate': round((n_matched / max(n_lidar, 1)) * 100, 1),
                'field_match_rate': round((n_matched / max(n_field, 1)) * 100, 1),
                'unmatched_lidar_count': len(unmatched_lidar),
                'unmatched_field_count': len(unmatched_field),
                'mean_distance_m': round(float(np.mean(dists)), 2) if dists else None,
                'median_distance_m': round(float(np.median(dists)), 2) if dists else None,
                'mean_score': round(float(np.mean(scores)), 4) if scores else None,
                'dbh_mae_cm': round(dbh_mae, 1) if dbh_mae is not None else None,

                'dbh_rmse_cm': round(dbh_rmse, 1) if dbh_rmse is not None else None,
                'dbh_corr': round(dbh_corr, 3) if dbh_corr is not None else None,
            }

            datasets[file_id] = {
                'id': file_id,
                'filename': csv_name,
                'path': single_csv,
                'summary': summary,
                'confusion_matrix': conf_matrix,
                'table_rows': table_rows,
                'geojson': geojson_data,
                'report_text': report_text,
                'csv_path': os.path.join(target_out_dir, 'field_assignment.csv'),
                'report_path': report_file,
            }

            batch_summary_list.append({
                'id': file_id,
                'filename': csv_name,
                'total_lidar': n_lidar,
                'matched_count': n_matched,
                'lidar_match_rate': summary['lidar_match_rate'],
                'field_match_rate': summary['field_match_rate'],
                'mean_distance_m': summary['mean_distance_m'],
                'dbh_mae_cm': summary['dbh_mae_cm'],
                'dbh_corr': summary['dbh_corr']
            })

        if not datasets:
            return JsonResponse({'status': 'error', 'message': 'No valid datasets could be processed.'}, status=400)

        first_id = list(datasets.keys())[0]
        first_ds = datasets[first_id]

        return JsonResponse({
            'status': 'ok',
            'is_batch': is_multi,
            'batch_summary': batch_summary_list,
            'datasets': datasets,
            'active_id': first_id,
            # Direct access defaults for single-dataset
            'summary': first_ds['summary'],
            'confusion_matrix': first_ds['confusion_matrix'],
            'table_rows': first_ds['table_rows'],
            'geojson': first_ds['geojson'],
            'report_text': first_ds['report_text'],
            'csv_path': first_ds['csv_path'],
            'report_path': first_ds['report_path'],
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def build_leaflet_geojson(assignments, lidar_trees, field_trees):
    """Build a WGS84 GeoJSON FeatureCollection containing lines, LiDAR points, and Field points."""
    from pyproj import Transformer

    source_crs = field_trees[0].get('crs') if field_trees else None
    transformer = None
    if source_crs:
        try:
            transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
        except Exception:
            transformer = None

    def _to_wgs84(xy):
        if xy is None:
            return None
        x, y = float(xy[0]), float(xy[1])
        if transformer:
            try:
                lon, lat = transformer.transform(x, y)
                return [float(lon), float(lat)]
            except Exception:
                return [x, y]
        return [x, y]

    features = []

    # 1. Add Matched Vector Lines
    for a in assignments:
        if a.get('lidar_tree_id') is not None and a.get('field_treeid') is not None:
            l_coords = _to_wgs84(a.get('lidar_xy'))
            f_coords = _to_wgs84(a.get('field_xy'))
            if l_coords and f_coords:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [l_coords, f_coords]
                    },
                    "properties": {
                        "type": "match_line",
                        "lidar_id": a['lidar_tree_id'],
                        "field_id": str(a['field_treeid']),
                        "distance_m": round(a['distance_m'], 2) if a.get('distance_m') is not None else None,
                        "score": round(a['score'], 3) if a.get('score') is not None else None,
                        "lidar_dbh": a.get('lidar_dbh_cm'),
                        "field_dbh": a.get('field_dbh_cm'),
                        "lidar_class": a.get('lidar_height_class'),
                        "field_class": a.get('field_height_class'),
                        "species": a.get('field_species') or '',
                    }
                })

    # 2. Add LiDAR Tree Points
    for tid, lt in lidar_trees.items():
        coords = _to_wgs84(lt['centroid_xy'])
        if coords:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coords
                },
                "properties": {
                    "type": "lidar_point",
                    "tree_id": tid,
                    "height_m": round(lt['height_m'], 2) if lt.get('height_m') is not None else None,
                    "height_class": lt.get('height_class'),
                    "dbh_cm": round(lt['dbh_cm'], 1) if lt.get('dbh_cm') is not None else None,
                    "volume_m3": round(lt['volume_m3'], 3) if lt.get('volume_m3') is not None else None,
                    "n_points": lt.get('n_points', 0)
                }
            })

    # 3. Add Field Survey Tree Points
    for ft in field_trees:
        coords = _to_wgs84(ft['xy'])
        if coords:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coords
                },
                "properties": {
                    "type": "field_point",
                    "field_id": str(ft['field_treeid']),
                    "height_class": ft.get('height_class'),
                    "height_range": ft.get('height_range'),
                    "dbh_cm": round(ft['dbh_cm'], 1) if ft.get('dbh_cm') is not None else None,
                    "species": ft.get('species') or '-',
                    "crown_class": ft.get('crown_class'),
                    "health": ft.get('health')
                }
            })

    return {"type": "FeatureCollection", "features": features}


def download_file(request):
    """Download output CSV or report file."""
    path = request.GET.get('path', '').strip()
    if not path or not os.path.exists(path):
        raise Http404("File not found")

    filename = os.path.basename(path)
    response = FileResponse(open(path, 'rb'), as_attachment=True, filename=filename)
    return response


@csrf_exempt
def load_custom_layer(request):
    """API to load a custom point/vector layer from GDB or vector file as WGS84 GeoJSON."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        raw_path = data.get('gdb_path', '').strip()
        layer_name = data.get('layer', '').strip()

        if not raw_path:
            return JsonResponse({'status': 'error', 'message': 'gdb_path is required'}, status=400)

        resolved_path = resolve_gdb_path(raw_path)
        if not os.path.exists(resolved_path):
            return JsonResponse({'status': 'error', 'message': f'Path not found: {raw_path}'}, status=404)

        import pyogrio
        from pyproj import Transformer

        available_layers = pyogrio.list_layers(resolved_path)
        layer_names = [l[0] if isinstance(l, (list, tuple, np.ndarray)) else str(l) for l in available_layers]
        if not layer_name or layer_name not in layer_names:
            layer_name = layer_names[0] if layer_names else None

        if not layer_name:
            return JsonResponse({'status': 'error', 'message': 'No valid vector layers found'}, status=404)

        gdf = pyogrio.read_dataframe(resolved_path, layer=layer_name)
        if gdf.empty:
            return JsonResponse({
                'status': 'ok',
                'layer_name': layer_name,
                'attributes': [],
                'feature_count': 0,
                'geojson': {'type': 'FeatureCollection', 'features': []}
            })

        # Extract attribute column names (excluding geometry)
        attribute_cols = [str(col) for col in gdf.columns if col != 'geometry']

        # Setup CRS transformer to WGS84 (EPSG:4326)
        transformer = None
        if gdf.crs:
            try:
                transformer = Transformer.from_crs(gdf.crs, "EPSG:4326", always_xy=True)
            except Exception:
                transformer = None

        features = []
        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            # Compute point coordinate (centroid if polygon/multiline)
            centroid = geom.centroid if hasattr(geom, 'centroid') else geom
            x, y = float(centroid.x), float(centroid.y)

            if transformer:
                try:
                    lon, lat = transformer.transform(x, y)
                    coords = [float(lon), float(lat)]
                except Exception:
                    coords = [x, y]
            else:
                coords = [x, y]

            # Collect serializable properties
            props = {}
            for col in attribute_cols:
                val = row[col]
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    props[col] = None
                elif isinstance(val, (np.integer, np.int64, np.int32)):
                    props[col] = int(val)
                elif isinstance(val, (np.floating, np.float64, np.float32)):
                    props[col] = float(val)
                elif hasattr(val, 'isoformat'):
                    props[col] = val.isoformat()
                else:
                    props[col] = str(val)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coords
                },
                "properties": props
            })

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return JsonResponse({
            'status': 'ok',
            'layer_name': layer_name,
            'attributes': attribute_cols,
            'feature_count': len(features),
            'geojson': geojson
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def boundary_preview(request):
    """API to preview the field-survey boundary polygon (convex hull + buffer)
    as WGS84 GeoJSON, so the map can live-update while the user drags the
    boundary-buffer slider. Mirrors field_etl's /api/boundary/ but uses the
    matcher's own field-point reading + exclusion filters for consistency."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        gdb_path = data.get('gdb_path', '').strip()
        layer = data.get('layer', '').strip()
        buffer_m = float(data.get('buffer_m', 5.0))

        # Same exclusion filters as run_match
        min_hc = data.get('min_height_class')
        min_hc = int(min_hc) if min_hc is not None and str(min_hc).strip() != '' else 1
        max_hc = data.get('max_height_class')
        max_hc = int(max_hc) if max_hc is not None and str(max_hc).strip() != '' else 5
        min_dbh = data.get('min_dbh')
        min_dbh = float(min_dbh) if min_dbh is not None and str(min_dbh).strip() != '' else None
        max_dbh = data.get('max_dbh')
        max_dbh = float(max_dbh) if max_dbh is not None and str(max_dbh).strip() != '' else None
        species_filter = data.get('species_filter')

        if not gdb_path or not os.path.exists(resolve_gdb_path(gdb_path)):
            return JsonResponse({'status': 'error', 'message': 'Field data path invalid'}, status=400)

        field_trees = read_field_points(
            gdb_path=gdb_path,
            layer=layer if layer else None,
            min_height_class=min_hc,
            max_height_class=max_hc,
            min_dbh=min_dbh,
            max_dbh=max_dbh,
            species_filter=species_filter
        )
        if not field_trees:
            return JsonResponse({'status': 'ok', 'field_count': 0, 'geojson': None})

        boundary = build_field_boundary(field_trees, buffer_m=buffer_m)
        polygon = boundary.get('polygon')
        if polygon is None:
            return JsonResponse({'status': 'ok', 'field_count': len(field_trees), 'geojson': None})

        # Reproject boundary ring to WGS84 for the Leaflet map
        from pyproj import Transformer as _T
        src_crs = boundary.get('crs') or field_trees[0].get('crs')
        _xf = _T.from_crs(src_crs, 'EPSG:4326', always_xy=True) if src_crs else None

        def _proj(x, y):
            if _xf:
                lon, lat = _xf.transform(float(x), float(y))
                return [float(lon), float(lat)]
            return [float(x), float(y)]

        ring = [_proj(p[0], p[1]) for p in list(polygon.exterior.coords)]
        geojson = {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [ring]},
                'properties': {
                    'type': 'field_boundary',
                    'label': 'Field Boundary (%.1fm buffer)' % buffer_m,
                    'buffer_m': boundary['buffer_m'],
                    'field_count': len(field_trees),
                }
            }]
        }
        return JsonResponse({
            'status': 'ok',
            'field_count': len(field_trees),
            'buffer_m': boundary['buffer_m'],
            'geojson': geojson,
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

