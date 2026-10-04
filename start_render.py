"""Start Streamlit on the port supplied by Render, without shell expansion."""
from pathlib import Path
import os
import sys


def main():
    os.chdir(Path(__file__).resolve().parent)
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    os.execv(sys.executable, [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address=0.0.0.0", f"--server.port={port}",
        "--server.headless=true",
    ])


if __name__ == "__main__":
    main()
