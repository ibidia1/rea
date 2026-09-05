@echo off
title Reanimation polyvalente - Kairouan
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ================================================
    echo   Le logiciel n'est pas encore installe sur ce poste.
    echo   Executer d'abord "installer.bat", une seule fois.
    echo ================================================
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo ================================================
echo   Demarrage du logiciel de reanimation...
echo   Le navigateur va s'ouvrir automatiquement.
echo.
echo   NE PAS FERMER CETTE FENETRE pendant l'utilisation :
echo   la fermer arrete le logiciel pour tout le monde.
echo ================================================
echo.

streamlit run rea_app.py

echo.
echo Le logiciel est arrete.
pause
