"""
One-time setup: save your QCi API token to disk so that
dirac_solver.py --mode cloud can authenticate without ever handling the
token itself.

Where to get the token
-----------------------
Request a QCi account and API token at:
    https://quantumcomputinginc.com/learn/tutorials-and-use-cases/quick-start-on-cloud
You will receive the token by email.

What this script does
----------------------
QCi's qci-client package does not provide a built-in persistent config
file (unlike IBM's QiskitRuntimeService or D-Wave's Ocean SDK) -- it
normally expects the QCI_TOKEN and QCI_API_URL environment variables to
be set for every session. This script writes a small local JSON file
instead, so dirac_solver.py can pick up your credentials automatically
without you having to re-set environment variables every time:
    Windows: %USERPROFILE%\\.qci\\config.json
    Linux/Mac: ~/.qci/config.json

Alternative (no file, session-only): instead of running this script,
you can just set environment variables in the current terminal:
    set QCI_TOKEN=your-token-here          (Windows cmd)
    set QCI_API_URL=https://api.qci-prod.com

Usage
-----
    python dirac_save_account.py
    (you will be prompted for the token; the API URL defaults to
    https://api.qci-prod.com unless you enter a different one)
"""

import json
from pathlib import Path

DEFAULT_URL = "https://api.qci-prod.com"
CONFIG_PATH = Path.home() / ".qci" / "config.json"


def main():
    token = input("QCi API token: ").strip()
    if not token:
        print("No token entered -- aborting.")
        return

    url = input(f"QCi API URL [default: {DEFAULT_URL}]: ").strip() or DEFAULT_URL

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"token": token, "url": url}, indent=2))

    print(f"\nCredentials saved to: {CONFIG_PATH}")
    print("You can now run:")
    print("    python dirac_solver.py --mode cloud")


if __name__ == "__main__":
    main()
