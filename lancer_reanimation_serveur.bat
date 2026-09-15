@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Reanimation - Serveur - Kairouan
cd /d "%~dp0"

rem ===========================================================================
rem  Ouvre le logiciel EN MODE SERVEUR : ce poste devient le serveur de la
rem  reanimation, joignable depuis les autres PC, tablettes et telephones du
rem  reseau local.
rem
rem  AUCUNE adresse IP n'est ecrite dans ce fichier. Au lancement, ce launcher
rem  DETECTE l'adresse reseau de ce poste (outils\adresse_reseau.ps1), la
rem  donne a l'application par REA_HOTE, et Streamlit ecoute dessus. Comme
rem  l'adresse n'est plus la boucle locale, le code d'acces devient
rem  automatiquement obligatoire sur tous les comptes (regle de rea\config.py,
rem  AUTH_EXIGEE) : c'est voulu, pas un reglage a part.
rem
rem  La base de donnees reste sur CE poste. Les autres appareils n'installent
rem  rien : ils ouvrent seulement l'adresse affichee ci-dessous dans leur
rem  navigateur.
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

rem Le dossier du programme sur le chemin d'import : sans lui, "import rea"
rem echoue quand ce fichier est lance depuis un dossier synchronise (OneDrive)
rem ou dont le nom porte un espace.
set "PYTHONPATH=%~dp0"

rem Le port vient de config.py comme d'habitude ; s'il ne repond pas, 8501.
set "REA_PORT="
for /f "usebackq delims=" %%p in (`"%VENV%" -c "import sys; sys.path.insert(0, r'%~dp0'); import rea.config as c; print(c.PORT)" 2^>nul`) do set "REA_PORT=%%p"
if not defined REA_PORT set "REA_PORT=8501"

rem Detection de l'adresse reseau de ce poste. Le script n'ecrit qu'une ligne :
rem l'adresse, ou rien s'il n'en trouve pas.
set "ADRESSE="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\adresse_reseau.ps1" 2^>nul`) do set "ADRESSE=%%i"

if defined ADRESSE (
    set "REA_HOTE=!ADRESSE!"
    set "URL_NAVIGATEUR=http://!ADRESSE!:%REA_PORT%"
    set "ADRESSE_AFFICHEE=!ADRESSE!:%REA_PORT%"
    rem Streamlit n'ecoute que sur cette adresse : on sonde son ouverture
    rem dessus, pas sur la boucle locale ou rien ne repondrait.
    set "HOTE_SONDE=!ADRESSE!"
) else (
    rem Aucune adresse detectee : on ecoute quand meme sur toutes les cartes
    rem (0.0.0.0) pour que le reseau fonctionne, et on ouvre le navigateur en
    rem local. Il faudra lire l'IP de ce poste avec "ipconfig".
    set "REA_HOTE=0.0.0.0"
    set "URL_NAVIGATEUR=http://127.0.0.1:%REA_PORT%"
    set "ADRESSE_AFFICHEE=<adresse de ce poste> : %REA_PORT%   (voir : ipconfig)"
    rem 0.0.0.0 englobe la boucle locale : on peut sonder 127.0.0.1.
    set "HOTE_SONDE=127.0.0.1"
)

echo ================================================
echo   Demarrage du logiciel de reanimation (SERVEUR)...
echo.
echo   Ce poste est maintenant le SERVEUR de la reanimation.
echo.
echo   Depuis les autres PC / tablettes / telephones du
echo   reseau, ouvrir dans le navigateur :
echo.
echo        http://!ADRESSE_AFFICHEE!
echo.
echo   Un code d'acces est desormais exige sur tous les
echo   comptes (le logiciel est joignable sur le reseau).
echo.
echo   NE PAS FERMER CETTE FENETRE pendant l'utilisation :
echo   la fermer arrete le serveur pour tout le monde.
echo ================================================
echo.

rem Le navigateur de CE poste s'ouvre depuis ici (headless = true dans
rem .streamlit\config.toml). L'attente guette le port plutot que de compter
rem les secondes : sur un poste lent, un delai fixe ouvre sur une page d'erreur.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 120; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('!HOTE_SONDE!', %REA_PORT%); $c.Close(); Start-Process '!URL_NAVIGATEUR!'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%VENV%" -m streamlit run rea_app.py --server.address !REA_HOTE! --server.port %REA_PORT%

echo.
echo Le serveur est arrete.
pause
endlocal
