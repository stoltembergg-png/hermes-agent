@echo off
REM Compatibility wrapper for the universal Python installer.
setlocal
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  python "%~dp0install-vector.py" %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  py "%~dp0install-vector.py" %*
  exit /b %ERRORLEVEL%
)
echo Python 3 is required. Install Python, then run this installer again.
exit /b 1
