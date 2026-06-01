# 2. UAV LiDAR

2.1 Site: Reclamation wellsite (no visible stems) with planted trees near Grand Prairie, Alberta

Data: UAV_reclamation_GP262_20230809_aoi.laz

Sensor: DJI Zenmuse L1 (~1 500 pts/m²)

TreeFiltering (Stem-invisible scene)

Drag the .laz file into CloudCompare; click Apply, Yes.

![image15.png](img/image15.png)

Select the point cloud in DB Tree panel. You can browse visualization properties of point clouds such as Colors (RGB or scalar Fields) and active Scalar Fields (Intensity, Return Number, etc.).

![image16.png](img/image16.png)

Check ALS. From the Predefined models dropdown, choose treefiltering_als_esegformer3D_128_15cm (GPU3GB), click Download. With the point cloud selected, click Apply.

![image17.png](img/image17.png)

- Note: You can browse the downloaded DL model path by clicking the Model path button.The plugin automatically detects whether your PC has a CUDA-enabled GPU. If none is found, the “Use GPU” checkbox will be off and the plugin will default to CPU mode.

![image18.png](img/image18.png)

Result: tree points turn red, ground turns blue; active scalar field = treefilter.

![image19.png](img/image19.png)

![image20.png](img/image20.png)

![image21.png](img/image21.png)

TreeisoNet-TreeLoc (treetop detection)

Ensure the point cloud is selected. Choose Reclamation→ALS (stem invisible)→2.TreeLoc→treeisonet_als_reclamation_treeloc_esegformer3D_128_10cm(GPU4GB)→Download, Apply.

![image22.png](img/image22.png)

Results: Treetops appear (black), with perpoint confidence shown by color gradient.

![image23.png](img/image23.png)

- Note: You can tune TreeLoc parameters (i.e. Confidence threshold: minimum detection confidence; Non-maximum suppression (NMS) cutoff: threshold for suppressing overlapping detections; Max gap: maximum distance between points to be considered connected; Minimum radius: minimum tree-top radius to filter out noise), then click Re-run extraction. Defaults are sufficient for most cases.

- Tip: To show the color bar, scroll down in Properties→check Visible; adjust digit precision under Display Settings→Displayed numbers precision. You don’t need to do this for now.

![image24.png](img/image24.png)

![image25.png](img/image25.png)

![image26.png](img/image26.png)

TreeisoNet-TreeOff (individual‑tree delineation)

Select the original point cloud (not treetops).

Choose 3.TreeOff→treeisonet_als_reclamation_treeoff_esegformer3D_128_10cm(GPU4GB) →Download, Apply.

![image27.png](img/image27.png)

![image28.png](img/image28.png)

Uncheck the box to hide treetops; select the main point cloud.

![image29.png](img/image29.png)

Export stats → Open output path: CSV with tree locations, heights, crown areas.

![image30.png](img/image30.png)

![image31.png](img/image31.png)

2.2 Site: Norwegian Institute of Bioeconomy Research (NIBIO) forest (visible stems) from ForInstance dataset (Puliti et al., 2023)

Data: UAV_mixedwood_NIBIO_plot1.laz

Sensor: Riegl miniVUX1 (~9500 pts/m²)

TreeFiltering

Remove previous clouds (selecting them and press the Delete key).

Load new .laz; Apply, Yes.

![image32.png](img/image32.png)

Select cloud; choose UAV→treefiltering_uav_esegformer3D_128_12cm(GPU3GB)→Download, Apply.

![image33.png](img/image33.png)

Results: tree points in red and ground in blue with a new active scalar field named treefilter.

![image34.png](img/image34.png)

TreeisoNet-StemCls (stem filtering)

Select cloud; choose Mixedwood→UAV (stem explicit)→1.StemCls→treeisonet_uav_mixedwood_stemcls_esegformer3D_128_8cm(GPU3GB)→Download, Apply.

![image35.png](img/image35.png)

- (Optional) Interactive refine via Filter points , Segment , Merge .

![image36.png](img/image36.png)

![image37.png](img/image37.png)

![image38.png](img/image38.png)

![image39.png](img/image39.png)

TreeisoNet-TreeLoc (tree‑base detection)

Select cloud; choose Mixedwood→UAV (stem explicit)→2.TreeLoc→treeisonet_uav_mixedwood_treeloc_esegformer3D_128_10cm(GPU3GB)→Download,Apply.

![image40.png](img/image40.png)

Results: Tree bases appear (black).

![image41.png](img/image41.png)

StemClusterSP: individual-tree stem clustering and isolation based on the shortest-path (SP) rule

Select cloud; enable 3.StemClusterSP; click Apply.

![image42.png](img/image42.png)

Results: individual stems assigned stemoff IDs per point.

![image43.png](img/image43.png)

Individual-tree delineation with the isolated stems as prior information

Option 1: CrownOff3D

Select cloud; choose Mixedwood→UAV(stem explicit)→4.CrownOff3D→ treeisonet_uav_mixedwood_crownoff_esegformer3D_128_15cm(GPU4GB)→Download, Apply.

![image44.png](img/image44.png)

Results: Tree IDs appear in a new scalar field itc.

![image45.png](img/image45.png)

Option 2: CrownClusterSP (TreeISO + SP)

Select cloud; enable 4.CrownClusterSP; click Apply. Export stats → CSV with tree metrics.

![image46.png](img/image46.png)

![image47.png](img/image47.png)

- Note: CrownClusterSP segments trees into small initial clusters based a treeiso algorithm, and allocate those clusters to the isolated stems based on the shortest-path rule. This method produces less noise than CrownOff3D and provides greater flexibility for custom clustering parameters.
