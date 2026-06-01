#!/usr/bin/env python3
"""
TreeAIBox cross-platform installer (Windows / macOS / Linux).

Why this exists
---------------
CloudCompare ships its own *embedded* Python (via the PythonRuntime plugin).
A CloudCompare upgrade can change that embedded Python's version (e.g. 3.10 ->
3.12), which silently invalidates every compiled wheel (torch, PyQt6, ...)
installed against the old one. Installing straight into the embedded
site-packages also needs admin rights on Windows and gets wiped by reinstalls.

This script instead builds an **isolated virtual environment outside the app**,
matching CloudCompare's embedded Python version, and installs all dependencies
there. You then point CloudCompare at it once
(plugins -> Python Plugin -> Show Settings -> "local" -> the env directory).
Because the env lives in user space, it:
  * needs no admin rights,
  * survives CloudCompare reinstalls/upgrades, and
  * only needs to be recreated if CloudCompare's Python *minor* version changes
    (just re-run this script).

The right torch build is chosen automatically:
  * Windows / Linux + NVIDIA GPU -> CUDA wheels (cu121)
  * Windows / Linux, no GPU       -> CPU wheels
  * macOS                         -> default PyPI wheels (CPU + Metal/MPS; CUDA
                                     does not exist on macOS)

Usage
-----
    python install.py                      # auto-detect everything
    python install.py --gpu cpu            # force CPU torch
    python install.py --cc-python <path>   # point at CloudCompare's python
    python install.py --env <dir>          # choose where the venv is created
    python install.py --recreate           # delete & rebuild the venv

Run it with any Python 3 you have; it only orchestrates subprocesses. The venv
itself is built from CloudCompare's embedded Python so the version always
matches.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Validated dependency versions (Python 3.12). Keep in sync with requirements.txt.
TORCH_VERSION = "2.5.1"
TORCHVISION_VERSION = "0.20.1"
TORCHAUDIO_VERSION = "2.5.1"
CUDA_INDEX = "https://download.pytorch.org/whl/cu121"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

HERE = Path(__file__).resolve().parent
REQUIREMENTS = HERE / "requirements.txt"


# --------------------------------------------------------------------------- #
# Discovery helpers
# --------------------------------------------------------------------------- #
def candidate_cc_pythons() -> list[Path]:
    """Best-effort list of where CloudCompare's embedded python might live."""
    cands: list[Path] = []
    if sys.platform.startswith("win"):
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            r"C:\CloudCompare",
            r"D:\CloudCompare",
            r"E:\CloudCompare",
        ]
        for r in roots:
            cands.append(Path(r) / "CloudCompare" / "plugins" / "Python" / "python.exe")
            cands.append(Path(r) / "plugins" / "Python" / "python.exe")
        # CloudCompare PythonRuntime stores the active env folder in the registry.
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\CCCorp\CloudCompare:PythonRuntime.Settings",
            )
            env_path, _ = winreg.QueryValueEx(key, "EnvPath")
            if env_path:
                cands.insert(0, Path(env_path) / "python.exe")
        except OSError:
            pass
    elif sys.platform == "darwin":
        for app in ("/Applications/CloudCompare.app", str(Path.home() / "Applications/CloudCompare.app")):
            base = Path(app) / "Contents"
            cands += [
                base / "plugins" / "Python" / "bin" / "python3",
                base / "Frameworks" / "Python" / "bin" / "python3",
                base / "Resources" / "python" / "bin" / "python3",
            ]
    else:  # Linux
        cands += [
            Path("/app/plugins/Python/bin/python3"),  # flatpak (inside sandbox)
            Path("/usr/lib/cloudcompare/plugins/Python/bin/python3"),
            Path.home() / ".local/share/CloudCompare/plugins/Python/bin/python3",
        ]
    return [c for c in cands if c.exists()]


def detect_cc_python(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"--cc-python does not exist: {p}")
        return p
    found = candidate_cc_pythons()
    if found:
        return found[0]
    msg = [
        "Could not auto-detect CloudCompare's embedded Python.",
        "Pass it explicitly, e.g.:",
    ]
    if sys.platform.startswith("win"):
        msg.append(r'    python install.py --cc-python "C:\Program Files\CloudCompare\plugins\Python\python.exe"')
    elif sys.platform == "darwin":
        msg.append("    python install.py --cc-python /Applications/CloudCompare.app/Contents/plugins/Python/bin/python3")
        msg.append("  (macOS often ships Python 3.11 inside the .app; or build a 3.11 venv yourself.)")
    else:
        msg.append("    # Linux flatpak runs Python inside the sandbox; you can also build a venv")
        msg.append("    # with a system python matching CloudCompare's version and point CC at it.")
        msg.append("    python install.py --base-python $(which python3.12)")
    sys.exit("\n".join(msg))


def python_version(py: Path) -> tuple[int, int, int]:
    out = subprocess.check_output(
        [str(py), "-c", "import sys;print('%d %d %d' % sys.version_info[:3])"],
        text=True,
    ).split()
    return tuple(int(x) for x in out)  # type: ignore[return-value]


def default_env_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "TreeAIBox" / "env"


def has_nvidia_gpu() -> bool:
    if sys.platform == "darwin":
        return False
    return shutil.which("nvidia-smi") is not None and (
        subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )


def venv_python(env_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def run(cmd: list[str]) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call(cmd)


def create_venv(base_python: Path, env_dir: Path, recreate: bool) -> Path:
    if env_dir.exists() and recreate:
        print(f"[*] Removing existing env: {env_dir}")
        shutil.rmtree(env_dir)
    if not env_dir.exists():
        print(f"[*] Creating isolated venv at: {env_dir}")
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        # No --system-site-packages on purpose: we do NOT want CloudCompare's
        # (possibly stale/mismatched) embedded packages leaking into the env.
        run([str(base_python), "-m", "venv", str(env_dir)])
    else:
        print(f"[*] Reusing existing venv at: {env_dir} (use --recreate to rebuild)")
    return venv_python(env_dir)


def pip(py: Path, *args: str) -> None:
    run([str(py), "-m", "pip", *args])


def install_torch(py: Path, gpu_mode: str) -> None:
    trio = [
        f"torch=={TORCH_VERSION}",
        f"torchvision=={TORCHVISION_VERSION}",
        f"torchaudio=={TORCHAUDIO_VERSION}",
    ]
    if sys.platform == "darwin":
        print("[*] Installing torch (macOS: default PyPI wheels, CPU + MPS)...")
        pip(py, "install", "--upgrade", *trio)
        return
    if gpu_mode == "cuda":
        print("[*] Installing CUDA torch (cu121)...")
        pip(py, "install", "--upgrade", "--index-url", CUDA_INDEX, *trio)
    else:
        print("[*] Installing CPU torch...")
        pip(py, "install", "--upgrade", "--index-url", CPU_INDEX, *trio)


def verify(py: Path) -> bool:
    print("\n[*] Verifying imports in the new environment...")
    probe = r"""
import importlib, sys
mods = ["numpy","requests","sklearn","skimage","timm","numpy_indexed",
        "numpy_groupies","circle_fit","cut_pursuit_py",
        "PyQt6.QtCore","PyQt6.QtWebEngineWidgets","torch","torchvision"]
ok = True
for m in mods:
    try:
        importlib.import_module(m)
        print("  OK  ", m)
    except Exception as e:
        ok = False
        print("  FAIL", m, "->", type(e).__name__, str(e)[:120])
try:
    import torch
    print("  torch", torch.__version__, "| cuda:", torch.cuda.is_available(),
          "| mps:", getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
except Exception:
    pass
sys.exit(0 if ok else 1)
"""
    return subprocess.run([str(py), "-c", probe]).returncode == 0


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Install TreeAIBox dependencies into an isolated venv.")
    ap.add_argument("--cc-python", help="Path to CloudCompare's embedded python (auto-detected if omitted).")
    ap.add_argument("--base-python", help="Python used to create the venv (defaults to CloudCompare's python so the version matches).")
    ap.add_argument("--env", help="Directory for the virtual environment (default: per-OS user data dir).")
    ap.add_argument("--gpu", choices=["auto", "cuda", "cpu"], default="auto", help="torch build to install (default: auto-detect NVIDIA GPU).")
    ap.add_argument("--recreate", action="store_true", help="Delete and rebuild the venv from scratch.")
    ap.add_argument("--no-verify", action="store_true", help="Skip the post-install import check.")
    args = ap.parse_args()

    if not REQUIREMENTS.exists():
        sys.exit(f"requirements.txt not found next to install.py ({REQUIREMENTS})")

    print("=" * 70)
    print(" TreeAIBox installer")
    print("=" * 70)

    cc_python = detect_cc_python(args.cc_python)
    cc_ver = python_version(cc_python)
    print(f"[*] CloudCompare Python : {cc_python}  (v{cc_ver[0]}.{cc_ver[1]}.{cc_ver[2]})")

    base_python = Path(args.base_python) if args.base_python else cc_python
    if args.base_python:
        b = python_version(base_python)
        if b[:2] != cc_ver[:2]:
            print(f"[!] WARNING: base python is {b[0]}.{b[1]} but CloudCompare uses "
                  f"{cc_ver[0]}.{cc_ver[1]}. Compiled wheels must match CloudCompare's "
                  f"minor version or the plugin will fail to import.")

    # torch only ships wheels for a window of Python versions; warn if outside it.
    if cc_ver[:2] not in {(3, 9), (3, 10), (3, 11), (3, 12)} and sys.platform != "darwin":
        print(f"[!] WARNING: torch {TORCH_VERSION} may not provide wheels for Python "
              f"{cc_ver[0]}.{cc_ver[1]}. If install fails, bump TORCH_VERSION at the top "
              f"of this script to a release that supports {cc_ver[0]}.{cc_ver[1]}.")

    env_dir = Path(args.env) if args.env else default_env_dir()

    gpu_mode = args.gpu
    if gpu_mode == "auto":
        gpu_mode = "cuda" if has_nvidia_gpu() else "cpu"
    print(f"[*] torch build         : {'CUDA (cu121)' if gpu_mode == 'cuda' and sys.platform != 'darwin' else 'default/CPU+MPS' if sys.platform == 'darwin' else 'CPU'}")
    print(f"[*] Environment dir     : {env_dir}")

    py = create_venv(base_python, env_dir, args.recreate)
    pip(py, "install", "--upgrade", "pip")
    install_torch(py, gpu_mode)
    print("[*] Installing remaining dependencies from requirements.txt...")
    pip(py, "install", "-r", str(REQUIREMENTS))

    ok = True
    if not args.no_verify:
        ok = verify(py)

    print("\n" + "=" * 70)
    if ok:
        print(" SUCCESS - dependencies installed.")
    else:
        print(" Dependencies installed, but some imports FAILED (see above).")
    print("=" * 70)
    print("\nNext step - point CloudCompare at this environment (one time):")
    print("  1. Launch CloudCompare.")
    print("  2. Menu: Plugins -> Python Plugin -> Show Settings.")
    print('  3. Choose "local" and select this folder:')
    print(f"        {env_dir}")
    print("  4. Restart CloudCompare.")
    print("\nNote: do NOT launch CloudCompare from a shell that has this venv")
    print("      'activated' (CloudCompare issue #2093). Just point it via the")
    print("      settings dialog above.")
    print("\nAfter a CloudCompare upgrade: only re-run this script if CloudCompare's")
    print("Python *minor* version changed (this script prints it above).")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
