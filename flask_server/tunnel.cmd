@echo off
rem ============================================================
rem  chat-bridge tunnel - one file, double-click toggles ON/OFF
rem  ON  : reverse tunnel A 0.0.0.0:54321 to local 127.0.0.1:5000
rem  OFF : stop tunnel - closes every ssh.exe on this machine
rem  window cb-tunnel-54321 is the tunnel - keep it open
rem ============================================================
cd /d E:\chat-bridge-main\flask_server
rem fixed install folder - edit this line if you move the file
rem child window jumps straight to the runner loop
if defined TUNNEL_CHILD goto runner
rem tunnel window found - stop, otherwise start
tasklist /V | findstr /i cb-tunnel-54321 >nul 2>nul
if not errorlevel 1 goto do_stop
rem ---------------- ON ----------------
if exist tunnel.stop del tunnel.stop >nul 2>nul
netstat -an | findstr :5000 | findstr LISTENING >nul 2>nul
if errorlevel 1 echo [warn] local port 5000 not listening - run start_server.cmd first
start cmd /c set TUNNEL_CHILD=1 ^& tunnel.cmd
echo [ok] tunnel starting in new window
echo [ok] run this file again to stop it
ping -n 4 127.0.0.1 >nul
exit /b 0
rem ---------------- OFF ----------------
:do_stop
echo [info] stopping tunnel ...
echo stop > tunnel.stop
taskkill /F /IM ssh.exe >nul 2>nul
echo [ok] ssh killed - tunnel window closes itself
echo [ok] run this file again to start it
pause
exit /b 0
rem ---------------- runner - child window ----------------
:runner
title cb-tunnel-54321
taskkill /F /IM ssh.exe >nul 2>nul
echo [tunnel] connecting - keep this window open
start /b ssh -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N -R 0.0.0.0:54321:127.0.0.1:5000 ubuntu@10.2.66.248
ping -n 3 127.0.0.1 >nul
:loop
if exist tunnel.stop goto runner_exit
tasklist | findstr /i ssh.exe >nul 2>nul
if errorlevel 1 goto reconnect
timeout /t 2 >nul
goto loop
:reconnect
if exist tunnel.stop goto runner_exit
echo [tunnel] dropped - retry in 15s ...
timeout /t 15 >nul
if exist tunnel.stop goto runner_exit
echo [tunnel] reconnecting ...
start /b ssh -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N -R 0.0.0.0:54321:127.0.0.1:5000 ubuntu@10.2.66.248
ping -n 3 127.0.0.1 >nul
goto loop
:runner_exit
taskkill /F /IM ssh.exe >nul 2>nul
del tunnel.stop >nul 2>nul
echo [tunnel] stopped - window closing
timeout /t 2 >nul
exit
