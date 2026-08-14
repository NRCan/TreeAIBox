#!/usr/bin/env python3
"""
Launcher script for TreeAIBox Field Assignment Web Studio (Django)
==================================================================

Starts the local Django web application and opens it in your default web browser.

Usage:
    python scripts/run_web_app.py [--port 8000]
"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

def main():
    base_dir = Path(__file__).resolve().parent.parent / "web_assignment"
    manage_py = base_dir / "manage.py"

    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================")
    print(f"  Starting TreeAIBox Field Assignment Web Studio")
    print(f"  URL: {url}")
    print(f"=======================================================\n")

    # Open browser slightly after launching
    import threading
    def _open_browser():
        time.sleep(1.2)
        print(f"Opening browser at {url}...")
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    cmd = [sys.executable, str(manage_py), "runserver", f"127.0.0.1:{port}"]
    try:
        subprocess.run(cmd, cwd=str(base_dir))
    except KeyboardInterrupt:
        print("\nStopping TreeAIBox Web Studio...")

if __name__ == '__main__':
    main()
