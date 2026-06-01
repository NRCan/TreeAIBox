# 5. QSM / Architecture

Site: Tropical trees scan datasets provided by Guyana Forestry Commission (Gonzalez de Tanago et al. 2018 and Lau et al. 2019)

Remove previous clouds; load GUY02_000.laz; Apply, Yes.

Select the point cloud. In Properties, set Point size to 3 for clarity.

![image68.png](img/image68.png)

Select cloud; Branch→woodcls_branch_tls_segformer3D_128_2.5cm(GPU3GB)→Download, Apply.

![image69.png](img/image69.png)

Results: wood points in red and other leafy points in blue in a new scalar field branchcls.

![image70.png](img/image70.png)

Select cloud; Stem→woodcls_stem_tls_segformer3D_128_4cm(GPU3GB)→Download, Apply.

![image71.png](img/image71.png)

Results: stem points in red and other points in blue in a new scalar field stemcls.

![image72.png](img/image72.png)

- (Optional) Refine stem label via Filter points , Segment , Merge , and Arithmetic .

![image36.png](img/image36.png)

![image37.png](img/image37.png)

![image38.png](img/image38.png)

![image73.png](img/image73.png)

Switch to the QSM tab. Customize the parameters in the Initial segmentation: cut-pursuit panel, and click Initial segmentation button. A new scalar field init_segs is then created.

![image74.png](img/image74.png)

For clearer visualization, convert init_segs scalar field to random RGB: Edit → Scalar fields → Convert to random RGB.

![image75.png](img/image75.png)

Customize the parameters in the Skeletonization panel, and click Skeletonization and Export.

![image76.png](img/image76.png)

Results: tree skeleton curves and meshes

![image77.png](img/image77.png)

![image78.png](img/image78.png)

Click Open output path (tree structure as xml). Two files are created: GUY02_000.laz_wood.xml and GUY02_000.laz_woodobj.obj. The first records tree architecture; the latter provides 3D mesh objects for other software.

![image79.png](img/image79.png)
