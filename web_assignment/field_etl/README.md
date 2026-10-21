# Step 1 — Field Point ETL (field_etl)

The first step of the TreeAIBox LiDAR-to-Field pipeline: **clean the source
field-survey points and export clean points, the transect line and a boundary
polygon**, ready for the Field Matcher (Step 2) and for GIS.

## Webpage: /field-etl/

| Control | Purpose |
|---------|---------|
| Source data | pick / type a vector (.gdb, .shp, **.gpkg**, .geojson) **or a CSV** |
| Scan layers | list layers and pick the survey-point layer |
| Derive DBH from perimeter | when no DBH column exists, compute dbh = perimeter / pi |
| Process & map | read + clean + flag anomalies + draw map |
| Layer manager | toggle Points / Flagged / Transect line / Boundary polygon |
| Show labels / Label by | toggle + choose a field (Tree ID, Species, DBH, Perimeter, Side, y-axis) |
| Boundary buffer slider | recompute the boundary polygon live (0–30 m) |
| Export | **GeoPackage** (points + line + boundary), GeoJSON, Clean CSV |

## CSV input

The source can be a **cleaned CSV** (e.g. `transect1_cleaned.csv`), the natural
Step-1 input format. Two layouts are auto-detected:
- **transect-relative** : `y-axis(m)` + `Side` + `x-axis(m)` columns with no
  coordinates -> points reconstructed from the begin/end LiDAR anchors
  (EPSG:2961 defaults from the workbook);
- **generic** : explicit `x/y` or `lon/lat` columns -> used directly.

DBH is derived from the perimeter column when no DBH column exists.

## APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| /field-etl/api/list-layers/ | POST | {path} → {layers, default_layer} |
| /field-etl/api/pick/ | POST | native file/folder picker |
| /field-etl/api/process/ | POST | {path, layer, derive_dbh} → geojson + stats + anomalies |
| /field-etl/api/boundary/ | POST | {path, layer, buffer_m} → boundary polygon (for slider) |
| /field-etl/export/gpkg/ | GET | ?path=&layer=&buffer=&exclude=&derive_dbh= → .gpkg |
| /field-etl/export/geojson/ | GET | ?... → .geojson |
| /field-etl/export/csv/ | GET | ?... → clean .csv |

## GPKG export layers

| Layer | Content |
|-------|---------|
| field_points | clean points (tree_id, species, dbh_cm, perimeter_cm, dbh_derived, side, y_axis_m, height_class, flagged, anomalies) |
| transect_line | best-fit transect axis with length_m |
| boundary | convex hull + buffer of all points (buffer_m recorded) |

## Integration with the Field Matcher

This is the **first step**; the matcher (root /) is step 2. Both live in the same
Django project (web_assignment). A link in the matcher header navigates to
/field-etl/. The matcher also accepts .gpkg inputs (via pyogrio).
