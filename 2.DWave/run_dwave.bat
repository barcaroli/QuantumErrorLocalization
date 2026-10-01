@echo off
REM =====================================================================
REM Run script for dwave_solver.py
REM Tunisia education-chain Fellegi-Holt benchmark (D-Wave quantum annealing)
REM
REM Requires: Python 3.9+ in PATH.
REM Expects the following files in the same folder as this .bat:
REM   dwave_solver.py, dwave_save_account.py, ibm_qaoa_solver.py,
REM   generate_implied_edits.py, check_generalized_localization.py,
REM   variables.csv, rules_logic.csv, testdata.csv
REM =====================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo D-Wave quantum annealing solver - Tunisia benchmark
echo ============================================
echo Working directory: %cd%
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

for %%F in (variables.csv rules_logic.csv testdata.csv dwave_solver.py ibm_qaoa_solver.py generate_implied_edits.py check_generalized_localization.py) do (
    if not exist %%F (
        echo ERROR: required file %%F not found in %cd%
        pause
        exit /b 1
    )
)

if not exist venv_dwave (
    echo Creating virtual environment "venv_dwave"...
    python -m venv venv_dwave
    if errorlevel 1 (
        echo ERROR: failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call venv_dwave\Scripts\activate.bat

echo.
echo Installing/updating required packages (dwave-ocean-sdk)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet dwave-ocean-sdk
if errorlevel 1 (
    echo ERROR: package installation failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
set /p RECORD_ID="Which test record to solve (from testdata.csv)? [default R6]: "
if "%RECORD_ID%"=="" set RECORD_ID=R6

echo.
echo Choose sampler:
echo   1 - Local simulated annealing (no D-Wave account needed)
echo   2 - D-Wave Leap hybrid solver (cloud, needs saved API token)
echo   3 - Real D-Wave QPU (cloud, needs saved API token)
set /p TARGET="Enter 1, 2 or 3 [default 1]: "
if "%TARGET%"=="" set TARGET=1

if "%TARGET%"=="2" (
    set SAMPLER_ARG=--sampler hybrid
) else if "%TARGET%"=="3" (
    set SAMPLER_ARG=--sampler qpu
) else (
    set SAMPLER_ARG=
)

if not "%TARGET%"=="1" (
    if not exist "%USERPROFILE%\.config\dwave\dwave.conf" (
        echo.
        echo No saved D-Wave credentials found.
        echo Running the one-time setup now -- you will be asked for your
        echo D-Wave Leap API token ^(from https://cloud.dwavesys.com/leap/^).
        echo.
        python dwave_save_account.py
        if errorlevel 1 (
            echo ERROR: account setup failed.
            pause
            exit /b 1
        )
    )
)

echo.
echo Running dwave_solver.py --record %RECORD_ID% !SAMPLER_ARG! ...
echo ---------------------------------------------------------------------
python dwave_solver.py --record %RECORD_ID% !SAMPLER_ARG!
set SOLVER_EXIT=%errorlevel%
echo ---------------------------------------------------------------------

if not "%SOLVER_EXIT%"=="0" (
    echo.
    echo The solver exited with an error ^(code %SOLVER_EXIT%^). See output above.
) else (
    echo.
    echo Done. See the D-Wave result above.
)

call venv_dwave\Scripts\deactivate.bat

pause
endlocal
