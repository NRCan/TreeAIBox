"""CSV reader for field_etl."""
import csv, math
from pathlib import Path
import numpy as np
from pyproj import Transformer
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from semantic_field_assignment import find_column

DEFAULT_ANCHOR_BEGIN = (335537.194, 4982784.652)
DEFAULT_ANCHOR_END = (335553.26499, 4982797.43999)
DEFAULT_ANCHOR_CRS = "EPSG:2961"
HEIGHT_CLASS_RANGES = {0:"?",1:"<5m",2:"5-10m",3:"10-15m",4:"15-20m",5:">20m"}

def _csv_headers(path):
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        rdr = csv.reader(f)
        try:
            return next(rdr)
        except StopIteration:
            return []

def is_csv(path):
    return (path.lower().endswith((".csv",".txt")) or (Path(path).is_file() and bool(_csv_headers(path))))

def _head(cols, exact, aliases):
    return find_column(cols, exact, list(aliases))

def _num(v):
    if v is None: return None
    v = str(v).strip()
    if v in ("","NA","N/A","NULL") or (len(v)==1 and ord(v)==92): return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (ValueError, TypeError):
        return None

def _txt(v):
    if v is None: return None
    s = str(v).strip()
    return s or None

class Records(list):
    """A list of field-point dicts that can carry metadata (e.g. anchor_line)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.anchor_line = None
        self.is_transect_relative = False


def read_field_points_csv(path, derive_dbh=True, anchor_begin=DEFAULT_ANCHOR_BEGIN, anchor_end=DEFAULT_ANCHOR_END, anchor_crs=DEFAULT_ANCHOR_CRS):
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty: " + str(path))
    cols = [str(k).strip() for k in (reader.fieldnames or [])]

    id_col = _head(cols, "Tree ID", ["treeid","tree_id","id","tag_no","tag"])
    sp_col = _head(cols, "Species", ["species","specie","sp","tree_species","botanical_name"])
    dbh_col = _head(cols, "DBH", ["dbh_cm","dbh","diameter_cm","diameter","diam_cm"])
    size_col = _head(cols, "Tree perimeter(cm)", ["perimeter_cm","perimeter","circumference","circ_cm","girth_cm"])
    side_col = _head(cols, "Side", ["side","left_right","lr"])
    y_col = _head(cols, "y-axis(m)", ["y_axis_m","y_axis","y_m","dist_along","meter_on_y","along"])
    x_col = _head(cols, "x-axis(m)", ["x_axis_m","x_axis","x_m","perp_offset","distance_from"])
    lon_col = _head(cols, "lon", ["longitude","lon","x","long"])
    lat_col = _head(cols, "lat", ["latitude","lat","y","lat_deg"])
    hc_col = _head(cols, "Height Level", ["height_level","hightlevel","height_class","class","hc"])

    def detect_xy():
        if lon_col and lat_col and any(_num(r.get(lon_col)) is not None for r in rows):
            return ("lonlat", lon_col, lat_col)
        xcols = [c for c in ("x","x_m","easting","easting_m","utmx") if find_column(cols, c, [])]
        ycols = [c for c in ("y","y_m","northing","northing_m","utmy") if find_column(cols, c, [])]
        if xcols and ycols and any(_num(r.get(xcols[0])) is not None for r in rows):
            return ("xy", xcols[0], ycols[0])
        return None

    xy = detect_xy()
    is_transect = (not xy) and bool(side_col) and bool(y_col) and bool(x_col)

    reconstruct = None
    if is_transect:
        from pyproj import CRS as PCCRS
        try:
            src = PCCRS.from_user_input(anchor_crs)
            projected = bool(src.is_projected)
        except Exception:
            src = None; projected = False
        a0 = tuple(float(v) for v in anchor_begin)
        b0 = tuple(float(v) for v in anchor_end)
        if not projected:
            mlat = (a0[1]+b0[1])/2.0; mlon = (a0[0]+b0[0])/2.0
            zone = int((mlon+180)/6)%60 + 1
            metric = PCCRS.from_epsg(32600+zone if mlat>=0 else 32700+zone)
            to_m = Transformer.from_crs(src or "EPSG:4326", metric, always_xy=True)
            a0 = tuple(to_m.transform(*a0)); b0 = tuple(to_m.transform(*b0))
        a = np.array(a0, float); b = np.array(b0, float)
        d = b - a; L = float(np.hypot(*d))
        if L <= 0: raise ValueError("Begin/End anchors coincide; cannot reconstruct positions.")
        ux, uy = d / L
        # Normal vector pointing LEFT (-uy, ux) and RIGHT (uy, -ux)
        # When facing from begin (A) to end (B):
        # Left is rotated 90° CCW (-uy, ux); Right is rotated 90° CW (uy, -ux)
        px_left, py_left = -uy, ux
        def rec(y_m, side, x_m):
            is_left = not (side and str(side).strip().lower() in ("right", "r"))
            sign = 1.0 if is_left else -1.0
            return a[0] + ux * y_m + px_left * (sign * x_m), a[1] + uy * y_m + py_left * (sign * x_m)
        reconstruct = rec

    records = []
    for i, row in enumerate(rows):
        if not any(str(v).strip() for v in (row or {}).values()):
            continue
        tid = _txt(row.get(id_col)) if id_col else None
        if tid is None: tid = str(i+1)
        perim = _num(row.get(size_col)) if size_col else None
        dbh = _num(row.get(dbh_col)) if dbh_col else None
        derived = False
        if dbh is None and perim is not None and derive_dbh and perim > 0:
            dbh = round(perim/math.pi, 2); derived = True
        hc = _num(row.get(hc_col)) if hc_col else None
        hc = int(hc) if hc is not None and 0 <= hc <= 5 else None
        if is_transect:
            y_m = _num(row.get(y_col)) or 0.0
            x_m = _num(row.get(x_col)) or 0.0
            side = _txt(row.get(side_col)) or "Left"
            ex_, ny_ = reconstruct(y_m, side, x_m)
            x, y = float(ex_), float(ny_); crs = str(anchor_crs)
        elif xy:
            kind, c1, c2 = xy
            a1 = _num(row.get(c1)); a2 = _num(row.get(c2))
            if a1 is None or a2 is None: continue
            x, y = a1, a2; crs = "EPSG:4326" if kind=="lonlat" else str(anchor_crs)
        else:
            continue
        records.append({
            "fid": i, "tree_id": str(tid),
            "x": float(x), "y": float(y),
            "dbh_cm": dbh, "perimeter_cm": perim, "dbh_derived": derived,
            "species": _txt(row.get(sp_col)) if sp_col else None,
            "side": _txt(row.get(side_col)) if side_col else None,
            "y_axis_m": _num(row.get(y_col)) if y_col else None,
            "height_class": hc,
            "height_range": HEIGHT_CLASS_RANGES.get(hc) if hc is not None else None,
            "crs": crs,
            "raw": {str(k).strip(): v for k, v in (row or {}).items() if k is not None},
        })
    out = Records(records)
    out.is_transect_relative = is_transect
    if is_transect:
        # the true survey transect line = the begin/end anchor segment (native CRS)
        out.anchor_line = (tuple(float(v) for v in anchor_begin),
                           tuple(float(v) for v in anchor_end),
                           str(anchor_crs))
    return out
