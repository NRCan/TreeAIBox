"""field_etl.views — STEP-1 webpage + APIs.

Webpage:  /field-etl/   (clean field points -> export GPKG/GeoJSON/CSV)
"""
import json
import math
import os
import traceback

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .services import (
    DEFAULT_ANCHOR_BEGIN,
    DEFAULT_ANCHOR_END,
    DEFAULT_ANCHOR_CRS,
    DEFAULT_BUFFER_M,
    MAX_BUFFER_M,
    build_cleaned_csv,
    build_gpkg_bytes,
    build_geojson,
    boundary_polygon,
    flag_anomalies,
    list_layers,
    read_field_points_any,
    transect_line,
)


def index(request):
    return render(request, "field_etl/index.html", {
        "default_source": "C:/Users/arunb/Downloads/20260727/Arun_Analysis/ETL/transect1_cleaned.csv",
        "default_buffer": DEFAULT_BUFFER_M,
    })


@csrf_exempt
def api_pick(request):
    """POST -> opens native file/folder picker (tkinter)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        initial = (json.loads(request.body or b"{}").get("initial_dir") or "").strip()
        init = initial if (initial and os.path.exists(initial)) else None
        path = filedialog.askopenfilename(
            title="Select Field Vector Dataset",
            filetypes=[("Vector / GeoData", "*.gdb *.shp *.gpkg *.geojson"), ("All Files", "*.*")],
            initialdir=init,
        )
        root.destroy()
        if path:
            path = os.path.normpath(path).replace("\\", "/")
        return JsonResponse({"status": "ok", "path": path or ""})
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


@csrf_exempt
def api_list_layers(request):
    """POST {path} -> {layers, default_layer}"""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    try:
        data = json.loads(request.body or b"{}")
        raw = (data.get("path") or "").strip()
        if not raw:
            return JsonResponse({"status": "error", "message": "path required"}, status=400)
        layers, default = list_layers(raw)
        return JsonResponse({"status": "ok", "path": raw, "layers": layers, "default_layer": default})
    except Exception as exc:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


@csrf_exempt
def api_process(request):
    """POST {path, layer, derive_dbh} -> {geojson, stats, anomalies, line, source_crs}"""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    try:
        data = json.loads(request.body or b"{}")
        raw = (data.get("path") or "").strip()
        layer = (data.get("layer") or "").strip() or None
        derive = bool(data.get("derive_dbh", True))
        if not raw:
            return JsonResponse({"status": "error", "message": "path required"}, status=400)

        records = read_field_points_any(raw, layer=layer, derive_dbh=derive)
        if not records:
            return JsonResponse({"status": "error", "message": "No usable field points in layer"}, status=400)
        flag_anomalies(records)

        line = transect_line(records)
        boundary = boundary_polygon(records, buffer_m=float(data.get("buffer_m", DEFAULT_BUFFER_M)))
        geojson = build_geojson(records, line, boundary, exclude_anomalies=False)

        all_count = len(records)
        clean_count = sum(1 for r in records if not r.get("is_anomaly"))
        anomaly_list = [
            {"tree_id": r["tree_id"], "dbh_cm": r["dbh_cm"],
             "anomalies": r.get("anomalies", [])}
            for r in records if r.get("is_anomaly")
        ]
        derived_count = sum(1 for r in records if r.get("dbh_derived"))

        return JsonResponse({
            "status": "ok",
            "path": raw,
            "layer": layer,
            "source_crs": records[0]["crs"] if records else None,
            "geojson": geojson,
            "stats": {
                "total": all_count,
                "clean": clean_count,
                "anomalies": len(anomaly_list),
                "dbh_from_perimeter": derived_count,
            },
            "anomalies": anomaly_list,
            "line": line,
        })
    except Exception as exc:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


@csrf_exempt
def api_boundary(request):
    """POST {path, layer, buffer_m} -> boundary GeoJSON polygon (recompute on slider)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    try:
        data = json.loads(request.body or b"{}")
        raw = (data.get("path") or "").strip()
        layer = (data.get("layer") or "").strip() or None
        buffer_m = float(data.get("buffer_m", DEFAULT_BUFFER_M))
        buffer_m = max(0.0, min(MAX_BUFFER_M, buffer_m))
        derive = bool(data.get("derive_dbh", True))
        if not raw:
            return JsonResponse({"status": "error", "message": "path required"}, status=400)

        records = read_field_points_any(raw, layer=layer, derive_dbh=derive)
        flag_anomalies(records)
        line = transect_line(records)
        boundary = boundary_polygon(records, buffer_m=buffer_m)
        geojson = build_geojson(records, line, boundary, exclude_anomalies=False)
        polys = [f for f in geojson["features"] if f["geometry"]["type"] == "Polygon"]
        return JsonResponse({
            "status": "ok",
            "buffer_m": buffer_m,
            "polygon": polys[0] if polys else None,
        })
    except Exception as exc:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


def export_gpkg(request):
    """GET ?path=&layer=&buffer=&exclude=1 -> .gpkg download (points+line+boundary)."""
    try:
        raw = (request.GET.get("path") or "").strip()
        layer = (request.GET.get("layer") or "").strip() or None
        buffer_m = float(request.GET.get("buffer", DEFAULT_BUFFER_M))
        buffer_m = max(0.0, min(MAX_BUFFER_M, buffer_m))
        exclude = request.GET.get("exclude", "1").lower() not in ("0", "false", "no")
        derive = request.GET.get("derive_dbh", "1").lower() not in ("0", "false", "no")
        if not raw:
            raise Http404("path parameter missing")
        records = read_field_points_any(raw, layer=layer, derive_dbh=derive)
        flag_anomalies(records)
        line = transect_line(records)
        boundary = boundary_polygon(records, buffer_m=buffer_m)
        payload = build_gpkg_bytes(records, line, boundary,
                                   exclude_anomalies=exclude,
                                   src_crs=records[0]["crs"] if records else None,
                                   buffer_m=buffer_m)
        resp = HttpResponse(payload, content_type="application/geopackage+vnd.sqlite3")
        resp["Content-Disposition"] = 'attachment; filename="field_etl_clean.gpkg"'
        return resp
    except Exception as exc:
        traceback.print_exc()
        raise Http404(f"GPKG export failed: {exc}") from exc


def export_geojson(request):
    """GET ?path=&layer=&exclude=1 -> .geojson download."""
    try:
        raw = (request.GET.get("path") or "").strip()
        layer = (request.GET.get("layer") or "").strip() or None
        buffer_m = float(request.GET.get("buffer", DEFAULT_BUFFER_M))
        buffer_m = max(0.0, min(MAX_BUFFER_M, buffer_m))
        exclude = request.GET.get("exclude", "1").lower() not in ("0", "false", "no")
        derive = request.GET.get("derive_dbh", "1").lower() not in ("0", "false", "no")
        if not raw:
            raise Http404("path parameter missing")
        records = read_field_points_any(raw, layer=layer, derive_dbh=derive)
        flag_anomalies(records)
        line = transect_line(records)
        boundary = boundary_polygon(records, buffer_m=buffer_m)
        gj = build_geojson(records, line, boundary, exclude_anomalies=exclude)
        resp = HttpResponse(json.dumps(gj, indent=2), content_type="application/geo+json")
        resp["Content-Disposition"] = 'attachment; filename="field_etl_clean.geojson"'
        return resp
    except Exception as exc:
        traceback.print_exc()
        raise Http404(f"GeoJSON export failed: {exc}") from exc


def export_csv(request):
    """GET ?path=&layer=&exclude=1 -> .csv download of the clean points."""
    try:
        raw = (request.GET.get("path") or "").strip()
        layer = (request.GET.get("layer") or "").strip() or None
        exclude = request.GET.get("exclude", "1").lower() not in ("0", "false", "no")
        derive = request.GET.get("derive_dbh", "1").lower() not in ("0", "false", "no")
        if not raw:
            raise Http404("path parameter missing")
        records = read_field_points_any(raw, layer=layer, derive_dbh=derive)
        flag_anomalies(records)
        text = build_cleaned_csv(records, exclude_anomalies=exclude)
        resp = HttpResponse(text, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="field_etl_clean.csv"'
        return resp
    except Exception as exc:
        traceback.print_exc()
        raise Http404(f"CSV export failed: {exc}") from exc
