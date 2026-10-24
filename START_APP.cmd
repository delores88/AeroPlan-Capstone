@echo off
setlocal
set "AEROPLAN_ROOT=%~dp0"
cd /d "%AEROPLAN_ROOT%"
powershell.exe -NoLogo -NoProfile -Command "& ([ScriptBlock]::Create([IO.File]::ReadAllText((Join-Path $env:AEROPLAN_ROOT 'INSTALL_AND_START_WINDOWS.txt'))))"
if errorlevel 1 (
  echo.
  echo AeroPlan did not start. Review the error above and README.md.
  pause
)
endlocal
