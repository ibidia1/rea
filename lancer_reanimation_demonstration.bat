@echo off
setlocal EnableExtensions
title Reanimation polyvalente - DEMONSTRATION
cd /d "%~dp0"

rem ===========================================================================
rem  La demonstration : le meme logiciel, sur une base A PART.
rem
rem  REA_DIR pointe vers C:\ReaService\demonstration (a cote de "programme"),
rem  jamais vers les donnees du service : des patients fictifs dans la vraie
rem  base fausseraient les statistiques de la Recherche. Le port 8502 permet
rem  de l'ouvrir pendant que la vraie base tourne sur 8501.
rem
rem  La base est refaite chaque jour par outils\base_demonstration.py : deux
rem  patients hospitalises, un historique de sejours clos, un compte par role.
rem ===========================================================================

if not exist ".venv\Scripts\python.exe" (
    echo Logiciel non installe. Executer installer.bat d'abord.
    pause
    exit /b 1
)

set "VENV=%~dp0.venv\Scripts\python.exe"
set "PYTHONPATH=%~dp0"
set "REA_DIR=%~dp0..\demonstration"
set "REA_DEMONSTRATION=1"
set "REA_HOTE=127.0.0.1"
set "REA_PORT=8502"

echo ================================================
echo   Reanimation polyvalente - DEMONSTRATION
echo   Patients fictifs, base separee de celle du service
echo   http://127.0.0.1:8502
echo   Comptes "Demo - ...", code : demo2026
echo ================================================
echo.

"%VENV%" outils\base_demonstration.py
if errorlevel 1 (
    echo.
    echo La base de demonstration n'a pas pu etre preparee.
    pause
    exit /b 1
)

start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 120; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 8502); $c.Close(); Start-Process 'http://127.0.0.1:8502'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%VENV%" -m streamlit run rea_app.py --server.address 127.0.0.1 --server.port 8502

endlocal
