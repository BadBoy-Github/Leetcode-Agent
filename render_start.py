import os
import subprocess
import sys


def main() -> int:
    port = os.environ.get("PORT", "8501")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError(f"PORT must be an integer from 1 to 65535; got {port!r}")

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address=0.0.0.0",
        f"--server.port={port}",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--server.headless=true",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
