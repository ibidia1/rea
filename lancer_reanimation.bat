@echo off
setlocal EnableExtensions
title Reanimation polyvalente - Kairouan
cd /d "%~dp0"

rem ===========================================================================
rem  Ouvre le logiciel. C'est ce fichier que l'icone du Bureau appelle.
rem
rem  Aucun accent ici : la console Windows ne les affiche pas comme le
rem  Bloc-notes, et un message d'erreur illisible ne sert a personne.
rem ===========================================================================

if not exist ".venv\Scripts\python.exe" (
    echo ================================================
    echo   Le logiciel n'est pas encore installe sur ce poste.
    echo   Executer d'abord "installer.bat", une seule fois.
    echo ================================================
    echo.
    pause
    exit /b 1
)

set "VENV=%~dp0.venv\Scripts\python.exe"

rem L'adresse et le port viennent de rea\config.py, seul endroit ou ils sont
rem ecrits (SPEC 2.4, invariant 5). 127.0.0.1 : le logiciel n'est joignable que
rem depuis ce poste. Le jour du multi-postes, une seule ligne change, la-bas.
set "REA_HOTE="
set "REA_PORT="
for /f "usebackq delims=" %%h in (`"%VENV%" -c "import rea.config as c; print(c.HOTE)" 2^>nul`) do set "REA_HOTE=%%h"
for /f "usebackq delims=" %%p in (`"%VENV%" -c "import rea.config as c; print(c.PORT)" 2^>nul`) do set "REA_PORT=%%p"

if not defined REA_HOTE (
    echo Impossible de lire la configuration ^(rea\config.py^).
    echo Installation incomplete : relancer "installer.bat".
    pause
    exit /b 1
)

echo ================================================
echo   Demarrage du logiciel de reanimation...
echo.
echo   Le navigateur s'ouvre tout seul dans quelques
echo   secondes, sur http://%REA_HOTE%:%REA_PORT%
echo.
echo   Accessible depuis ce poste uniquement.
echo.
echo   NE PAS FERMER CETTE FENETRE pendant l'utilisation :
echo   la fermer arrete le logiciel.
echo ================================================
echo.

rem Le navigateur s'ouvre depuis ici, et non par Streamlit : la configuration
rem du depot fixe "headless = true" (.streamlit/config.toml), sans quoi
rem Streamlit reclame une adresse e-mail a la premiere ouverture et reste
rem bloque la. Headless, il ne demande rien - mais il n'ouvre plus rien non
rem plus, et l'icone du Bureau n'ouvrait donc qu'une fenetre noire.
rem
rem L'attente guette le port plutot que de compter les secondes : sur un
rem poste lent, un delai fixe ouvre le navigateur sur une page d'erreur.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 120; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('%REA_HOTE%', %REA_PORT%); $c.Close(); Start-Process 'http://%REA_HOTE%:%REA_PORT%'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%VENV%" -m streamlit run rea_app.py --server.address %REA_HOTE% --server.port %REA_PORT%

echo.
echo Le logiciel est arrete.
pause
endlocal
