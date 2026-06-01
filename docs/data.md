# Demo data

The workshop tutorial uses five LiDAR point clouds spanning UAV, ALS, and TLS sensors.

## Download

!!! download "All datasets (single zip, ≈ 263 MB)"
    **[CSRS2025_Lethbridge_Workshop_TreeAIBoxPlugin_June16.zip](https://github.com/NRCan/TreeAIBox/releases/download/workshop-2025/CSRS2025_Lethbridge_Workshop_TreeAIBoxPlugin_June16.zip)**

    Mirror (Google Drive): <https://drive.google.com/file/d/14HTZ12Vw2iCs-7ewJePhJwJHEurv5Z8S/>

Unzip anywhere, then drag each `.laz` into CloudCompare as you reach it in the tutorial.

## Contents

| Sensor | File | Size | Used in |
|---|---|---|---|
| UAV LiDAR | `UAV_reclamation_GP262_20230809_aoi.laz` | 13 MB | [UAV — reclamation](tutorial-uav.md) |
| UAV LiDAR | `UAV_mixedwood_NIBIO_plot1.laz` | 49 MB | [UAV — mixedwood](tutorial-uav.md) |
| ALS | `ALS_Castle_C1_20180716a.laz` | 8 MB | [ALS](tutorial-als.md) |
| TLS | `TLS_boreal_Aspen_2018.laz` | 69 MB | [TLS](tutorial-tls.md) |
| TLS | `GUY02_000.laz` | 2 MB | [QSM / architecture](tutorial-qsm.md) |

!!! note "Maintainers"
    The download link points to a GitHub Release asset. To publish it, create a
    release tagged `workshop-2025` on the repository and attach the zip (see the
    project README / repository maintainer notes). Update the owner in the link above
    if you host the release on a fork rather than `NRCan/TreeAIBox`.
