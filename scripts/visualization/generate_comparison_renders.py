#!/usr/bin/env python3
"""
Generate High-Resolution Visual Comparison Renders & HTML Report for Segmented vs Refined Plots
Renders 3D Perspective and Top-Down (XY) side-by-side comparisons for all 8 plots.
"""

import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import laspy
import pyvista as pv
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def get_itc_rgb_colors(itc_array, seed=42):
    """
    Generate high-contrast RGB colors for ITC array.
    ITC 0 is dark gray, positive ITCs get vibrant distinct colors.
    """
    n_pts = len(itc_array)
    rgb = np.zeros((n_pts, 3), dtype=np.uint8)
    
    # Ground/unassigned points: subtle dark slate gray
    ground_mask = (itc_array == 0)
    rgb[ground_mask] = [90, 95, 105]
    
    unique_itc = np.unique(itc_array[itc_array > 0])
    if len(unique_itc) == 0:
        return rgb
        
    # Generate distinct random colors using Golden Ratio / HSV
    np.random.seed(seed)
    n_colors = len(unique_itc)
    
    # Use qualitative colormaps combined
    cmap1 = plt.get_cmap('tab20', 20)
    cmap2 = plt.get_cmap('tab20b', 20)
    cmap3 = plt.get_cmap('tab20c', 20)
    base_palette = np.vstack([cmap1.colors[:, :3], cmap2.colors[:, :3], cmap3.colors[:, :3]])
    
    # Assign colors with hash permutation to prevent adjacent IDs from sharing similar hues
    color_map = {}
    for idx, tree_id in enumerate(unique_itc):
        palette_idx = (tree_id * 7 + 13) % len(base_palette)
        color = (base_palette[palette_idx] * 255).astype(np.uint8)
        color_map[tree_id] = color
        
    for tree_id in unique_itc:
        mask = (itc_array == tree_id)
        rgb[mask] = color_map[tree_id]
        
    return rgb


def render_plot_comparison(orig_las_path, refined_las_path, output_dir, plot_name, summary_row=None):
    """Render side-by-side comparison for a single plot in 3D perspective and Top-down view."""
    print(f"\n[*] Rendering visual comparison for {plot_name}...")
    t0 = time.time()
    
    las_orig = laspy.read(orig_las_path)
    las_ref = laspy.read(refined_las_path)
    
    pts_orig = np.column_stack([las_orig.x, las_orig.y, las_orig.z])
    pts_ref = np.column_stack([las_ref.x, las_ref.y, las_ref.z])
    
    rgb_orig = get_itc_rgb_colors(las_orig.itc, seed=42)
    rgb_ref = get_itc_rgb_colors(las_ref.itc, seed=42)
    
    # Subsample if extremely large for smooth rendering
    max_pts = 400000
    if len(pts_orig) > max_pts:
        step = int(np.ceil(len(pts_orig) / max_pts))
        pts_orig = pts_orig[::step]
        rgb_orig = rgb_orig[::step]
        
    if len(pts_ref) > max_pts:
        step = int(np.ceil(len(pts_ref) / max_pts))
        pts_ref = pts_ref[::step]
        rgb_ref = rgb_ref[::step]
        
    cloud_orig = pv.PolyData(pts_orig)
    cloud_orig['RGB'] = rgb_orig
    
    cloud_ref = pv.PolyData(pts_ref)
    cloud_ref['RGB'] = rgb_ref
    
    n_trees_orig = len(np.unique(las_orig.itc[las_orig.itc > 0]))
    n_trees_ref = len(np.unique(las_ref.itc[las_ref.itc > 0]))
    
    # Subplot details
    txt_orig = f"ORIGINAL SEGMENTATION\n{n_trees_orig} Trees"
    if summary_row is not None:
        noise = summary_row.get('removed_noise_stumps', 0)
        splits = summary_row.get('split_merged_clusters', 0)
        extra = summary_row.get('extra_trees_disentangled', 0)
        txt_ref = f"REFINED SEGMENTATION\n{n_trees_ref} Trees (Removed {noise} stumps | Split {splits} clusters into +{extra} trees)"
    else:
        txt_ref = f"REFINED SEGMENTATION\n{n_trees_ref} Trees"
        
    # ---------------- 1. Render 3D Perspective View ----------------
    plotter_3d = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(2048, 1024))
    plotter_3d.set_background('#181a1f')
    
    # Left: Original
    plotter_3d.subplot(0, 0)
    plotter_3d.add_text(f"{plot_name.upper()} - {txt_orig}", font_size=12, color='white', font='courier')
    plotter_3d.add_mesh(cloud_orig, scalars='RGB', rgb=True, point_size=2.5, render_points_as_spheres=True)
    plotter_3d.show_grid(color='#404552')
    
    # Right: Refined
    plotter_3d.subplot(0, 1)
    plotter_3d.add_text(f"{plot_name.upper()} - {txt_ref}", font_size=12, color='#4ade80', font='courier')
    plotter_3d.add_mesh(cloud_ref, scalars='RGB', rgb=True, point_size=2.5, render_points_as_spheres=True)
    plotter_3d.show_grid(color='#404552')
    
    plotter_3d.link_views()
    plotter_3d.view_isometric()
    plotter_3d.reset_camera()
    
    path_3d = os.path.join(output_dir, f"{plot_name}_comparison_3d.png")
    plotter_3d.screenshot(path_3d)
    plotter_3d.close()
    
    # ---------------- 2. Render Top-Down (XY) View ----------------
    plotter_top = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(2048, 1024))
    plotter_top.set_background('#181a1f')
    
    # Left: Original
    plotter_top.subplot(0, 0)
    plotter_top.add_text(f"{plot_name.upper()} [TOP-DOWN XY] - {txt_orig}", font_size=12, color='white', font='courier')
    plotter_top.add_mesh(cloud_orig, scalars='RGB', rgb=True, point_size=3.0, render_points_as_spheres=True)
    plotter_top.show_grid(color='#404552')
    
    # Right: Refined
    plotter_top.subplot(0, 1)
    plotter_top.add_text(f"{plot_name.upper()} [TOP-DOWN XY] - {txt_ref}", font_size=12, color='#4ade80', font='courier')
    plotter_top.add_mesh(cloud_ref, scalars='RGB', rgb=True, point_size=3.0, render_points_as_spheres=True)
    plotter_top.show_grid(color='#404552')
    
    plotter_top.link_views()
    plotter_top.view_xy()
    plotter_top.reset_camera()
    
    path_top = os.path.join(output_dir, f"{plot_name}_comparison_top.png")
    plotter_top.screenshot(path_top)
    plotter_top.close()
    
    print(f"    -> Rendered 3D ({path_3d}) and Top View ({path_top}) in {time.time() - t0:.1f}s")
    return path_3d, path_top


def generate_html_report(plots_data, summary_df, output_html_path):
    """Generate a self-contained responsive HTML comparison report."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TreeAIBox - Plot Segmentation Refinement Comparison</title>
<style>
  :root {{
    --bg-dark: #0f1117;
    --card-bg: #1a1d26;
    --card-border: #2b3040;
    --accent: #22c55e;
    --accent-blue: #3b82f6;
    --accent-red: #ef4444;
    --text-primary: #f3f4f6;
    --text-secondary: #9ca3af;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    line-height: 1.5;
    padding: 24px;
  }}
  header {{
    max-width: 1400px;
    margin: 0 auto 24px auto;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--card-border);
  }}
  h1 {{ font-size: 28px; font-weight: 700; color: #fff; margin-bottom: 8px; }}
  p.subtitle {{ color: var(--text-secondary); font-size: 15px; }}
  
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    max-width: 1400px;
    margin: 0 auto 32px auto;
  }}
  .stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 18px;
  }}
  .stat-label {{ font-size: 13px; text-transform: uppercase; color: var(--text-secondary); font-weight: 600; }}
  .stat-val {{ font-size: 26px; font-weight: 700; margin-top: 4px; }}
  .val-green {{ color: var(--accent); }}
  .val-blue {{ color: var(--accent-blue); }}
  .val-red {{ color: var(--accent-red); }}
  
  .tabs-container {{
    max-width: 1400px;
    margin: 0 auto 20px auto;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .tab-btn {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    color: var(--text-secondary);
    padding: 10px 18px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }}
  .tab-btn:hover {{ background: #242938; color: #fff; }}
  .tab-btn.active {{
    background: var(--accent-blue);
    color: #fff;
    border-color: var(--accent-blue);
  }}
  
  .plot-view {{
    display: none;
    max-width: 1400px;
    margin: 0 auto;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    overflow: hidden;
    padding: 24px;
  }}
  .plot-view.active {{ display: block; }}
  
  .plot-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .plot-title {{ font-size: 22px; font-weight: 700; color: #fff; }}
  .plot-badges {{ display: flex; gap: 10px; }}
  .badge {{
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
  }}
  .badge-orig {{ background: #374151; color: #e5e7eb; }}
  .badge-ref {{ background: #065f46; color: #34d399; }}
  .badge-split {{ background: #1e3a8a; color: #60a5fa; }}
  
  .view-toggle-bar {{
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
  }}
  .subtab-btn {{
    background: #232733;
    border: 1px solid #374151;
    color: #9ca3af;
    padding: 6px 14px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
  }}
  .subtab-btn.active {{
    background: #374151;
    color: #fff;
    border-color: #4b5563;
  }}
  
  .img-wrapper {{
    width: 100%;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--card-border);
    margin-bottom: 16px;
  }}
  .img-wrapper img {{
    width: 100%;
    height: auto;
    display: block;
  }}
  
  .legend-box {{
    background: #13161f;
    border: 1px solid var(--card-border);
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: var(--text-secondary);
    display: flex;
    gap: 24px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  
  table.summary-tbl {{
    width: 100%;
    max-width: 1400px;
    margin: 40px auto 0 auto;
    border-collapse: collapse;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    overflow: hidden;
  }}
  table.summary-tbl th, table.summary-tbl td {{
    padding: 12px 16px;
    text-align: left;
    font-size: 14px;
    border-bottom: 1px solid var(--card-border);
  }}
  table.summary-tbl th {{ background: #202431; color: var(--text-secondary); font-weight: 600; }}
  table.summary-tbl tr:last-child td {{ border-bottom: none; }}
  table.summary-tbl tr:hover td {{ background: #212534; }}
</style>
</head>
<body>

<header>
  <h1>TreeAIBox: Plot Segmentation vs. Refinement Visual Comparison</h1>
  <p class="subtitle">Side-by-side visual analysis showing noise stump removal (<2.5m), multi-stem crown disentanglement, and individual tree crown recovery across all 8 clipped plots.</p>
</header>

<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-label">Initial Clusters</div>
    <div class="stat-val">{summary_df['initial_clusters'].sum()}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Noise Stumps Removed</div>
    <div class="stat-val val-red">-{summary_df['removed_noise_stumps'].sum()}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Overlapped Clusters Split</div>
    <div class="stat-val val-blue">{summary_df['split_merged_clusters'].sum()}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Disentangled Trees Recovered</div>
    <div class="stat-val val-green">+{summary_df['extra_trees_disentangled'].sum()}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Final Refined Trees</div>
    <div class="stat-val val-green">{summary_df['final_refined_trees'].sum()}</div>
  </div>
</div>

<div class="tabs-container">
"""
    for idx, d in enumerate(plots_data):
        active_cls = "active" if idx == 0 else ""
        html += f'  <button class="tab-btn {active_cls}" onclick="switchPlot(\'{d["plot_name"]}\', this)">{d["plot_name"].upper()}</button>\n'
        
    html += '</div>\n\n'
    
    for idx, d in enumerate(plots_data):
        active_cls = "active" if idx == 0 else ""
        pname = d["plot_name"]
        orig_img_3d = os.path.basename(d["path_3d"])
        orig_img_top = os.path.basename(d["path_top"])
        
        html += f"""
<div id="view-{pname}" class="plot-view {active_cls}">
  <div class="plot-header">
    <div class="plot-title">{pname.upper()} Detailed Comparison</div>
    <div class="plot-badges">
      <span class="badge badge-orig">Original: {d["initial_trees"]} Trees</span>
      <span class="badge badge-ref">Refined: {d["refined_trees"]} Trees</span>
      <span class="badge badge-split">Split: {d["split_clusters"]} Clusters (+{d["extra_trees"]} Trees)</span>
    </div>
  </div>
  
  <div class="view-toggle-bar">
    <button class="subtab-btn active" onclick="switchPerspective('{pname}', '3d', this)">3D Isometric Perspective</button>
    <button class="subtab-btn" onclick="switchPerspective('{pname}', 'top', this)">Top-Down (XY) Canopy View</button>
  </div>
  
  <div id="img-{pname}-3d" class="img-wrapper">
    <img src="{orig_img_3d}" alt="{pname} 3D View">
  </div>
  <div id="img-{pname}-top" class="img-wrapper" style="display:none;">
    <img src="{orig_img_top}" alt="{pname} Top View">
  </div>
  
  <div class="legend-box">
    <div class="legend-item"><div class="legend-dot" style="background:#5a5f69;"></div> <span>Gray = Unassigned Ground / Noise</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#22c55e;"></div> <span>Distinct Colors = Individual Tree Crowns (ITC)</span></div>
    <div class="legend-item"><span>Left Side: Original Segmentation with merged clusters</span></div>
    <div class="legend-item"><span>Right Side: Refined Segmentation with disentangled individual trees</span></div>
  </div>
</div>
"""

    # Add Summary Table
    html += """
<table class="summary-tbl">
  <thead>
    <tr>
      <th>Plot Name</th>
      <th>Initial Trees</th>
      <th>Removed Noise/Stumps</th>
      <th>Split Clusters</th>
      <th>Recovered Trees</th>
      <th>Final Clean Trees</th>
      <th>Min Height (m)</th>
      <th>Mean Height (m)</th>
      <th>Mean Crown Diam (m)</th>
    </tr>
  </thead>
  <tbody>
"""
    for _, row in summary_df.iterrows():
        html += f"""    <tr>
      <td><b>{row['plot_name']}</b></td>
      <td>{row['initial_clusters']}</td>
      <td style="color:var(--accent-red);">{row['removed_noise_stumps']}</td>
      <td style="color:var(--accent-blue);">{row['split_merged_clusters']}</td>
      <td style="color:var(--accent); font-weight:600;">+{row['extra_trees_disentangled']}</td>
      <td style="color:var(--accent); font-weight:700;">{row['final_refined_trees']}</td>
      <td>{row['min_height_m']}m</td>
      <td>{row['mean_height_m']}m</td>
      <td>{row['mean_crown_diameter_m']}m</td>
    </tr>
"""
    html += """  </tbody>
</table>

<script>
function switchPlot(plotName, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.plot-view').forEach(v => v.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('view-' + plotName).classList.add('active');
}
function switchPerspective(plotName, type, btn) {
  const container = document.getElementById('view-' + plotName);
  container.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  
  const img3d = document.getElementById('img-' + plotName + '-3d');
  const imgTop = document.getElementById('img-' + plotName + '-top');
  if (type === '3d') {
    img3d.style.display = 'block';
    imgTop.style.display = 'none';
  } else {
    img3d.style.display = 'none';
    imgTop.style.display = 'block';
  }
}
</script>
</body>
</html>
"""
    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"[*] Saved interactive HTML comparison report: {output_html_path}")


def main():
    base_dir = r"D:\LLR DATA\Clipped_Plots\Segmented_Results"
    refined_dir = os.path.join(base_dir, "Refined")
    renders_dir = os.path.join(refined_dir, "Comparison_Renders")
    os.makedirs(renders_dir, exist_ok=True)
    
    summary_path = os.path.join(refined_dir, "all_plots_refined_inventory_summary.csv")
    if os.path.exists(summary_path):
        df_summary = pd.read_csv(summary_path)
    else:
        df_summary = pd.DataFrame()
        
    plots_data = []
    
    for i in range(1, 9):
        pname = f"plot_{i}"
        orig_las = os.path.join(base_dir, f"{pname}_segmented.las")
        ref_las = os.path.join(refined_dir, f"{pname}_refined.las")
        
        if not os.path.exists(orig_las) or not os.path.exists(ref_las):
            print(f"[!] Warning: Files for {pname} not found. Skipping.")
            continue
            
        row = df_summary[df_summary['plot_name'] == pname].iloc[0] if len(df_summary) > 0 and pname in df_summary['plot_name'].values else None
        
        path_3d, path_top = render_plot_comparison(orig_las, ref_las, renders_dir, pname, summary_row=row)
        
        plots_data.append({
            'plot_name': pname,
            'path_3d': path_3d,
            'path_top': path_top,
            'initial_trees': int(row['initial_clusters']) if row is not None else 0,
            'refined_trees': int(row['final_refined_trees']) if row is not None else 0,
            'split_clusters': int(row['split_merged_clusters']) if row is not None else 0,
            'extra_trees': int(row['extra_trees_disentangled']) if row is not None else 0
        })
        
    html_report_path = os.path.join(renders_dir, "visual_comparison_report.html")
    generate_html_report(plots_data, df_summary, html_report_path)
    
    # Also save a copy in refined_dir for direct access
    top_level_html = os.path.join(refined_dir, "visual_comparison_report.html")
    generate_html_report(plots_data, df_summary, top_level_html)


if __name__ == "__main__":
    main()
