@echo off
REM =====================================================================
REM Run script for generate_dirac_report.py
REM Solves ALL records in testdata.csv in one run (not one at a time),
REM and produces the STATIS-style and LISTAIMP-style comparison tables.
REM
REM Requires: venv_dirac already created by run_dirac.bat (run that once
REM first if venv_dirac does not exist yet).
REM =====================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo Dirac-3 (QCi) batch report - Tunisia benchmark
echo ============================================
echo Working directory: %cd%
echo.

for %%F in (variables.csv rules_logic.csv testdata.csv dirac_solver.py generate_dirac_report.py ibm_qaoa_solver.py generate_implied_edits.py check_generalized_localization.py) do (
    if not exist %%F (
        echo ERROR: required file %%F not found in %cd%
        pause
        exit /b 1
    )
)

if not exist venv_dirac (
    echo Virtual environment "venv_dirac" not found.
    echo Run run_dirac.bat once first to create it and install packages.
    pause
    exit /b 1
)

call venv_dirac\Scripts\activate.bat

echo.
echo Choose mode:
echo   1 - Local test (classical stand-in solver, NOT Dirac-3, no account needed)
echo   2 - Real Dirac-3 device (cloud, needs saved QCi API token, one job per record)
set /p TARGET="Enter 1 or 2 [default 1]: "
if "%TARGET%"=="" set TARGET=1

if "%TARGET%"=="2" (
    set MODE_ARG=--mode cloud
    if not exist "%USERPROFILE%\.qci\config.json" (
        echo.
        echo No saved QCi credentials found. Run dirac_save_account.py first,
        echo or run_dirac.bat once with option 2 to set it up.
        pause
        exit /b 1
    )
) else (
    set MODE_ARG=
)

echo.
echo Running generate_dirac_report.py !MODE_ARG! ...
echo ---------------------------------------------------------------------
python generate_dirac_report.py !MODE_ARG!
echo ---------------------------------------------------------------------

call venv_dirac\Scripts\deactivate.bat

pause
endlocal
