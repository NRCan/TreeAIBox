# TreeAIBox

A CloudCompare Python plugin providing a unified GUI for deep-learning LiDAR
processing of forest and tree point clouds — tree/ground filtering, individual-tree
segmentation, wood/stem classification, and QSM reconstruction across TLS, ALS, and
UAV data.

This site covers **installation** and a hands-on **workshop tutorial** that walks
through every module on real demo datasets.

## Get started

- :material-download: **[Install the plugin](installation.md)** — one-click on Windows; scripts for macOS and Linux.
- :material-database: **[Get the demo data](data.md)** — the five LiDAR clouds used in the tutorial.
- :material-school: **Workshop tutorial** — [UAV](tutorial-uav.md) · [ALS](tutorial-als.md) · [TLS](tutorial-tls.md) · [QSM](tutorial-qsm.md)

## What you will learn

By the end of the tutorial you will be able to:

- Install and configure the TreeAIBox plugin in CloudCompare.
- Automatically separate tree and ground layers, detect stem/treetop locations,
  delineate 3D tree boundaries, and reconstruct branch structure from TLS, ALS, and UAV LiDAR.
- Perform manual refinement and interactive annotation of tree crowns.
- Export individual-tree outputs for downstream analysis.

## Prerequisites

- **CloudCompare** (latest release) with the Python plugin enabled.
- Basic familiarity with point-cloud navigation in CloudCompare.
- An NVIDIA GPU + CUDA drivers are recommended (the plugin falls back to CPU, which is slower).

!!! note
    You do **not** need to install Python — CloudCompare ships its own. See
    [Installation](installation.md).
