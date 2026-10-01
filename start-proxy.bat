@echo off
rem WorkBuddy local proxy - START
setlocal
cd /d "%~dp0"

set "NODE_EXE=node"
where node >nul 2>nul || set "NODE_EXE="
if not defined NODE_EXE (
  echo [x] Node.js not found in PATH.
  echo     Use the full path of node.exe on line 6 instead.
  pause
  exit /b 1
)

netstat -ano | findstr ":8787" | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
  echo [i] Port 8787 is already listening. Proxy seems to be running.
  echo     To restart, run stop-proxy.bat first.
  pause
  exit /b 0
)

echo [*] Starting WorkBuddy local proxy ...
start "WorkBuddy Proxy" /min "%NODE_EXE%" "%~dp0workbuddy-proxy.js"
timeout /t 3 /nobreak >nul 2>&1

netstat -ano | findstr ":8787" | findstr LISTENING >nul 2>&1
if errorlevel 1 (
  echo [x] Failed: port 8787 is not listening.
  echo     Check %~dp0workbuddy-proxy.log
  pause
  exit /b 1
)

echo [ok] Proxy started: http://127.0.0.1:8787
timeout /t 3 /nobreak >nul 2>&1
exit /b 0
