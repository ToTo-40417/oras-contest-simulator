@echo off
setlocal
pushd "%~dp0" || exit /b 1
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3 -B -m oras_gui.server
    goto :finished
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    python -B -m oras_gui.server
    goto :finished
)
echo Python 3.11 or newer is required.
echo https://www.python.org/downloads/
pause
popd
exit /b 1

:finished
set "status=%errorlevel%"
if not "%status%"=="0" pause
popd
exit /b %status%
