"""
One-time setup: save your IBM Quantum API key to disk so that
ibm_qaoa_solver.py --hardware can authenticate without ever handling the
token itself.

Where to get the token
-----------------------
1. Log in at https://quantum.cloud.ibm.com
2. Open the dashboard -> copy your API key (44 characters).
3. (Optional but recommended) copy the CRN of the instance you want to
   use -- Instances tab -> copy icon next to the instance row. If you
   skip this, all instances visible to your account will be used.

What this script does
----------------------
It calls QiskitRuntimeService.save_account(), which writes your
credentials to a local, plain-text file:
    Windows: %USERPROFILE%\\.qiskit\\qiskit-ibm.json
    Linux/Mac: $HOME/.qiskit/qiskit-ibm.json

Because the file is plain text, only run this on a machine you trust.
After running it once, ibm_qaoa_solver.py --hardware will authenticate
automatically via QiskitRuntimeService() -- no token is passed on the
command line or stored in any of the benchmark scripts.

Usage
-----
    python ibm_save_account.py
    (you will be prompted for the token and, optionally, the instance CRN)
"""

from qiskit_ibm_runtime import QiskitRuntimeService


def main():
    token = input("IBM Quantum API key (44 characters): ").strip()
    if not token:
        print("No token entered -- aborting.")
        return

    instance = input(
        "Instance CRN (optional, press Enter to use all available "
        "instances): "
    ).strip()

    QiskitRuntimeService.save_account(
        token=token,
        channel="ibm_quantum_platform",
        instance=instance if instance else None,
        overwrite=True,
        set_as_default=True,
    )
    print("\nCredentials saved. You can now run:")
    print("    python ibm_qaoa_solver.py --hardware")


if __name__ == "__main__":
    main()
