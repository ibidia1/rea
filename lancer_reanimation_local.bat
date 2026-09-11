@echo off
setlocal EnableExtensions
title Reanimation polyvalente - Local
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Logiciel non installe. Executer installer.bat d'abord.
    pause
    exit /b 1
)

set "VENV=%~dp0.venv\Scripts\python.exe"
set "PYTHONPATH=%~dp0"
set "REA_HOTE=127.0.0.1"
set "REA_PORT=8501"

echo ================================================
echo   Reanimation polyvalente - MODE LOCAL
echo   http://127.0.0.1:8501
echo ================================================
echo.

start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 120; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 8501); $c.Close(); Start-Process 'http://127.0.0.1:8501'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%VENV%" -m streamlit run rea_app.py --server.address 127.0.0.1 --server.port 8501

endlocal
