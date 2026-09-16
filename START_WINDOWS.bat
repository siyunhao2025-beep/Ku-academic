@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" goto ready
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto fail
goto ready
:use_python
python -m venv .venv
if errorlevel 1 goto fail
:ready
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'"
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" scripts\research.py doctor
if errorlevel 1 goto fail
if exist "runs\first-demo" goto done
".venv\Scripts\python.exe" scripts\quickstart.py runs\first-demo
if errorlevel 1 goto fail
:done
echo.
echo Ready. Open README.md and docs\GETTING_STARTED.md for research tasks.
echo Existing demo data is preserved. This demo is NOT a research result.
pause
exit /b 0
:fail
echo.
echo Setup failed. Install Python 3.10+ and check the error above.
pause
exit /b 1
