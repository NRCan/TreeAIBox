# 4. TLS LiDAR

Site: Aspen trees located in the Eastern Slopes of the Canadian Rockies near Castle Mountain Resort (McCaffrey and Hopkinson, 2020)

Data: TLS_boreal_Aspen_2018.laz

Sensor: Teledyne Optech TLS (~3 400 pts/m²)

Load TLS_boreal_Aspen_2018.laz. Follows same steps as Section 4.2.2, using TLS-specific models.

TreeFiltering: treefiltering_tls_esegformer3D_128_8cm(GPU3GB).

![image58.png](img/image58.png)

![image59.png](img/image59.png)

![image60.png](img/image60.png)

TreeisoNet-StemCls: treeisonet_tls_boreal_stemcls_esegformer3D_128_4cm(GPU3GB).

![image61.png](img/image61.png)

![image62.png](img/image62.png)

TreeisoNet-TreeLoc: treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB).

![image63.png](img/image63.png)

StemClusterSP: individual-tree stem clustering and isolation based on the shortest-path rule.

![image64.png](img/image64.png)

Individual-tree delineation via CrownClusterSP or CrownOff3D: treeisonet_tls_boreal_crownoff_esegformer3D_128_15cm(GPU4GB).

![image65.png](img/image65.png)

![image66.png](img/image66.png)

![image67.png](img/image67.png)
