@echo off
setlocal
title Installation - Logiciel de reanimation

echo ================================================
echo   Installation du logiciel de reanimation
echo   Service d'Anesthesie-Reanimation - Kairouan
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe, ou pas accessible.
    echo.
    echo 1. Installer Python 3.11 ou plus recent :
    echo    https://www.python.org/downloads/
    echo 2. Pendant l'installation, cocher la case
    echo    "Add python.exe to PATH".
    echo 3. Relancer ce fichier une fois Python installe.
    echo.
    pause
    exit /b 1
)

echo Python trouve :
python --version
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo Creation de l'environnement du logiciel...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] La creation de l'environnement a echoue.
        pause
        exit /b 1
    )
)

echo Installation des composants necessaires...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation a echoue. Verifier la connexion internet
    echo et relancer ce fichier.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Installation terminee.
echo.
echo   Pour ouvrir le logiciel au quotidien, utiliser
echo   "lancer_reanimation.bat" (voir README.md pour
echo   creer un raccourci sur le bureau).
echo ================================================
echo.
pause
