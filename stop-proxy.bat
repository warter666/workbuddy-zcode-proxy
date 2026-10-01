@echo off
rem WorkBuddy local proxy - STOP
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PIDFILE=%~dp0workbuddy-proxy.pid"
set "PID="

if exist "%PIDFILE%" set /p PID=<"%PIDFILE%"

if defined PID (
  taskkill /PID !PID! /T /F >nul 2>&1
  if not errorlevel 1 (
    echo [ok] Stopped proxy process PID !PID!
  ) else (
    echo [i] PID !PID! is not running. Searching by port ...
  )
  del /q "%PIDFILE%" >nul 2>&1
) else (
  echo [i] No PID file found. Searching by port ...
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8787" ^| findstr LISTENING') do (
  taskkill /PID %%a /T /F >nul 2>&1
  if not errorlevel 1 echo [ok] Stopped proxy process PID %%a
)

netstat -ano | findstr ":8787" | findstr LISTENING >nul 2>&1
if errorlevel 1 (
  echo [ok] Port 8787 released. Proxy stopped.
) else (
  echo [x] Port 8787 is still in use. Please check manually.
)
pause
exit /b 0
