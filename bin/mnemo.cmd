@echo off
rem mnemo: start and manage Mnemo on Windows.  Run `mnemo help` for commands.
setlocal
set "SRC=%~dp0.."
set "PY=%SRC%\.venv\Scripts\python.exe"
set "CMD=%~1"
if "%CMD%"=="" set "CMD=start"

if /i "%CMD%"=="start"     ( cd /d "%SRC%\app" & call npx --no-install electron . & goto :eof )
if /i "%CMD%"=="open"      ( cd /d "%SRC%\app" & call npx --no-install electron . & goto :eof )
if /i "%CMD%"=="headless"  ( cd /d "%SRC%" & echo Mnemo is learning without the window ^(Ctrl+C to stop^)... & "%PY%" -m mnemo.server --port 8765 & goto :eof )
if /i "%CMD%"=="config"    ( cd /d "%SRC%" & "%PY%" -m mnemo.cli config %2 %3 %4 %5 %6 %7 %8 %9 & goto :eof )
if /i "%CMD%"=="update"    ( cd /d "%SRC%" & git pull --ff-only & uv pip install --python "%PY%" -r requirements.txt & cd app & call npm install --no-fund --no-audit & echo Mnemo is up to date. & goto :eof )
if /i "%CMD%"=="doctor"    ( cd /d "%SRC%" & "%PY%" -m mnemo.cli doctor & goto :eof )
if /i "%CMD%"=="bench"     ( cd /d "%SRC%" & "%PY%" scripts\benchmark.py %2 %3 %4 %5 & goto :eof )
if /i "%CMD%"=="data"      ( start "" "%USERPROFILE%\.mnemo" & goto :eof )
if /i "%CMD%"=="help" goto :help
if /i "%CMD%"=="-h"   goto :help
echo Unknown command: %CMD% (try: mnemo help)
goto :eof
:help
echo mnemo                 open Mnemo
echo mnemo headless        learn in the background without a window
echo mnemo config          show settings   /   mnemo config start_params=125000000 context_length=32768
echo mnemo update          get the latest version
echo mnemo doctor          check Python, GPU, Node and disk
echo mnemo bench           speed test
echo mnemo data            open the data folder
