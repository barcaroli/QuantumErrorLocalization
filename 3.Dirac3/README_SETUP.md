# Setting up the environment for `dirac_solver.py`

The virtual environment (`venv_dirac`) is not shipped with this folder because
it is large and tied to the machine it was created on. Recreate it as follows.

## Requirements
- Windows with **Python 3.9+** (tested with 3.11) available as `python` in PATH
- Internet connection (to download packages)
- For the real Dirac-3 device only: a QCi API token

## Quick way
Double-click `run_dirac.bat`. It creates `venv_dirac`, installs the packages,
asks which test record to solve (default `R6`) and whether to use the local
test mode or the real Dirac-3 device.

## Manual way
From a command prompt in this folder:

```bat
python -m venv venv_dirac
venv_dirac\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then run:

```bat
:: local test (classical stand-in solver from dwave-ocean-sdk, NOT Dirac-3)
python dirac_solver.py --record R6

:: real Dirac-3 device
python dirac_save_account.py        & rem one-time: saves your QCi API token
python dirac_solver.py --record R6 --mode cloud
```

## Files that must be in the same folder
`dirac_solver.py`, `ibm_qaoa_solver.py`, `generate_implied_edits.py`,
`domain_utils.py`, `check_generalized_localization.py`, `variables.csv`,
`rules_logic.csv`, `testdata.csv` (and `dirac_save_account.py` for cloud runs).

## Report
`run_dirac_report.bat` (or `python generate_dirac_report.py --mode cloud`
inside the activated venv) produces the report; it needs `venv_dirac` to exist.

## Notes
- `requirements.txt` pins the versions used so far; if installation fails on
  your Python version, drop the `==x.y.z` pins and install the latest.
- `ibm_qaoa_solver.py` is only reused here for shared helper code; Qiskit is
  not required for the Dirac runs.
- Do not commit or share your QCi API token (`token.txt` contains one).
