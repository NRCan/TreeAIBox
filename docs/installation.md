# Installation

CloudCompare ships its **own embedded Python**, so you do **not** need to install
Python yourself. Pick your operating system below.

!!! info "Before you start"
    - **Internet access is required** — the installer downloads the AI/runtime packages (≈ 2.5 GB with CUDA).
    - **After updating CloudCompare, simply run the installer again** — it repairs the plugin for the new Python version.

## :material-microsoft-windows: Windows — one-click installer (recommended)

1. Install the latest **CloudCompare** from [cloudcompare.org/release](https://www.cloudcompare.org/release/).
2. Download **`TreeAIBox_Plugin_Installer.exe`** from the [releases page](https://github.com/NRCan/TreeAIBox/releases).
3. **Right-click → Run as administrator**, then follow the prompts.

The installer auto-detects CloudCompare, detects your NVIDIA GPU (installs CUDA
PyTorch, otherwise CPU PyTorch), installs all packages into CloudCompare's embedded
Python, copies the plugin files (including `LICENSE.txt`), and registers TreeAIBox.
Restart CloudCompare, then launch **TreeAIBox** from the Python plugin toolbar.

!!! tip "Windows SmartScreen"
    If SmartScreen warns about an unknown publisher, click **More info → Run anyway**.

## :material-apple: macOS

1. Install a CloudCompare build that includes the Python plugin.
2. Download or clone the [repository](https://github.com/NRCan/TreeAIBox).
3. In Finder, double-click **`install_macos.command`** (the first time you may need
   `chmod +x install_macos.command`, or run `bash install_macos.command` in Terminal).
   It builds an isolated environment matching CloudCompare's Python and installs all
   packages (CPU + Apple **Metal/MPS**; CUDA does not exist on macOS).
4. In CloudCompare: **Plugins → Python Plugin → Show Settings → "local"**, and select
   the printed environment folder (`~/Library/Application Support/TreeAIBox/env`). Restart CloudCompare.
5. Register the plugin: **Python Plugin → Register a script** → select `TreeAIBox.py`.

## :material-linux: Linux

1. Install CloudCompare (flatpak, or a build that includes the Python plugin).
2. Download or clone the [repository](https://github.com/NRCan/TreeAIBox).
3. Run **`bash install_linux.sh`**. It installs all packages (CUDA for NVIDIA GPUs,
   otherwise CPU) into an isolated environment; for the flatpak it also grants the
   required filesystem access.
4. In CloudCompare: **Plugins → Python Plugin → Show Settings → "local"**, select the
   printed environment folder (`~/.local/share/TreeAIBox/env`). Restart CloudCompare.
5. Register the plugin: **Python Plugin → Register a script** → select `TreeAIBox.py`.

## :material-wrench: Advanced / manual (any OS)

`install.py` is the cross-platform engine used by the macOS/Linux scripts. Run it
directly with **CloudCompare's own Python**:

```bash
"<CloudCompare-python>" install.py             # build environment + install dependencies
"<CloudCompare-python>" install.py --gpu cpu   # force CPU PyTorch
"<CloudCompare-python>" install.py --recreate  # rebuild the environment from scratch
```

Then point CloudCompare at the printed environment via **Plugins → Python Plugin →
Show Settings → "local"**, and register `TreeAIBox.py`.

## Verify the installation

Launch CloudCompare. In the Python toolbar → **Script Register**, confirm **TreeAIBox**
appears, then continue to the [workshop tutorial](data.md).

## Uninstall (optional)

In CloudCompare: **Remove Script → TreeAIBox**. Then delete:

- `…\CloudCompare\plugins\Python\Plugins\TreeAIBox`
- `%LOCALAPPDATA%\CloudCompare` (Windows) and any `TreeAIBox/env` environment folder.
