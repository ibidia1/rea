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

rem L'adresse et le port viennent de rea\config.py, seul endroit ou ils sont
rem ecrits (SPEC 2.4, invariant 5). 127.0.0.1 : le logiciel n'est joignable que
rem depuis ce poste. Le jour du multi-postes, une seule ligne change, la-bas.
for /f "delims=" %%h in ('python -c "import rea.config as c; print(c.HOTE)"') do set "REA_HOTE=%%h"
for /f "delims=" %%p in ('python -c "import rea.config as c; print(c.PORT)"') do set "REA_PORT=%%p"

if not defined REA_HOTE (
    echo Impossible de lire la configuration ^(rea\config.py^).
    echo Installation incomplete : relancer "installer.bat".
    pause
    exit /b 1
)

echo ================================================
echo   Demarrage du logiciel de reanimation...
echo   Le navigateur va s'ouvrir automatiquement.
echo.
echo   Accessible depuis ce poste uniquement ^(%REA_HOTE%^).
echo.
echo   NE PAS FERMER CETTE FENETRE pendant l'utilisation :
echo   la fermer arrete le logiciel pour tout le monde.
echo ================================================
echo.

streamlit run rea_app.py --server.address %REA_HOTE% --server.port %REA_PORT%

echo.
echo Le logiciel est arrete.
pause
