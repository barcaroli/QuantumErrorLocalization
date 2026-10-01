@echo off
REM =====================================================================
REM Run script for ibm_qaoa_solver.py
REM Tunisia education-chain Fellegi-Holt benchmark (IBM Quantum / QAOA)
REM
REM Requires: Python 3.9+ available as "python" in PATH.
REM Expects the following files in the same folder as this .bat:
REM   ibm_qaoa_solver.py, ibm_save_account.py,
REM   generate_implied_edits.py, check_generalized_localization.py,
REM   variables.csv, rules_logic.csv, testdata.csv
REM =====================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo IBM Quantum (QAOA) solver - Tunisia benchmark
echo ============================================
echo Working directory: %cd%
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3.9+ and make sure "python" is available from cmd.
    pause
    exit /b 1
)

for %%F in (variables.csv rules_logic.csv testdata.csv ibm_qaoa_solver.py generate_implied_edits.py check_generalized_localization.py) do (
    if not exist %%F (
        echo ERROR: required file %%F not found in %cd%
        pause
        exit /b 1
    )
)

if not exist venv_qaoa (
    echo Creating virtual environment "venv_qaoa"...
    python -m venv venv_qaoa
    if errorlevel 1 (
        echo ERROR: failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call venv_qaoa\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: failed to activate the virtual environment.
    pause
    exit /b 1
)

echo.
echo Installing/updating required packages...
echo (qiskit, qiskit-aer, qiskit-ibm-runtime, scipy, numpy)
python -m pip install --quiet --upgrade pip
python -m pip install --quiet qiskit qiskit-aer qiskit-ibm-runtime scipy numpy
if errorlevel 1 (
    echo ERROR: package installation failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
set /p RECORD_ID="Which test record to solve (from testdata.csv)? [default R6]: "
if "%RECORD_ID%"=="" set RECORD_ID=R6

echo.
echo Choose execution target:
echo   1 - Local simulator (Aer, no IBM account needed)
echo   2 - Real IBM Quantum hardware (requires a saved API key)
set /p TARGET="Enter 1 or 2 [default 1]: "
if "%TARGET%"=="" set TARGET=1

if "%TARGET%"=="2" (
    if not exist "%USERPROFILE%\.qiskit\qiskit-ibm.json" (
        echo.
        echo No saved IBM Quantum credentials found.
        echo Running the one-time setup now -- you will be asked for your
        echo IBM Quantum API key ^(from https://quantum.cloud.ibm.com^).
        echo.
        python ibm_save_account.py
        if errorlevel 1 (
            echo ERROR: account setup failed.
            pause
            exit /b 1
        )
    )
    set EXTRA_ARGS=--hardware
) else (
    set EXTRA_ARGS=
)

echo.
echo Running ibm_qaoa_solver.py --record %RECORD_ID% !EXTRA_ARGS! ...
echo ---------------------------------------------------------------------
python ibm_qaoa_solver.py --record %RECORD_ID% !EXTRA_ARGS!
set SOLVER_EXIT=%errorlevel%
echo ---------------------------------------------------------------------

if not "%SOLVER_EXIT%"=="0" (
    echo.
    echo The solver exited with an error ^(code %SOLVER_EXIT%^). See output above.
) else (
    echo.
    echo Done. See the QAOA result above.
)

call venv_qaoa\Scripts\deactivate.bat

pause
endlocal
