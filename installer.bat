@echo off
setlocal EnableExtensions
title Installation - Logiciel de reanimation
color 07

rem ===========================================================================
rem  Installation du logiciel de reanimation - Kairouan
rem
rem  Ce fichier se double-clique, une seule fois, et fait quatre choses :
rem
rem    1. il trouve Python, et l'installe s'il manque ;
rem    2. il pose le programme dans C:\ReaService\programme ;
rem    3. il installe les composants (cette etape demande Internet) ;
rem    4. il met une icone "Reanimation" sur le Bureau.
rem
rem  A la fin, le logiciel s'ouvre. Le Bureau suffit ensuite.
rem
rem  Le logiciel n'est joignable que depuis CE poste. L'ouvrir au Wi-Fi du
rem  service est un autre geste, avec d'autres consequences (un code d'acces
rem  devient obligatoire sur tous les comptes) : il est decrit dans
rem  INSTALLATION.md section 2, et ne se fait pas ici.
rem
rem  Aucun accent dans ce fichier : la console Windows n'affiche pas les
rem  memes caracteres que le Bloc-notes, et un "e accent" y devient un signe
rem  illisible au milieu d'un message d'erreur.
rem ===========================================================================

set "SOURCE=%~dp0"
if "%SOURCE:~-1%"=="\" set "SOURCE=%SOURCE:~0,-1%"
set "RACINE=C:\ReaService"
set "VERSION_PYTHON=3.12.7"
set "ETAPE=0"

echo.
echo  ==========================================================
echo    Installation du logiciel de reanimation
echo    Service d'Anesthesie-Reanimation - Kairouan
echo  ==========================================================
echo.
echo  Le programme sera installe dans : %RACINE%\programme
echo  Les dossiers des patients dans  : %RACINE%\donnees
echo.
echo  Pour garder %RACINE%, appuyer simplement sur Entree.
echo  Pour un autre emplacement, taper le chemin complet.
echo.
set "CHOIX="
set /p "CHOIX=Emplacement [%RACINE%] : "
if not "%CHOIX%"=="" set "RACINE=%CHOIX%"
if "%RACINE:~-1%"=="\" set "RACINE=%RACINE:~0,-1%"
set "PROGRAMME=%RACINE%\programme"
echo.

rem ---------------------------------------------------------------------------
rem  1. Python
rem ---------------------------------------------------------------------------
set "ETAPE=1"
echo  [1/4] Recherche de Python...
call :trouver_python
if not defined PY (
    echo.
    echo        Python n'est pas installe sur ce poste. Je m'en occupe.
    echo        Cette etape demande Internet et prend quelques minutes.
    echo.
    call :installer_python
    call :trouver_python
)
if not defined PY (
    echo.
    echo  [ECHEC] Python n'a pas pu etre installe automatiquement.
    echo.
    echo  A faire a la main, une seule fois :
    echo    1. ouvrir https://www.python.org/downloads/
    echo    2. telecharger Python 3.11 ou plus recent
    echo    3. PENDANT L'INSTALLATION, cocher "Add python.exe to PATH"
    echo    4. relancer ce fichier
    echo.
    goto :fin_erreur
)
echo        Python trouve : "%PY%"
"%PY%" --version
echo.

rem ---------------------------------------------------------------------------
rem  2. Le programme au bon endroit
rem ---------------------------------------------------------------------------
set "ETAPE=2"
echo  [2/4] Installation du programme...
if not exist "%PROGRAMME%" mkdir "%PROGRAMME%" 2>nul
if not exist "%PROGRAMME%" (
    echo.
    echo  [ECHEC] Impossible de creer %PROGRAMME%
    echo  Choisir un autre emplacement, ou relancer ce fichier en tant
    echo  qu'administrateur ^(clic droit / Executer en tant qu'administrateur^).
    echo.
    goto :fin_erreur
)
if /i "%SOURCE%"=="%PROGRAMME%" (
    echo        Deja au bon endroit, rien a copier.
) else (
    call :copier_programme
    if errorlevel 1 goto :fin_erreur
)
if not exist "%PROGRAMME%\rea_app.py" (
    echo.
    echo  [ECHEC] rea_app.py est introuvable dans %PROGRAMME%
    echo  Ce fichier a-t-il bien ete lance depuis le dossier du logiciel ?
    echo.
    goto :fin_erreur
)
echo.

rem ---------------------------------------------------------------------------
rem  3. Les composants
rem ---------------------------------------------------------------------------
set "ETAPE=3"
echo  [3/4] Installation des composants ^(demande Internet^)...
cd /d "%PROGRAMME%"
if not exist ".venv\Scripts\python.exe" "%PY%" -m venv ".venv"
set "VENV=%PROGRAMME%\.venv\Scripts\python.exe"
if not exist "%VENV%" (
    echo.
    echo  [ECHEC] La creation de l'environnement Python a echoue.
    echo.
    goto :fin_erreur
)
"%VENV%" -m pip install --upgrade pip >nul 2>&1
"%VENV%" -m pip install -r "%PROGRAMME%\requirements.txt"
if errorlevel 1 (
    echo.
    echo  [ECHEC] L'installation des composants a echoue.
    echo.
    echo  C'est presque toujours la connexion Internet. Verifier qu'une page
    echo  web s'ouvre sur ce poste, puis relancer ce fichier : ce qui est
    echo  deja fait ne sera pas refait.
    echo.
    goto :fin_erreur
)
echo        Composants installes.
echo.

rem ---------------------------------------------------------------------------
rem  4. L'icone du Bureau
rem ---------------------------------------------------------------------------
set "ETAPE=4"
echo  [4/4] Icone sur le Bureau...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROGRAMME%\outils\raccourcis.ps1" -Programme "%PROGRAMME%"
if errorlevel 1 (
    echo        [Avertissement] L'icone n'a pas pu etre creee.
    echo        Le logiciel s'ouvre quand meme par
    echo        %PROGRAMME%\lancer_reanimation.bat
) else (
    echo        Icone "Reanimation" posee sur le Bureau.
)
echo.

rem ---------------------------------------------------------------------------
rem  Fin
rem ---------------------------------------------------------------------------
color 0A
echo  ==========================================================
echo    Installation terminee.
echo  ==========================================================
echo.
echo    Programme : %PROGRAMME%
echo    Donnees   : %RACINE%\donnees
echo.
echo    Au quotidien : l'icone "Reanimation" sur le Bureau.
echo.
echo    A la premiere ouverture, le logiciel propose le compte
echo    administrateur Slah - qui reclamera aussitot un vrai code.
echo.
set "LANCER="
set /p "LANCER=Ouvrir le logiciel maintenant ? (O/n) : "
if /i not "%LANCER%"=="n" start "" "%PROGRAMME%\lancer_reanimation.bat"
endlocal
exit /b 0


rem ===========================================================================
rem  Sous-programmes
rem ===========================================================================

:copier_programme
rem Le programme est copie hors de son dossier d'origine, et c'est le point
rem le plus important de cette etape : une base SQLite posee dans un dossier
rem synchronise - OneDrive, Google Drive - se fait corrompre en silence par
rem la synchronisation, qui recopie le fichier pendant qu'on ecrit dedans.
rem C:\ReaService n'est synchronise par rien.
rem
rem /XD : ce qui ne se copie pas. ".venv" sera refait sur place, ".git" ne
rem sert qu'au developpement, et "donnees" n'est JAMAIS ecrase - c'est le
rem dossier des patients, et une reinstallation ne doit pas y toucher.
robocopy "%SOURCE%" "%PROGRAMME%" /E /NFL /NDL /NJH /NJS /NP /XD ".git" ".venv" "__pycache__" ".pytest_cache" "donnees" "sauvegardes" >nul
rem robocopy dit "0 a 7 = tout va bien" et "8 et plus = echec". C'est le seul
rem programme de Windows a compter ainsi, et l'oublier fait passer une copie
rem reussie pour une erreur.
if errorlevel 8 (
    echo.
    echo  [ECHEC] La copie des fichiers a echoue.
    echo.
    exit /b 1
)
echo        Programme copie dans %PROGRAMME%
exit /b 0

:trouver_python
rem Cherche un Python 3.11 ou plus recent, utilisable, et le laisse dans %PY%.
rem
rem "where python" ne suffit pas : Windows 10 et 11 livrent un faux
rem python.exe qui ne fait qu'ouvrir le Microsoft Store. Il repond a
rem "where", pas a "--version". On ne retient donc un candidat qu'apres
rem l'avoir fait executer une ligne de Python.
set "PY="
for /f "usebackq delims=" %%p in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do (
    call :verifier_python "%%p"
)
if defined PY exit /b 0
for /f "usebackq delims=" %%p in (`where python 2^>nul`) do (
    call :verifier_python "%%p"
)
if defined PY exit /b 0
for %%R in ("%LOCALAPPDATA%\Programs\Python" "%ProgramFiles%" "C:\") do (
    for /d %%d in ("%%~R\Python3*") do (
        call :verifier_python "%%~d\python.exe"
    )
)
exit /b 0

:verifier_python
rem %1 = un chemin candidat. On le retient s'il repond ET s'il est en 3.11+.
if defined PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%~1"
exit /b 0

:installer_python
rem Deux chemins, dans cet ordre. winget est le gestionnaire de paquets de
rem Windows : il connait la version courante, sait la mettre a jour, et n'a
rem pas besoin des droits administrateur en installation "utilisateur". Il
rem manque sur les Windows 10 anciens - d'ou le telechargement direct.
where winget >nul 2>&1
if not errorlevel 1 (
    echo        Installation par winget...
    winget install --id Python.Python.3.12 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 exit /b 0
    echo        winget n'a pas abouti, essai par telechargement direct.
)
echo        Telechargement de Python %VERSION_PYTHON%...
set "INSTALLATEUR=%TEMP%\python-%VERSION_PYTHON%-amd64.exe"
curl -L -o "%INSTALLATEUR%" "https://www.python.org/ftp/python/%VERSION_PYTHON%/python-%VERSION_PYTHON%-amd64.exe"
if errorlevel 1 (
    echo        Le telechargement a echoue. Pas d'Internet sur ce poste ?
    exit /b 1
)
if not exist "%INSTALLATEUR%" exit /b 1
echo        Installation de Python...
rem InstallAllUsers=0 : installation pour cet utilisateur seulement, donc
rem sans demander les droits administrateur. PrependPath=1 : "python"
rem repondra dans les fenetres de commande ouvertes ensuite.
"%INSTALLATEUR%" /passive InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del "%INSTALLATEUR%" 2>nul
exit /b 0

:fin_erreur
color 0C
echo  ==========================================================
echo    Installation interrompue a l'etape %ETAPE%.
echo    Rien n'a ete abime : relancer ce fichier apres avoir
echo    corrige le point signale ci-dessus.
echo  ==========================================================
echo.
pause
endlocal
exit /b 1
