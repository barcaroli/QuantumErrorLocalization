# Setting up the environment for `dwave_solver.py`

This folder does not ship a virtual environment (`venv_dwave`): it is large
and tied to the machine it was created on. Create it as follows.

## Requirements
- Windows with **Python 3.9+** available as `python` in PATH
- Internet connection (to download packages)
- For the Leap hybrid solver or the real QPU only: a D-Wave Leap API token
  (https://cloud.dwavesys.com/leap/)

## Quick way
Double-click `run_dwave.bat`. It creates `venv_dwave`, installs the packages,
asks which test record to solve (default `R6`) and which sampler to use
(local simulated annealing, Leap hybrid, or real QPU).

## Manual way
From a command prompt in this folder:

```bat
python -m venv venv_dwave
venv_dwave\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then run:

```bat
:: local simulated annealing (no D-Wave account needed)
python dwave_solver.py --record R6

:: cloud samplers (one-time: saves your API token first)
python dwave_save_account.py
python dwave_solver.py --record R6 --sampler hybrid
python dwave_solver.py --record R6 --sampler qpu
```

## Files that must be in the same folder
`dwave_solver.py`, `ibm_qaoa_solver.py`, `generate_implied_edits.py`,
`domain_utils.py`, `check_generalized_localization.py`, `variables.csv`,
`rules_logic.csv`, `testdata.csv` (and `dwave_save_account.py` for cloud runs).

## Report
`python generate_dwave_report.py` (inside the activated venv) produces the
report.

## Notes
- `ibm_qaoa_solver.py` is only reused here for shared helper code; Qiskit is
  not required for the D-Wave runs.
- Do not share your D-Wave API token.
