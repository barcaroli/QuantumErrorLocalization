"""
One-time setup: save your D-Wave Leap API token to disk so that
dwave_solver.py --sampler hybrid / --sampler qpu can authenticate
without ever handling the token itself.

Where to get the token
-----------------------
1. Log in at https://cloud.dwavesys.com/leap/
2. Dashboard -> API Token (copy it).

What this script does
----------------------
It writes a standard Ocean SDK config file to:
    Windows: %USERPROFILE%\\.config\\dwave\\dwave.conf
    Linux/Mac: ~/.config/dwave/dwave.conf

This is the same mechanism the official `dwave config create` wizard
uses -- this script just runs it non-interactively with sane defaults.
After running it once, dwave_solver.py --sampler hybrid/qpu will
authenticate automatically -- no token is passed on the command line or
stored in any of the benchmark scripts.

Alternative (no file, session-only): instead of running this script,
you can just set an environment variable in the current terminal:
    set DWAVE_API_TOKEN=your-token-here      (Windows cmd)
    $env:DWAVE_API_TOKEN="your-token-here"   (PowerShell)

Usage
-----
    python dwave_save_account.py
    (you will be prompted for the token)
"""

from dwave.cloud.config import update_config


def main():
    token = input("D-Wave Leap API token: ").strip()
    if not token:
        print("No token entered -- aborting.")
        return

    path = update_config(options={"token": token})
    print(f"\nCredentials saved to: {path}")
    print("You can now run:")
    print("    python dwave_solver.py --sampler hybrid")
    print("    python dwave_solver.py --sampler qpu")


if __name__ == "__main__":
    main()
