@echo off
REM =====================================================================
REM Run script for generate_scia_style_report.py
REM Produces a CONCORD/SCIA-style summary table from the QAOA results,
REM for comparison with STATIS.Example_Tunisia.
REM
REM Requires: Python 3.9+ in PATH, and venv_qaoa already set up by
REM run_ibm_qaoa.bat (run that once first if venv_qaoa does not exist yet).
REM =====================================================================

setlocal

cd /d "%~dp0"

echo ============================================
echo QAOA SCIA-style report generator
echo ============================================
echo Working directory: %cd%
echo.

for %%F in (variables.csv rules_logic.csv testdata.csv ibm_qaoa_solver.py generate_scia_style_report.py generate_implied_edits.py check_generalized_localization.py) do (
    if not exist %%F (
        echo ERROR: required file %%F not found in %cd%
        pause
        exit /b 1
    )
)

if not exist venv_qaoa (
    echo Virtual environment "venv_qaoa" not found.
    echo Run run_ibm_qaoa.bat once first to create it and install packages.
    pause
    exit /b 1
)

call venv_qaoa\Scripts\activate.bat

echo.
echo Running generate_scia_style_report.py ...
echo ---------------------------------------------------------------------
python generate_scia_style_report.py
echo ---------------------------------------------------------------------

call venv_qaoa\Scripts\deactivate.bat

pause
endlocal
