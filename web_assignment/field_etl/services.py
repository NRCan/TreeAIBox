"""field_etl.services — STEP 1 of the TreeAIBox pipeline.

Cleans source field points, derives DBH from perimeter, builds the transect
line and boundary polygon, and exports a GeoPackage.

Everything is computed on the fly from the selected vector layer
(GDB / SHP / GeoPackage / GeoJSON); this project intentionally has no DB.
"""
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import geopandas as gpd
import pyogrio
from pyproj import Transformer
from scipy.spatial import ConvexHull
from shapely.geometry import LineString, MultiPoint, Point, Polygon

# Reuse the mother app's GDB/vector helpers and column-aliasing
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
import sys
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from semantic_field_assignment import find_column, resolve_gdb_path  # noqa: E402

DEFAULT_BUFFER_M = 5.0
MAX_BUFFER_M = 100.0
DBH_FROM_PERIMETER = True   # when no DBH col exists, dbh = perimeter / pi

from .csv_reader import (  # noqa: E402
    DEFAULT_ANCHOR_BEGIN,
    DEFAULT_ANCHOR_END,
    DEFAULT_ANCHOR_CRS,
    is_csv,
    read_field_points_csv,
)


def read_field_points_any(path, layer=None, derive_dbh=DBH_FROM_PERIMETER,
                          anchor_begin=DEFAULT_ANCHOR_BEGIN,
                          anchor_end=DEFAULT_ANCHOR_END,
                          anchor_crs=DEFAULT_ANCHOR_CRS):
    """Read field points from a vector file OR a CSV (transect-relative or generic)."""
    if is_csv(path):
        return read_field_points_csv(path, derive_dbh=derive_dbh,
                                     anchor_begin=anchor_begin, anchor_end=anchor_end,
                                     anchor_crs=anchor_crs)
    return read_field_points(path, layer=layer, derive_dbh=derive_dbh)


# ---------------------------------------------------------------------------
# Layer listing
# ---------------------------------------------------------------------------
def list_layers(path):
    resolved = resolve_gdb_path(path)
    if not resolved or not os.path.exists(resolved):
        raise FileNotFoundError(f"Path not found: {path}")
    # CSV source: expose as a single pseudo-layer
    if is_csv(resolved):
        return ["__csv__"], ""
    layers = pyogrio.list_layers(resolved)
    names = []
    for l in (layers.tolist() if hasattr(layers, "tolist") else layers):
        if isinstance(l, (list, tuple, np.ndarray)):
            names.append(str(l[0]))
        else:
            names.append(str(l))
    default = next((n for n in names if any(k in n.lower() for k in
                   ("stemcenter", "field_point", "tree", "stem"))), names[0] if names else "")
    return names, default


# ---------------------------------------------------------------------------
# Field point reading + cleaning
# ---------------------------------------------------------------------------
SIZE_COLS = ("perimeter", "perimeter_cm", "circumference", "circ_cm", "girth", "girth_cm", "circ")
DBH_COLS = ("dbh_cm", "dbh", "diameter_cm", "diameter", "dbh_mm", "diam_cm")
SPECIES_COLS = ("species", "specie", "tree_species", "botanical_name", "sp")
SIDE_COLS = ("side", "left_right", "lr")
Y_COLS = ("y_axis_m", "y_axis", "meter_on_y", "y_m", "dist_along", "along", "y_pos")
ID_COLS = ("treeid", "tree_id", "id", "tag_no", "tag", "fid", "pointid")

HEIGHT_CLASS_RANGES = {0: "?", 1: "<5m", 2: "5-10m", 3: "10-15m", 4: "15-20m", 5: ">20m"}


def _col(cols, candidates):
    return find_column(cols, candidates[0], list(candidates[1:]))


def read_field_points(path, layer=None, derive_dbh=DBH_FROM_PERIMETER):
    """Read a vector layer into cleaned field-point dicts."""
    resolved = resolve_gdb_path(path)
    gdf = pyogrio.read_dataframe(resolved, layer=layer)
    if gdf.empty:
        raise ValueError(f"Layer has no features: {layer}")

    cols = [str(c) for c in gdf.columns]
    src_crs = gdf.crs

    id_col = _col(cols, ID_COLS)
    dbh_col = _col(cols, DBH_COLS)
    size_col = _col(cols, SIZE_COLS)
    sp_col = _col(cols, SPECIES_COLS)
    side_col = _col(cols, SIDE_COLS)
    y_col = _col(cols, Y_COLS)
    hc_col = _col(cols, ("height_level", "hightlevel", "height_class", "class", "hc"))

    def num(v):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return None
        try:
            f = float(v)
            return f if np.isfinite(f) else None
        except (ValueError, TypeError):
            return None

    def txt(v):
        return None if v is None else str(v).strip() or None

    records = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        x, y = float(geom.x), float(geom.y)
        if not (np.isfinite(x) and np.isfinite(y)):
            continue

        tid = None
        if id_col:
            tid = row[id_col]
            if isinstance(tid, (np.integer, np.int64)):
                tid = int(tid)
            else:
                tid = txt(tid)
        if tid is None or tid == "":
            tid = str(idx + 1)

        dbh = num(row[dbh_col]) if dbh_col else None
        perim = num(row[size_col]) if size_col else None
        derived = False
        if dbh is None and perim is not None and derive_dbh and perim > 0:
            dbh = round(perim / math.pi, 2)
            derived = True

        hc = num(row[hc_col]) if hc_col else None
        hc = int(hc) if hc is not None and 0 <= hc <= 5 else None

        rec = {
            "fid": idx,
            "tree_id": str(tid),
            "x": x,
            "y": y,
            "dbh_cm": dbh,
            "perimeter_cm": perim,
            "dbh_derived": derived,
            "species": txt(row[sp_col]) if sp_col else None,
            "side": txt(row[side_col]) if side_col else None,
            "y_axis_m": num(row[y_col]) if y_col else None,
            "height_class": hc,
            "height_range": HEIGHT_CLASS_RANGES.get(hc) if hc is not None else None,
            "crs": str(src_crs) if src_crs else None,
            "raw": row.to_dict() if hasattr(row, "to_dict") else dict(row),
        }
        records.append(rec)
    return records


def flag_anomalies(records):
    """Attach an anomaly reason to each record (cleaning step)."""
    seen = set()
    dup_ids = {}
    for r in records:
        if r["tree_id"] in seen:
            dup_ids[r["tree_id"]] = dup_ids.get(r["tree_id"], 1) + 1
        seen.add(r["tree_id"])

    dbhs = [r["dbh_cm"] for r in records if r["dbh_cm"] is not None]
    q1 = float(np.percentile(dbhs, 25)) if len(dbhs) >= 4 else None
    q3 = float(np.percentile(dbhs, 75)) if len(dbhs) >= 4 else None
    iqr = (q3 - q1) if (q1 is not None and q3 is not None) else None

    for r in records:
        reasons = []
        if dup_ids.get(r["tree_id"], 1) > 1:
            reasons.append("duplicate tree id")
        if r["dbh_cm"] is None:
            reasons.append("missing dbh/perimeter")
        elif r["dbh_cm"] <= 0 or r["dbh_cm"] > 250:
            reasons.append(f"implausible dbh ({r['dbh_cm']:.1f} cm)")
        elif iqr and (r["dbh_cm"] < q1 - 3 * iqr or r["dbh_cm"] > q3 + 3 * iqr):
            reasons.append(f"dbh outlier ({r['dbh_cm']:.1f} cm)")
        if r["perimeter_cm"] is not None and (r["perimeter_cm"] <= 0 or r["perimeter_cm"] > 800):
            reasons.append(f"implausible perimeter ({r['perimeter_cm']:.1f} cm)")
        r["anomalies"] = reasons
        r["is_anomaly"] = len(reasons) > 0
    return records


# ---------------------------------------------------------------------------
# Metric helpers: work in a projected/metre CRS even when the source is WGS84
# ---------------------------------------------------------------------------
def _to_metric(records):
    """Return (metric_pts_array, metric_crs, back_transformer_or_None).

    If the source CRS is projected, points are used as-is (already metres).
    If it is geographic (e.g. WGS84), points are reprojected to an on-the-fly
    UTM zone based on the centroid longitude, so distance/buffer math is in
    metres; back maps the result to the source CRS.
    """
    src_crs = records[0]["crs"] if records else None
    from pyproj import CRS as P_CRS
    if src_crs:
        try:
            src_obj = P_CRS.from_user_input(src_crs)
            if src_obj.is_projected:
                pts = np.array([[r["x"], r["y"]] for r in records])
                return pts, src_obj, None
            lat = np.mean([r["y"] for r in records])
            lon = np.mean([r["x"] for r in records])
            zone = int((lon + 180) / 6) % 60 + 1
            metric = P_CRS.from_epsg(32600 + zone) if lat >= 0 else P_CRS.from_epsg(32700 + zone)
            tr = Transformer.from_crs(src_obj, metric, always_xy=True)
            pts = np.array([tr.transform(r["x"], r["y"]) for r in records])
            back = Transformer.from_crs(metric, src_obj, always_xy=True)
            return pts, metric, back
        except Exception:
            pass
    pts = np.array([[r["x"], r["y"]] for r in records])
    return pts, None, None


# ---------------------------------------------------------------------------
# Transect line + boundary polygon (native CRS math -> WGS84 output)
# ---------------------------------------------------------------------------
def transect_line(records, src_crs=None):
    """Return the transect line.

    If the records come from a transect-relative CSV, the reconstructed anchor
    begin->end segment is used (this reproduces the LiDAR-anchor line from the
    original workbook, ~20.85 m). Otherwise a principal-component best-fit axis
    through the points is used.
    """
    anchor_line = getattr(records, "anchor_line", None)
    if anchor_line:
        (ax, ay), (bx, by), acrs = anchor_line
        start = (float(ax), float(ay))
        end_ = (float(bx), float(by))
        length = np.hypot(bx - ax, by - ay)
        return {"start": start, "end": end_, "length_m": round(float(length), 2)}

    good = [r for r in records if np.isfinite(r["x"]) and np.isfinite(r["y"])]
    if len(good) < 2:
        return None
    pts, _, back = _to_metric(good)
    centroid = pts.mean(axis=0)
    cov = np.cov(pts.T)
    vals, vecs = np.linalg.eigh(cov)
    axis = vecs[:, np.argmax(vals)]
    proj = (pts - centroid) @ axis
    i_min, i_max = int(np.argmin(proj)), int(np.argmax(proj))
    start = tuple(pts[i_min])
    end_ = tuple(pts[i_max])
    length = float(np.linalg.norm(np.array(end_) - np.array(start)))
    if back is not None:
        start = back.transform(start[0], start[1])
        end_ = back.transform(end_[0], end_[1])
    return {"start": start, "end": end_, "length_m": round(length, 2)}


def boundary_polygon(records, buffer_m=DEFAULT_BUFFER_M):
    """Convex hull of all points buffered by buffer_m metres, returned in the
    SOURCE CRS for correct downstream projection to WGS84."""
    good = [r for r in records if np.isfinite(r["x"]) and np.isfinite(r["y"])]
    if len(good) < 3:
        return None
    pts_metric, _, back = _to_metric(good)
    hull = ConvexHull(pts_metric)
    ring = pts_metric[hull.vertices]
    poly = Polygon(ring).buffer(buffer_m)
    if back is not None:
        from shapely.geometry import Polygon as _P
        ext = list(poly.exterior.coords)
        ext_native = [back.transform(x, y) for x, y in ext]
        poly = _P(ext_native)
    return poly


def _transformer_to_wgs84(src_crs):
    if not src_crs:
        return None
    try:
        return Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
    except Exception:
        return None


def build_geojson(records, line, boundary, exclude_anomalies=True, src_crs=None):
    tr = _transformer_to_wgs84(src_crs or (records[0]["crs"] if records else None))
    def proj(x, y):
        if tr:
            try:
                lon, lat = tr.transform(x, y)
                return [float(lon), float(lat)]
            except Exception:
                return [float(x), float(y)]
        return [float(x), float(y)]

    features = []
    for r in records:
        if exclude_anomalies and r.get("is_anomaly"):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": proj(r["x"], r["y"])},
            "properties": {
                "tree_id": r["tree_id"],
                "dbh_cm": r["dbh_cm"],
                "perimeter_cm": r["perimeter_cm"],
                "dbh_derived": r["dbh_derived"],
                "species": r["species"] or "-",
                "side": r["side"] or "-",
                "y_axis_m": r["y_axis_m"],
                "height_class": r["height_class"],
                "height_range": r["height_range"] or "-",
                "flagged": r.get("is_anomaly", False),
                "anomalies": "; ".join(r.get("anomalies", [])) or "-",
            },
        })

    if line:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [proj(*line["start"]), proj(*line["end"])]},
            "properties": {"name": "Transect line", "length_m": line["length_m"]},
        })

    if boundary is not None:
        ext = list(boundary.exterior.coords)
        ring = [proj(x, y) for x, y in ext]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"name": "Boundary polygon"},
        })

    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# GeoPackage export: points + line + boundary
# ---------------------------------------------------------------------------
def build_gpkg_bytes(records, line, boundary, exclude_anomalies=True,
                     src_crs=None, buffer_m=DEFAULT_BUFFER_M):
    """Return GPKG bytes with layers: field_points, transect_line, boundary."""
    tr = _transformer_to_wgs84(src_crs or (records[0]["crs"] if records else None))
    def proj(x, y):
        if tr:
            try:
                lon, lat = tr.transform(x, y)
                return [float(lon), float(lat)]
            except Exception:
                return [float(x), float(y)]
        return [float(x), float(y)]

    # points
    pt_records = []
    for r in records:
        if exclude_anomalies and r.get("is_anomaly"):
            continue
        lon, lat = proj(r["x"], r["y"])
        pt_records.append({
            "tree_id": r["tree_id"],
            "species": r["species"] or "",
            "dbh_cm": r["dbh_cm"],
            "perimeter_cm": r["perimeter_cm"],
            "dbh_derived": r["dbh_derived"],
            "side": r["side"] or "",
            "y_axis_m": r["y_axis_m"],
            "height_class": r["height_class"],
            "flagged": r.get("is_anomaly", False),
            "anomalies": "; ".join(r.get("anomalies", [])) or "",
            "geometry": Point(lon, lat),
        })
    pts_gdf = gpd.GeoDataFrame(pt_records, geometry="geometry", crs="EPSG:4326")

    # line
    line_records = []
    if line:
        s = proj(*line["start"]); e = proj(*line["end"])
        line_records.append({"name": "Transect line", "length_m": line["length_m"],
                             "geometry": LineString([s, e])})
    line_gdf = gpd.GeoDataFrame(line_records, geometry="geometry", crs="EPSG:4326") if line_records else None

    # boundary
    bnd_records = []
    if boundary is not None:
        ring = [proj(x, y) for x, y in list(boundary.exterior.coords)]
        bnd_records.append({"name": "Boundary polygon", "buffer_m": buffer_m,
                            "geometry": Polygon(ring)})
    bnd_gdf = gpd.GeoDataFrame(bnd_records, geometry="geometry", crs="EPSG:4326") if bnd_records else None

    tmpdir = tempfile.mkdtemp(prefix="field_etl_")
    tmppath = os.path.join(tmpdir, "clean_export.gpkg")
    try:
        pts_gdf.to_file(tmppath, driver="GPKG", layer="field_points")
        if line_gdf is not None:
            line_gdf.to_file(tmppath, driver="GPKG", layer="transect_line")
        if bnd_gdf is not None:
            bnd_gdf.to_file(tmppath, driver="GPKG", layer="boundary")
        with open(tmppath, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmppath)
            os.rmdir(tmpdir)
        except OSError:
            pass


def build_cleaned_csv(records, exclude_anomalies=True):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["tree_id", "species", "dbh_cm", "perimeter_cm", "dbh_derived",
                "side", "y_axis_m", "height_class", "flagged", "anomalies", "x", "y"])
    for r in records:
        if exclude_anomalies and r.get("is_anomaly"):
            continue
        w.writerow([r["tree_id"], r["species"] or "", r["dbh_cm"], r["perimeter_cm"],
                    r["dbh_derived"], r["side"] or "", r["y_axis_m"], r["height_class"],
                    r.get("is_anomaly", False), "; ".join(r.get("anomalies", [])) or "",
                    round(r["x"], 4), round(r["y"], 4)])
    return buf.getvalue()
