# QuantumErrorLocalization

Quantum and quantum-inspired solvers for **error localization** in statistical
data editing (the Fellegi-Holt problem), benchmarked against the classical
CONCORD/SCIA software.

## Purpose

In census and survey processing, a record that violates edit rules (for example
*"a person aged 0-14 cannot have a higher-education level"*) must be corrected.
The **Fellegi-Holt principle** says to change the fewest fields possible,
weighted by how much each field is trusted. Finding that minimum set of fields
is a *minimum-cost hitting-set* problem, which is NP-hard in general and grows
quickly with the number of variables and rules.

This project recasts error localization as a binary optimization problem (a
penalized pseudo-Boolean cost function, expressed as a QUBO or Ising
Hamiltonian) and solves it on different quantum platforms. It then checks
whether each platform returns the same minimum-cost corrections as CONCORD/SCIA.

The test case is a dedicated example usual in households surveys, with seven
variables: `ENROLL`, `EDULEV`, `DEGREE`, `DEGLEV`, `DEGCTY`, `FIELD` and `AGE`.
It has 11 test records (R1-R11) with known expected answers, including a
genuine degree-3 rule that tests whether each solver handles higher-order terms
correctly.

## How it works

1. **Problem definition**: `variables.csv` (fields, costs, domains),
   `rules_logic.csv` (edit rules) and `testdata.csv` (records).
2. **Edit closure**: `generate_implied_edits.py` derives the implied edits by
   Fellegi-Holt resolution. The explicit rules alone are not enough for a
   correct minimum.
3. **Cost function**: the edits violated by a record are turned into a
   penalized cost function over binary "change this field" variables.
4. **Solve**: the same problem goes to a quantum or quantum-inspired solver.
5. **Cross-check**: each result is compared with brute-force enumeration and
   with the CONCORD/SCIA reference output.
6. **Report**: a SCIA-style summary table (`*_statis_report.txt`) lists, per
   variable, how often it was imputed and which edits were responsible.

## Repository layout

| Folder | Contents |
|---|---|
| `0.Concord` | CONCORD/SCIA reference run (`VARDOM`, `REGOLE`, `LISTAIMP`, `STATIS`, ...) and `TESTDATA_README.txt` with the 11 test records and expected solutions |
| `1.IBM_Quantum` | **QAOA** on IBM Quantum. Parameters are optimized on the Aer simulator, with an optional single confirmatory run on real hardware (`ibm_qaoa_solver.py`) |
| `2.DWave` | **Quantum annealing** on D-Wave: local simulated annealing, Leap hybrid, or real QPU (`dwave_solver.py`) |
| `3.Dirac3` | **QCi Dirac-3** (Entropy Quantum Computing), with a local classical stand-in for testing (`dirac_solver.py`), plus `parse_real_case.py` for extending the closure to real VARDOM/REGOLE files |

Each platform folder is self-contained and has its own `README_SETUP.md`,
`requirements.txt` and a `run_*.bat` launcher.

## Quick start

1. Pick a platform folder, for example `1.IBM_Quantum`.
2. Follow its `README_SETUP.md`, or double-click the `run_*.bat` file, which
   creates the virtual environment and installs the dependencies.
3. Choose a test record (default `R6`) and a local or cloud target. Local mode
   needs no account.

```bat
cd 1.IBM_Quantum
python ibm_qaoa_solver.py --record R6          :: simulator
python ibm_qaoa_solver.py --record R6 --hardware
```

## Notes

- Cloud and hardware runs need personal API credentials (IBM Quantum, D-Wave
  Leap, QCi). Never commit them. The token files in the platform folders
  (`set_token.txt`, `token.txt`) should be excluded from version control.
- Virtual environments (`venv_*`) are not part of the repository. They are
  recreated from `requirements.txt`.
