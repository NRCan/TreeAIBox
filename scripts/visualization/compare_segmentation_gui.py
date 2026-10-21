#!/usr/bin/env python3
"""
Interactive Side-by-Side 3D Plot & Individual Tree Split Visualizer for TreeAIBox
Powered by PyQt6 and PyVista (VTK hardware acceleration on NVIDIA RTX 3090).

Allows users to:
1. Browse entire plots side-by-side with synchronized 3D rotation, panning, and zoom.
2. Select any Original Tree ID to directly compare side-by-side:
   - Left: Original Tree ID (pre-refinement)
   - Right: Split Tree IDs (post-refinement) that were disentangled from it.
3. Filter by 'Split Trees Only' or 'Removed Stumps Only' to inspect every correction.
4. Toggle between 'Isolate Tree' and 'Highlight in Plot Context'.
"""

import sys
import os
import glob
import numpy as np
import pandas as pd
import laspy
import pyvista as pv
from pyvistaqt import QtInteractor
import matplotlib.pyplot as plt

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QFrame, QSplitter, QCheckBox,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QIcon, QColor, QDesktopServices


def get_distinct_palette():
    """Build a rich 60-color qualitative palette."""
    cmap1 = plt.get_cmap('tab20', 20)
    cmap2 = plt.get_cmap('tab20b', 20)
    cmap3 = plt.get_cmap('tab20c', 20)
    return np.vstack([cmap1.colors[:, :3], cmap2.colors[:, :3], cmap3.colors[:, :3]])


PALETTE = get_distinct_palette()


def get_tree_color(tree_id):
    """Generate consistent distinct RGB (0-255) for a given tree ID."""
    if tree_id <= 0:
        return np.array([80, 85, 95], dtype=np.uint8)
    idx = (int(tree_id) * 7 + 13) % len(PALETTE)
    return (PALETTE[idx] * 255).astype(np.uint8)


class CompareSegmentationGUI(QMainWindow):
    """Side-by-side synchronized 3D split visualizer."""
    
    def __init__(self):
        super().__init__()
        self.base_dir = r"D:\LLR DATA\Clipped_Plots\Segmented_Results"
        self.refined_dir = os.path.join(self.base_dir, "Refined")
        self.summary_df = None
        self.load_summary()
        
        # Current Plot Data
        self.current_plot_name = None
        self.pts_orig = None
        self.pts_ref = None
        self.itc_orig = None
        self.itc_ref = None
        self.stem_orig = None
        
        # Tree mappings: orig_id -> { 'pts': int, 'split_ids': list, 'type': 'split'|'clean'|'removed', 'z_span': float }
        self.tree_info = {}
        self.selected_orig_id = None  # None means whole plot
        self.filter_mode = 'all'      # 'all', 'split', 'removed', 'clean'
        self.view_context_mode = 'isolate' # 'isolate' or 'context'
        
        self.init_ui()
        self.load_plot(0)
        
    def load_summary(self):
        summary_path = os.path.join(self.refined_dir, "all_plots_refined_inventory_summary.csv")
        if os.path.exists(summary_path):
            self.summary_df = pd.read_csv(summary_path)
            
    def init_ui(self):
        self.setWindowTitle("TreeAIBox - Side-by-Side Tree Split & Refinement Visualizer")
        self.setGeometry(60, 60, 1680, 980)
        
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "treeaibox_logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        # 1. Top Control Bar
        control_bar = QFrame()
        control_bar.setStyleSheet("background-color: #1a1d26; border-radius: 8px; padding: 6px;")
        bar_layout = QHBoxLayout(control_bar)
        bar_layout.setContentsMargins(10, 6, 10, 6)
        bar_layout.setSpacing(12)
        
        lbl_plot = QLabel("Plot:")
        lbl_plot.setStyleSheet("color: #e5e7eb; font-weight: bold; font-size: 13px;")
        bar_layout.addWidget(lbl_plot)
        
        self.combo_plot = QComboBox()
        self.combo_plot.setStyleSheet("""
            QComboBox {
                background-color: #2b3040;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
                min-width: 120px;
            }
        """)
        for i in range(1, 9):
            self.combo_plot.addItem(f"Plot {i}", f"plot_{i}")
        self.combo_plot.currentIndexChanged.connect(self.on_plot_changed)
        bar_layout.addWidget(self.combo_plot)
        
        btn_prev = QPushButton("◀")
        btn_prev.setStyleSheet("background:#374151; color:#fff; padding:5px 10px; border-radius:4px; font-weight:bold;")
        btn_prev.clicked.connect(self.on_prev_plot)
        bar_layout.addWidget(btn_prev)
        
        btn_next = QPushButton("▶")
        btn_next.setStyleSheet("background:#374151; color:#fff; padding:5px 10px; border-radius:4px; font-weight:bold;")
        btn_next.clicked.connect(self.on_next_plot)
        bar_layout.addWidget(btn_next)
        
        bar_layout.addSpacing(15)
        
        # Camera Presets
        lbl_cam = QLabel("Camera:")
        lbl_cam.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: bold;")
        bar_layout.addWidget(lbl_cam)
        
        btn_iso = QPushButton("3D Isometric")
        btn_iso.setStyleSheet("background:#2b3040; color:#fff; padding:5px 10px; border-radius:4px;")
        btn_iso.clicked.connect(self.set_view_isometric)
        bar_layout.addWidget(btn_iso)
        
        btn_top = QPushButton("Top View (XY)")
        btn_top.setStyleSheet("background:#2b3040; color:#fff; padding:5px 10px; border-radius:4px;")
        btn_top.clicked.connect(self.set_view_top)
        bar_layout.addWidget(btn_top)
        
        btn_reset = QPushButton("Reset View")
        btn_reset.setStyleSheet("background:#2b3040; color:#fff; padding:5px 10px; border-radius:4px;")
        btn_reset.clicked.connect(self.reset_views)
        bar_layout.addWidget(btn_reset)
        
        bar_layout.addSpacing(15)
        
        # View Mode Toggle: Isolate vs Context
        lbl_mode = QLabel("Inspection:")
        lbl_mode.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: bold;")
        bar_layout.addWidget(lbl_mode)
        
        self.radio_isolate = QRadioButton("Isolate Tree")
        self.radio_isolate.setChecked(True)
        self.radio_isolate.setStyleSheet("color: #fff;")
        self.radio_isolate.toggled.connect(self.on_context_mode_changed)
        bar_layout.addWidget(self.radio_isolate)
        
        self.radio_context = QRadioButton("Show in Context")
        self.radio_context.setStyleSheet("color: #9ca3af;")
        self.radio_context.toggled.connect(self.on_context_mode_changed)
        bar_layout.addWidget(self.radio_context)
        
        bar_layout.addStretch()
        
        btn_whole = QPushButton("🔍 Whole Plot")
        btn_whole.setStyleSheet("background:#059669; color:#fff; padding:5px 14px; border-radius:4px; font-weight:bold;")
        btn_whole.clicked.connect(self.show_whole_plot)
        bar_layout.addWidget(btn_whole)
        
        btn_html = QPushButton("🌐 HTML Report")
        btn_html.setStyleSheet("background:#2563eb; color:#fff; padding:5px 14px; border-radius:4px; font-weight:bold;")
        btn_html.clicked.connect(self.open_html_report)
        bar_layout.addWidget(btn_html)
        
        main_layout.addWidget(control_bar)
        
        # 2. Main Content Splitter (Sidebar + 3D Viewports)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2b3040;
                width: 4px;
            }
        """)
        
        # Left Sidebar: Tree List & Filter Chips
        sidebar = QFrame()
        sidebar.setStyleSheet("background-color: #161922; border-radius: 8px; border: 1px solid #242938;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)
        
        lbl_trees_title = QLabel("Original Tree IDs")
        lbl_trees_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        sidebar_layout.addWidget(lbl_trees_title)
        
        # Filter Buttons
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)
        
        self.btn_f_all = QPushButton("All")
        self.btn_f_all.setStyleSheet("background:#2b3040; color:#fff; padding:4px 8px; border-radius:4px; font-size:11px;")
        self.btn_f_all.clicked.connect(lambda: self.set_filter('all'))
        filter_layout.addWidget(self.btn_f_all)
        
        self.btn_f_split = QPushButton("⚡ Split")
        self.btn_f_split.setStyleSheet("background:#1e3a8a; color:#60a5fa; padding:4px 8px; border-radius:4px; font-size:11px; font-weight:bold;")
        self.btn_f_split.clicked.connect(lambda: self.set_filter('split'))
        filter_layout.addWidget(self.btn_f_split)
        
        self.btn_f_removed = QPushButton("🗑 Stumps")
        self.btn_f_removed.setStyleSheet("background:#450a0a; color:#f87171; padding:4px 8px; border-radius:4px; font-size:11px;")
        self.btn_f_removed.clicked.connect(lambda: self.set_filter('removed'))
        filter_layout.addWidget(self.btn_f_removed)
        
        sidebar_layout.addLayout(filter_layout)
        
        # Tree List Widget
        self.tree_list = QListWidget()
        self.tree_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1d26;
                color: #e5e7eb;
                border: 1px solid #2b3040;
                border-radius: 6px;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #232733;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #242938;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        self.tree_list.itemClicked.connect(self.on_tree_selected)
        sidebar_layout.addWidget(self.tree_list, 1)
        
        # Summary Box at bottom of sidebar
        self.lbl_sidebar_info = QLabel("Loading plot data...")
        self.lbl_sidebar_info.setStyleSheet("color: #9ca3af; font-size: 11px; line-height: 1.4;")
        self.lbl_sidebar_info.setWordWrap(True)
        sidebar_layout.addWidget(self.lbl_sidebar_info)
        
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 0)
        
        # Right Side: Comparison Display
        display_frame = QFrame()
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.setSpacing(6)
        
        # Info Header Card
        self.header_card = QFrame()
        self.header_card.setStyleSheet("background-color: #161922; border: 1px solid #242938; border-radius: 6px; padding: 6px 12px;")
        header_card_layout = QHBoxLayout(self.header_card)
        header_card_layout.setContentsMargins(8, 4, 8, 4)
        
        self.lbl_card_title = QLabel("Original Tree ID: Whole Plot")
        self.lbl_card_title.setStyleSheet("color: #fff; font-size: 13px; font-weight: bold;")
        header_card_layout.addWidget(self.lbl_card_title)
        
        self.lbl_card_detail = QLabel("Left: Original Segmented | Right: Refined Segmentation")
        self.lbl_card_detail.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: bold;")
        header_card_layout.addWidget(self.lbl_card_detail)
        
        header_card_layout.addStretch()
        lbl_hint = QLabel("💡 Dual synchronized 3D viewports (linked rotation)")
        lbl_hint.setStyleSheet("color: #6b7280; font-size: 11px; font-style: italic;")
        header_card_layout.addWidget(lbl_hint)
        
        display_layout.addWidget(self.header_card)
        
        # Synchronized Dual Viewports (QtInteractor)
        self.interactor = QtInteractor(self, shape=(1, 2))
        self.interactor.set_background('#101217')
        display_layout.addWidget(self.interactor.interactor, 1)
        self.interactor.link_views()
        
        splitter.addWidget(display_frame)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 1340])
        
        main_layout.addWidget(splitter, 1)
        
    def on_plot_changed(self, index):
        self.load_plot(index)
        
    def on_prev_plot(self):
        curr = self.combo_plot.currentIndex()
        if curr > 0:
            self.combo_plot.setCurrentIndex(curr - 1)
            
    def on_next_plot(self):
        curr = self.combo_plot.currentIndex()
        if curr < self.combo_plot.count() - 1:
            self.combo_plot.setCurrentIndex(curr + 1)
            
    def on_context_mode_changed(self):
        if self.radio_isolate.isChecked():
            self.view_context_mode = 'isolate'
        else:
            self.view_context_mode = 'context'
        if self.selected_orig_id is not None:
            self.render_tree_pair(self.selected_orig_id)
        else:
            self.render_whole_plot()
            
    def set_filter(self, mode):
        self.filter_mode = mode
        self.populate_tree_list()
        
    def show_whole_plot(self):
        self.selected_orig_id = None
        self.tree_list.clearSelection()
        self.render_whole_plot()
        
    def open_html_report(self):
        report_path = os.path.join(self.refined_dir, "visual_comparison_report.html")
        if os.path.exists(report_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(report_path))
            
    def set_view_isometric(self):
        self.interactor.view_isometric()
        self.interactor.reset_camera()
        
    def set_view_top(self):
        self.interactor.view_xy()
        self.interactor.reset_camera()
        
    def reset_views(self):
        self.interactor.reset_camera()
        
    def load_plot(self, index):
        pname = self.combo_plot.itemData(index)
        self.current_plot_name = pname
        
        orig_las_path = os.path.join(self.base_dir, f"{pname}_segmented.las")
        ref_las_path = os.path.join(self.refined_dir, f"{pname}_refined.las")
        
        if not os.path.exists(orig_las_path) or not os.path.exists(ref_las_path):
            return
            
        las_orig = laspy.read(orig_las_path)
        las_ref = laspy.read(ref_las_path)
        
        self.pts_orig = np.column_stack([las_orig.x, las_orig.y, las_orig.z])
        self.pts_ref = np.column_stack([las_ref.x, las_ref.y, las_ref.z])
        self.itc_orig = np.array(las_orig.itc, dtype=np.int32)
        self.itc_ref = np.array(las_ref.itc, dtype=np.int32)
        
        # Build mapping of original Tree ID -> Refined Tree IDs
        self.tree_info = {}
        unique_orig = np.unique(self.itc_orig[self.itc_orig > 0])
        
        split_count = 0
        removed_count = 0
        clean_count = 0
        
        for orig_id in unique_orig:
            mask = (self.itc_orig == orig_id)
            pts_c = int(np.sum(mask))
            z_span = float(np.ptp(self.pts_orig[mask, 2]))
            
            # Find which refined IDs correspond to these points
            sub_ref_ids = np.unique(self.itc_ref[mask])
            split_ids = [int(x) for x in sub_ref_ids if x > 0]
            
            if len(split_ids) == 0:
                ttype = 'removed'
                removed_count += 1
            elif len(split_ids) > 1:
                ttype = 'split'
                split_count += 1
            else:
                ttype = 'clean'
                clean_count += 1
                
            self.tree_info[orig_id] = {
                'pts': pts_c,
                'z_span': round(z_span, 2),
                'split_ids': split_ids,
                'type': ttype
            }
            
        self.lbl_sidebar_info.setText(
            f"<b>{pname.upper()} Summary:</b><br>"
            f"Original Trees: {len(unique_orig)}<br>"
            f"⚡ Merged Trees Split: <b style='color:#60a5fa;'>{split_count}</b><br>"
            f"🗑 Stumps Removed: <b style='color:#f87171;'>{removed_count}</b><br>"
            f"✓ Single Clean Trees: {clean_count}"
        )
        
        self.populate_tree_list()
        self.selected_orig_id = None
        self.render_whole_plot()
        
    def populate_tree_list(self):
        self.tree_list.clear()
        
        for orig_id, info in sorted(self.tree_info.items()):
            ttype = info['type']
            if self.filter_mode == 'split' and ttype != 'split':
                continue
            if self.filter_mode == 'removed' and ttype != 'removed':
                continue
            if self.filter_mode == 'clean' and ttype != 'clean':
                continue
                
            if ttype == 'split':
                label = f"⚡ Tree {orig_id:2d}  ➔  SPLIT into {len(info['split_ids'])} IDs: {info['split_ids']}"
                color = QColor("#60a5fa")
            elif ttype == 'removed':
                label = f"🗑 Tree {orig_id:2d}  ➔  REMOVED (Stump {info['z_span']}m, {info['pts']} pts)"
                color = QColor("#f87171")
            else:
                label = f"✓ Tree {orig_id:2d}  ➔  Clean (Refined ID {info['split_ids'][0]})"
                color = QColor("#9ca3af")
                
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, orig_id)
            item.setForeground(color)
            self.tree_list.addItem(item)
            
    def on_tree_selected(self, item):
        orig_id = item.data(Qt.ItemDataRole.UserRole)
        self.selected_orig_id = orig_id
        self.render_tree_pair(orig_id)
        
    def render_tree_pair(self, orig_id):
        """Render selected Tree ID on left and its Split IDs on right."""
        info = self.tree_info.get(orig_id)
        if not info:
            return
            
        mask_orig = (self.itc_orig == orig_id)
        pts_tree = self.pts_orig[mask_orig]
        split_ids = info['split_ids']
        ttype = info['type']
        
        # Update Info Card
        if ttype == 'split':
            self.lbl_card_title.setText(f"Original Tree ID {orig_id}  ({info['pts']:,} points | Height: {info['z_span']}m)")
            self.lbl_card_detail.setText(f"⚡ SPLIT INTO {len(split_ids)} INDIVIDUAL TREES ➔ Refined IDs: {split_ids}")
            self.lbl_card_detail.setStyleSheet("color: #60a5fa; font-size: 13px; font-weight: bold;")
        elif ttype == 'removed':
            self.lbl_card_title.setText(f"Original Tree ID {orig_id}  ({info['pts']:,} points | Height: {info['z_span']}m)")
            self.lbl_card_detail.setText(f"🗑 CLASSIFIED AS NOISE/STUMP (<2.5m) ➔ Removed from inventory")
            self.lbl_card_detail.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_card_title.setText(f"Original Tree ID {orig_id}  ({info['pts']:,} points | Height: {info['z_span']}m)")
            self.lbl_card_detail.setText(f"✓ Valid Single Tree ➔ Renumbered as Refined ID {split_ids[0]}")
            self.lbl_card_detail.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: bold;")

        # --- LEFT PANE: ORIGINAL TREE ID ---
        self.interactor.subplot(0, 0)
        self.interactor.clear()
        
        if self.view_context_mode == 'context':
            # Background context: dim gray
            bg_mask = ~mask_orig
            if np.sum(bg_mask) > 0:
                cloud_bg = pv.PolyData(self.pts_orig[bg_mask][::3])
                self.interactor.add_mesh(cloud_bg, color='#374151', opacity=0.15, point_size=2)
                
        # Original tree points (Solid bright cyan/yellow)
        cloud_orig_tree = pv.PolyData(pts_tree)
        orig_color = '#06b6d4' if ttype == 'split' else ('#ef4444' if ttype == 'removed' else '#10b981')
        self.interactor.add_mesh(cloud_orig_tree, color=orig_color, point_size=4.0, render_points_as_spheres=True)
        
        # Add label
        center_orig = np.mean(pts_tree, axis=0)
        center_orig[2] = np.max(pts_tree[:, 2]) + 1.0
        self.interactor.add_point_labels([center_orig], [f"Original Tree ID: {orig_id}"], font_size=12, text_color='white', point_color=orig_color)
        self.interactor.add_text(f"ORIGINAL TREE ID: {orig_id}\n1 Cluster ({info['pts']:,} pts)", position='upper_left', font_size=12, color='white')
        self.interactor.show_grid(color='#2b3040')

        # --- RIGHT PANE: SPLIT REFINED TREE IDs ---
        self.interactor.subplot(0, 1)
        self.interactor.clear()
        
        if self.view_context_mode == 'context':
            bg_mask_ref = ~mask_orig
            if np.sum(bg_mask_ref) > 0:
                cloud_bg_ref = pv.PolyData(self.pts_ref[bg_mask_ref][::3])
                self.interactor.add_mesh(cloud_bg_ref, color='#374151', opacity=0.15, point_size=2)
                
        if ttype == 'removed':
            # Draw as dark muted noise points
            cloud_noise = pv.PolyData(pts_tree)
            self.interactor.add_mesh(cloud_noise, color='#6b7280', point_size=3.0, render_points_as_spheres=True)
            self.interactor.add_text("REFINED: REMOVED\n(Set to Noise / Ground)", position='upper_left', font_size=12, color='#f87171')
        else:
            # Color points according to their individual Split Tree IDs
            ref_sub_itc = self.itc_ref[mask_orig]
            rgb_split = np.zeros((len(pts_tree), 3), dtype=np.uint8)
            
            label_positions = []
            label_texts = []
            
            for s_id in split_ids:
                s_mask = (ref_sub_itc == s_id)
                s_pts = pts_tree[s_mask]
                s_color = get_tree_color(s_id)
                rgb_split[s_mask] = s_color
                
                # Position label above crown top
                if len(s_pts) > 0:
                    top_pt = np.median(s_pts, axis=0)
                    top_pt[2] = np.max(s_pts[:, 2]) + 1.0
                    label_positions.append(top_pt)
                    label_texts.append(f"Tree {s_id}")
                    
            # Any unassigned points within cluster
            rgb_split[ref_sub_itc == 0] = [80, 85, 95]
            
            cloud_split = pv.PolyData(pts_tree)
            cloud_split['RGB'] = rgb_split
            self.interactor.add_mesh(cloud_split, scalars='RGB', rgb=True, point_size=4.0, render_points_as_spheres=True)
            
            if len(label_positions) > 0:
                self.interactor.add_point_labels(label_positions, label_texts, font_size=12, text_color='#4ade80')
                
            self.interactor.add_text(
                f"REFINED RESULT: {len(split_ids)} Split Tree(s)\nIDs: {split_ids}",
                position='upper_left', font_size=12, color='#4ade80'
            )
            
        self.interactor.show_grid(color='#2b3040')
        
        # Link views and focus camera
        self.interactor.link_views()
        self.interactor.reset_camera()
        
    def render_whole_plot(self):
        """Render entire plot side-by-side."""
        self.lbl_card_title.setText(f"{self.current_plot_name.upper()} - Whole Plot Overview")
        self.lbl_card_detail.setText("Select any Tree ID on the left to inspect side-by-side splits")
        self.lbl_card_detail.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: bold;")
        
        # Subsample for smooth 60 FPS whole-plot viewing
        step = max(1, len(self.pts_orig) // 300000)
        p_orig = self.pts_orig[::step]
        p_ref = self.pts_ref[::step]
        itc_o = self.itc_orig[::step]
        itc_r = self.itc_ref[::step]
        
        rgb_o = np.zeros((len(p_orig), 3), dtype=np.uint8)
        for t_id in np.unique(itc_o[itc_o > 0]):
            rgb_o[itc_o == t_id] = get_tree_color(t_id)
        rgb_o[itc_o == 0] = [70, 75, 85]
        
        rgb_r = np.zeros((len(p_ref), 3), dtype=np.uint8)
        for t_id in np.unique(itc_r[itc_r > 0]):
            rgb_r[itc_r == t_id] = get_tree_color(t_id)
        rgb_r[itc_r == 0] = [70, 75, 85]
        
        # Left: Original
        self.interactor.subplot(0, 0)
        self.interactor.clear()
        cloud_o = pv.PolyData(p_orig)
        cloud_o['RGB'] = rgb_o
        self.interactor.add_mesh(cloud_o, scalars='RGB', rgb=True, point_size=2.5, render_points_as_spheres=True)
        n_orig = len(np.unique(self.itc_orig[self.itc_orig > 0]))
        self.interactor.add_text(f"{self.current_plot_name.upper()} - ORIGINAL ({n_orig} Trees)", position='upper_left', font_size=12, color='white')
        self.interactor.show_grid(color='#2b3040')
        
        # Right: Refined
        self.interactor.subplot(0, 1)
        self.interactor.clear()
        cloud_r = pv.PolyData(p_ref)
        cloud_r['RGB'] = rgb_r
        self.interactor.add_mesh(cloud_r, scalars='RGB', rgb=True, point_size=2.5, render_points_as_spheres=True)
        n_ref = len(np.unique(self.itc_ref[self.itc_ref > 0]))
        self.interactor.add_text(f"{self.current_plot_name.upper()} - REFINED ({n_ref} Trees)", position='upper_left', font_size=12, color='#4ade80')
        self.interactor.show_grid(color='#2b3040')
        
        self.interactor.link_views()
        self.interactor.reset_camera()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TreeAIBox Tree Split Visualizer")
    win = CompareSegmentationGUI()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
