# Setting up the environment for `ibm_qaoa_solver.py`

The virtual environment (`venv_qaoa`) is not shipped with this folder because
it is large and tied to the machine it was created on. Recreate it as follows.

## Requirements
- Windows with **Python 3.9+** (tested with 3.11) available as `python` in PATH
- Internet connection (to download packages)
- For real hardware only: an IBM Quantum account and API key
  (https://quantum.cloud.ibm.com)

## Quick way
Double-click `run_ibm_qaoa.bat`. It creates `venv_qaoa`, installs the
packages, asks which test record to solve (default `R6`) and whether to use
the local simulator or IBM hardware.

## Manual way
From a command prompt in this folder:

```bat
python -m venv venv_qaoa
venv_qaoa\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then run:

```bat
:: local simulator (Aer, no IBM account needed)
python ibm_qaoa_solver.py --record R6

:: real IBM Quantum hardware
python ibm_save_account.py          & rem one-time: saves your API key
python ibm_qaoa_solver.py --record R6 --hardware
```

## Files that must be in the same folder
`ibm_qaoa_solver.py`, `generate_implied_edits.py`, `domain_utils.py`,
`check_generalized_localization.py`, `variables.csv`, `rules_logic.csv`,
`testdata.csv` (and `ibm_save_account.py` for hardware runs).

## Report
After a solver run, `run_report.bat` (needs `venv_qaoa` to exist) produces the
SCIA-style summary via `generate_scia_style_report.py`.

## Notes
- `requirements.txt` pins the versions used so far; if installation fails on
  your Python version, drop the `==x.y.z` pins and install the latest.
- Do not commit or share your IBM API key (`set_token.txt` contains one).
