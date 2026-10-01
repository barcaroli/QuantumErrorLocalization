@echo off
REM =====================================================================
REM Run script for dirac_solver.py
REM Tunisia education-chain Fellegi-Holt benchmark (QCi Dirac-3)
REM
REM Requires: Python 3.9+ in PATH.
REM Expects the following files in the same folder as this .bat:
REM   dirac_solver.py, dirac_save_account.py, ibm_qaoa_solver.py,
REM   generate_implied_edits.py, check_generalized_localization.py,
REM   variables.csv, rules_logic.csv, testdata.csv
REM =====================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo Dirac-3 (QCi) solver - Tunisia benchmark
echo ============================================
echo Working directory: %cd%
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

for %%F in (variables.csv rules_logic.csv testdata.csv dirac_solver.py ibm_qaoa_solver.py generate_implied_edits.py check_generalized_localization.py) do (
    if not exist %%F (
        echo ERROR: required file %%F not found in %cd%
        pause
        exit /b 1
    )
)

if not exist venv_dirac (
    echo Creating virtual environment "venv_dirac"...
    python -m venv venv_dirac
    if errorlevel 1 (
        echo ERROR: failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call venv_dirac\Scripts\activate.bat

echo.
echo Installing/updating required packages (qci-client, dwave-ocean-sdk)...
echo (dwave-ocean-sdk is used only as the classical local-test stand-in solver)
python -m pip install --quiet --upgrade pip
python -m pip install --quiet qci-client dwave-ocean-sdk
if errorlevel 1 (
    echo ERROR: package installation failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
set /p RECORD_ID="Which test record to solve (from testdata.csv)? [default R6]: "
if "%RECORD_ID%"=="" set RECORD_ID=R6

echo.
echo Choose mode:
echo   1 - Local test (classical stand-in solver, NOT Dirac-3, no account needed)
echo   2 - Real Dirac-3 device (cloud, needs saved QCi API token)
set /p TARGET="Enter 1 or 2 [default 1]: "
if "%TARGET%"=="" set TARGET=1

if "%TARGET%"=="2" (
    set MODE_ARG=--mode cloud
    if not exist "%USERPROFILE%\.qci\config.json" (
        echo.
        echo No saved QCi credentials found.
        echo Running the one-time setup now -- you will be asked for your
        echo QCi API token.
        echo.
        python dirac_save_account.py
        if errorlevel 1 (
            echo ERROR: account setup failed.
            pause
            exit /b 1
        )
    )
) else (
    set MODE_ARG=
)

echo.
echo Running dirac_solver.py --record %RECORD_ID% !MODE_ARG! ...
echo ---------------------------------------------------------------------
python dirac_solver.py --record %RECORD_ID% !MODE_ARG!
set SOLVER_EXIT=%errorlevel%
echo ---------------------------------------------------------------------

if not "%SOLVER_EXIT%"=="0" (
    echo.
    echo The solver exited with an error ^(code %SOLVER_EXIT%^). See output above.
) else (
    echo.
    echo Done. See the result above.
)

call venv_dirac\Scripts\deactivate.bat

pause
endlocal
