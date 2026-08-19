#!/usr/bin/env python3
"""GUI wrapper for the point‑cloud‑to‑polygon script.

The UI is built with PyQt6 and provides the following controls:

* **Load LAS/LAZ file** – opens a file dialog and populates the scalar field list.
* **Scalar field** – drop‑down of all scalar fields in the file.
* **Threshold** – optional numeric filter; leave empty to use all points.
* **Alpha** – optional alpha‑shape value; leave empty for a convex hull.
* **Top Z threshold** – filters points above this normalized height (0-1).
* **Height filter (m)** – filters points above this absolute height in meters (for grouped polygons only).
* **Group by** – field to group points by for separate polygons.
* **CRS** – coordinate reference system (EPSG code or WKT).
* **Output file** – file dialog to choose the destination shapefile or GeoJSON.
* **Run** – executes the conversion and writes the polygon.

The conversion logic is identical to the command‑line script in
`pointcloud_to_polygon.py`.
"""

import sys
from pathlib import Path

import laspy
import numpy as np
from scipy.spatial import ConvexHull, Voronoi
from shapely.geometry import MultiPoint, Polygon
from shapely.ops import unary_union
import geopandas as gpd

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QCheckBox,
)


# ---------------------------------------------------------------------------
# Helper functions – identical to the command‑line script
# ---------------------------------------------------------------------------

def alpha_shape(points, alpha):
    """Return the alpha shape (concave hull) of a set of points.

    Parameters
    ----------
    points : np.ndarray
        Nx2 array of (x, y) coordinates.
    alpha : float
        Alpha value controlling the concavity.
    """
    if len(points) < 4:
        return MultiPoint(list(points)).convex_hull

    from scipy.spatial import Delaunay

    tri = Delaunay(points)
    edges = set()
    for ia, ib, ic in tri.simplices:
        pa, pb, pc = points[ia], points[ib], points[ic]
        a = np.linalg.norm(pb - pc)
        b = np.linalg.norm(pa - pc)
        c = np.linalg.norm(pa - pb)
        s = (a + b + c) / 2.0
        area = np.sqrt(s * (s - a) * (s - b) * (s - c))
        if area == 0:
            continue
        circum_r = a * b * c / (4.0 * area)
        if circum_r < 1.0 / alpha:
            edges.update([(ia, ib), (ib, ic), (ic, ia)])

    edge_points = []
    for ia, ib in edges:
        edge_points.append(points[ia])
        edge_points.append(points[ib])

    m = MultiPoint(edge_points)
    return unary_union(m.convex_hull)


def voronoi_polygons(points, boundary=None):
    """Create Voronoi polygons from points, clipped to boundary if provided."""
    from shapely.geometry import Polygon
    vor = Voronoi(points)
    polygons = []
    for region_idx in vor.regions:
        if -1 in region_idx or len(region_idx) == 0:
            continue  # Skip infinite or empty regions
        region_points = vor.vertices[region_idx]
        poly = Polygon(region_points)
        if boundary:
            poly = poly.intersection(boundary)
        if not poly.is_empty:
            polygons.append(poly)
    return polygons


# ---------------------------------------------------------------------------
# Main GUI class
# ---------------------------------------------------------------------------
class PolygonGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LAS → Polygon (PyQt6)")
        self.resize(650, 250)
        self.las = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # File selector
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        load_btn = QPushButton("Load LAS/LAZ")
        load_btn.clicked.connect(self.load_file)
        file_layout.addWidget(QLabel("File:"))
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(load_btn)
        layout.addLayout(file_layout)

        # Scalar field selector
        scalar_layout = QHBoxLayout()
        self.scalar_combo = QComboBox()
        scalar_layout.addWidget(QLabel("Scalar field:"))
        scalar_layout.addWidget(self.scalar_combo)
        layout.addLayout(scalar_layout)

        # Group by field selector
        group_layout = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.addItem("None (single polygon)")
        group_layout.addWidget(QLabel("Group by:"))
        group_layout.addWidget(self.group_combo)
        layout.addLayout(group_layout)

        # Threshold input
        thresh_layout = QHBoxLayout()
        self.thresh_edit = QLineEdit()
        self.thresh_edit.setPlaceholderText("None (use all points)")
        thresh_layout.addWidget(QLabel("Threshold:"))
        thresh_layout.addWidget(self.thresh_edit)
        layout.addLayout(thresh_layout)

        # Alpha input
        alpha_layout = QHBoxLayout()
        self.alpha_edit = QLineEdit()
        self.alpha_edit.setPlaceholderText("None (convex hull)")
        alpha_layout.addWidget(QLabel("Alpha:"))
        alpha_layout.addWidget(self.alpha_edit)
        layout.addLayout(alpha_layout)

        # Normalization and top Z options
        norm_layout = QHBoxLayout()
        self.top_z_edit = QLineEdit()
        self.top_z_edit.setPlaceholderText("0.9")
        self.top_z_edit.setText("0.9")
        self.height_filter_edit = QLineEdit()
        self.height_filter_edit.setPlaceholderText("None (use all heights)")
        norm_layout.addWidget(QLabel("Top Z threshold:"))
        norm_layout.addWidget(self.top_z_edit)
        norm_layout.addWidget(QLabel("Height filter (m):"))
        norm_layout.addWidget(self.height_filter_edit)
        layout.addLayout(norm_layout)

        # Output selector
        out_layout = QHBoxLayout()
        self.out_edit = QLineEdit()
        out_btn = QPushButton("Browse…")
        out_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(QLabel("Output:"))
        out_layout.addWidget(self.out_edit)
        out_layout.addWidget(out_btn)
        layout.addLayout(out_layout)

        # CRS input
        crs_layout = QHBoxLayout()
        self.crs_edit = QLineEdit()
        self.crs_edit.setPlaceholderText("EPSG code (e.g., 2956) or WKT string")
        crs_layout.addWidget(QLabel("CRS:"))
        crs_layout.addWidget(self.crs_edit)
        layout.addLayout(crs_layout)

        # Run button
        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self.run_conversion)
        layout.addWidget(run_btn)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open LAS/LAZ file",
            str(Path.home()),
            "LAS/LAZ files (*.las *.laz)",
        )
        if not path:
            return
        try:
            self.las = laspy.read(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file: {e}")
            return
        self.file_edit.setText(path)
        # Populate scalar fields
        self.scalar_combo.clear()
        self.scalar_combo.addItem("<select>")
        # Try a few ways to get available scalar/dimension names from laspy
        names = []
        try:
            # Preferred: LasData.point_format.dimension_names (laspy >=2)
            if hasattr(self.las, 'point_format') and hasattr(self.las.point_format, 'dimension_names'):
                names = list(self.las.point_format.dimension_names)
        except Exception:
            names = []

        # Fallback: the structured dtype names from the points array
        if not names:
            try:
                if hasattr(self.las, 'points') and hasattr(self.las.points, 'dtype') and self.las.points.dtype.names:
                    names = list(self.las.points.dtype.names)
            except Exception:
                names = []

        # Final safety: try header point_format if present
        if not names:
            try:
                if hasattr(self.las, 'header') and hasattr(self.las.header, 'point_format') and hasattr(self.las.header.point_format, 'dimension_names'):
                    names = list(self.las.header.point_format.dimension_names)
            except Exception:
                names = []

        # Populate combo box excluding coordinates
        # Exclude coordinate fields (case-insensitive)
        self.scalar_combo.clear()
        self.scalar_combo.addItem("<select>")
        self.group_combo.clear()
        self.group_combo.addItem("None (single polygon)")
        for name in names:
            if name.strip().lower() not in ['x', 'y', 'z']:
                self.scalar_combo.addItem(name)
                self.group_combo.addItem(name)

    def browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save polygon(s)",
            str(Path.home()),
            "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)",
        )
        if path:
            self.out_edit.setText(path)

    def run_conversion(self):
        if self.las is None:
            QMessageBox.warning(self, "Missing file", "Please load a LAS/LAZ file first.")
            return
        scalar = self.scalar_combo.currentText()
        if scalar == "<select>":
            QMessageBox.warning(self, "Missing field", "Please select a scalar field.")
            return
        group_field = self.group_combo.currentText()
        if group_field == "None (single polygon)":
            group_field = None
        # Threshold
        thresh_text = self.thresh_edit.text().strip()
        threshold = float(thresh_text) if thresh_text else None
        # Alpha
        alpha_text = self.alpha_edit.text().strip()
        alpha = float(alpha_text) if alpha_text else None
        # Normalize
        normalize = False  # Data is already normalized
        # Top Z
        top_z_text = self.top_z_edit.text().strip()
        top_z = float(top_z_text) if top_z_text else 0.9
        # Height filter
        height_filter_text = self.height_filter_edit.text().strip()
        height_filter = float(height_filter_text) if height_filter_text else None
        # Output
        out_path = self.out_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Missing output", "Please choose an output file.")
            return

        # Grab coordinates and scalar
        x = np.asarray(self.las.x)
        y = np.asarray(self.las.y)
        z = np.asarray(self.las.z)
        z_original = z.copy()  # Keep original Z for height filtering
        scalar_vals = np.asarray(self.las[scalar])

        # Filter by threshold if provided
        if threshold is not None:
            mask = scalar_vals > threshold
            x = x[mask]
            y = y[mask]
            z = z[mask]
            z_original = z_original[mask]
            scalar_vals = scalar_vals[mask]

        # Slice top Z
        z_mask = z > top_z
        x = x[z_mask]
        y = y[z_mask]
        z = z[z_mask]
        z_original = z_original[z_mask]
        scalar_vals = scalar_vals[z_mask]

        # Project to XY (top view)
        points_xy = np.column_stack((x, y))

        polygons = []
        group_values = []

        if group_field is None:
            # Single polygon
            if len(points_xy) < 3:
                QMessageBox.warning(self, "Not enough points", "Need at least 3 points to create a polygon.")
                return

            # Build polygon
            if alpha is None:
                hull = ConvexHull(points_xy)
                polygon_coords = points_xy[hull.vertices]
                poly = Polygon(polygon_coords)
            else:
                poly = alpha_shape(points_xy, alpha)

            polygons.append(poly)
            group_values.append("all")
        else:
            # Group by field
            group_vals = self.las[group_field]
            # Need to apply same filters to group_vals
            if threshold is not None:
                group_vals = group_vals[mask]
            group_vals = group_vals[z_mask]

            # Apply height filter if specified
            if height_filter is not None:
                height_mask = z_original > height_filter
                x = x[height_mask]
                y = y[height_mask]
                z = z[height_mask]
                z_original = z_original[height_mask]
                scalar_vals = scalar_vals[height_mask]
                group_vals = group_vals[height_mask]

            unique_groups = np.unique(group_vals)
            avg_points = []
            for group_val in unique_groups:
                g_mask = group_vals == group_val
                if np.sum(g_mask) == 0:
                    continue
                avg_x = np.mean(x[g_mask])
                avg_y = np.mean(y[g_mask])
                avg_points.append([avg_x, avg_y])

            if len(avg_points) < 3:
                QMessageBox.warning(self, "Not enough groups", "Need at least 3 groups with points to create Voronoi polygons.")
                return

            avg_points = np.array(avg_points)
            # Create boundary from convex hull of all avg_points
            boundary_hull = ConvexHull(avg_points)
            boundary_coords = avg_points[boundary_hull.vertices]
            boundary = Polygon(boundary_coords)

            # Voronoi polygons
            vor_polys = voronoi_polygons(avg_points, boundary)
            polygons = vor_polys
            group_values = list(unique_groups[:len(vor_polys)])  # Assuming order matches

        if not polygons:
            QMessageBox.warning(self, "No polygons", "No valid polygons could be created.")
            return

        # Write output
        crs_input = self.crs_edit.text().strip()
        if crs_input:
            try:
                # Try to parse as EPSG code
                if crs_input.isdigit():
                    crs = f"EPSG:{crs_input}"
                else:
                    crs = crs_input
            except:
                crs = None
        else:
            crs = None
        
        gdf = gpd.GeoDataFrame({"geometry": polygons, "group": group_values}, crs=crs)
        try:
            gdf.to_file(out_path)
        except Exception as e:
            QMessageBox.critical(self, "Write error", f"Failed to write file: {e}")
            return
        
        if crs:
            QMessageBox.information(self, "Success", f"{len(polygons)} polygon(s) written to {out_path}")
        else:
            QMessageBox.warning(self, "Success (no CRS)", 
                              f"{len(polygons)} polygon(s) written to {out_path}\n\n"
                              "Warning: No coordinate reference system specified. "
                              "The output may not be usable in GIS software like ArcGIS.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = PolygonGUI()
    win.show()
    sys.exit(app.exec())
