"""Les fichiers que le service double-clique sous Windows.

Ils ne s'executent pas ici — ce dépôt est développé sous Linux, et un `.bat`
ne se lance pas sous pytest. Ces tests vérifient donc ce qui *est*
vérifiable sans Windows, et c'est précisément ce qui casse en silence : un
accent qui devient un carré dans la console, une étiquette `goto` qui
n'existe pas, un fichier appelé qui n'est plus là, une fin de ligne Unix.

Le reste — que Python s'installe vraiment, que l'icône apparaisse vraiment —
ne se vérifie que sur un poste Windows. Ces tests ne le prétendent pas.
"""

import re
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
BATCHS = sorted(RACINE.glob("*.bat"))


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def test_il_y_a_bien_les_deux_fichiers():
    noms = {chemin.name for chemin in BATCHS}
    assert noms == {"installer.bat", "lancer_reanimation.bat"}


@pytest.mark.parametrize("chemin", BATCHS, ids=lambda c: c.name)
def test_aucun_accent(chemin):
    """La console Windows n'est pas en UTF-8 : un « é » y devient un signe
    illisible, et c'est toujours au milieu d'un message d'erreur."""
    texte = lire(chemin)
    fautifs = sorted({c for c in texte if ord(c) > 126})
    assert not fautifs, f"{chemin.name} contient {fautifs}"


@pytest.mark.parametrize("chemin", BATCHS, ids=lambda c: c.name)
def test_fins_de_ligne_windows(chemin):
    """Un .bat en fins de ligne Unix marche presque toujours — et rate
    justement sur les etiquettes, donc sur les chemins d'erreur."""
    brut = chemin.read_bytes()
    assert b"\r\n" in brut, f"{chemin.name} n'a pas de fins de ligne Windows"
    assert not re.search(rb"(?<!\r)\n", brut), f"{chemin.name} melange les fins de ligne"


@pytest.mark.parametrize("chemin", BATCHS, ids=lambda c: c.name)
def test_chaque_etiquette_appelee_existe(chemin):
    """`goto :fin_erreur` vers une etiquette absente ne se voit qu'au moment
    de l'erreur : le fichier s'arrete sans rien dire, en pleine installation."""
    texte = lire(chemin)
    definies = set(re.findall(r"^\s*:(\w+)", texte, re.MULTILINE))
    appelees = set(re.findall(r"(?:goto|call)\s+:(\w+)", texte, re.IGNORECASE))
    assert appelees <= definies, f"{chemin.name} appelle {appelees - definies}"


@pytest.mark.parametrize("chemin", BATCHS, ids=lambda c: c.name)
def test_chaque_etiquette_definie_sert(chemin):
    """Une etiquette morte est du code que personne ne relit plus."""
    texte = lire(chemin)
    definies = set(re.findall(r"^\s*:(\w+)", texte, re.MULTILINE))
    appelees = set(re.findall(r"(?:goto|call)\s+:(\w+)", texte, re.IGNORECASE))
    assert definies <= appelees, f"{chemin.name} definit sans jamais l'appeler : {definies - appelees}"


def test_l_installateur_appelle_des_fichiers_qui_existent():
    texte = lire(RACINE / "installer.bat")
    for attendu in ("outils\\raccourcis.ps1", "requirements.txt",
                    "rea_app.py", "lancer_reanimation.bat"):
        assert attendu in texte, f"installer.bat ne parle pas de {attendu}"
        assert (RACINE / attendu.replace("\\", "/")).exists(), f"{attendu} n'existe pas"


def test_l_installateur_verifie_que_python_repond():
    """Windows livre un faux python.exe qui n'ouvre que le Microsoft Store.
    Il repond a `where`, pas a `--version` : sans essai reel, l'installation
    croit avoir trouve Python et echoue trois etapes plus loin."""
    texte = lire(RACINE / "installer.bat")
    assert "version_info >= (3, 11)" in texte
    assert ":verifier_python" in texte


def ligne_robocopy() -> str:
    """La vraie commande robocopy, pas le commentaire qui l'explique."""
    for ligne in lire(RACINE / "installer.bat").splitlines():
        if ligne.strip().lower().startswith("robocopy "):
            return ligne
    pytest.fail("installer.bat n'appelle plus robocopy")


def test_l_installateur_lit_le_compte_de_robocopy():
    """robocopy rend 0 a 7 quand tout va bien, et 8 ou plus quand ca casse.
    C'est le seul programme de Windows a compter ainsi : un `if errorlevel 1`
    ferait passer chaque copie reussie pour un echec."""
    texte = lire(RACINE / "installer.bat")
    apres = texte.split(ligne_robocopy(), 1)[1]
    # Le premier test d'erreur qui suit l'appel est celui qui juge la copie.
    premier = re.search(r"if errorlevel (\d+)", apres)
    assert premier is not None, "la copie n'est pas verifiee"
    assert premier.group(1) == "8"


def test_la_copie_epargne_le_dossier_des_patients():
    """Une reinstallation ne doit jamais ecraser `donnees`."""
    exclusions = ligne_robocopy().split("/XD", 1)[1]
    for dossier in ('"donnees"', '"sauvegardes"', '".venv"', '".git"'):
        assert dossier in exclusions, f"{dossier} devrait etre exclu de la copie"


def test_l_installateur_ne_touche_ni_au_reseau_ni_au_pare_feu():
    """Ouvrir le logiciel au Wi-Fi rend un code d'acces obligatoire sur tous
    les comptes : ce n'est pas un effet de bord d'une installation, c'est une
    decision, et elle se prend ailleurs (INSTALLATION.md section 2)."""
    texte = lire(RACINE / "installer.bat").lower()
    for interdit in ("netsh", "advfirewall", "0.0.0.0", "rea_hote="):
        assert interdit not in texte, f"installer.bat touche a {interdit}"


def test_le_lanceur_ouvre_le_navigateur_lui_meme():
    """`headless = true` dans .streamlit/config.toml evite que Streamlit
    reclame une adresse e-mail au premier lancement — mais il n'ouvre alors
    plus le navigateur, et l'icone du Bureau n'ouvrait qu'une fenetre noire."""
    config = lire(RACINE / ".streamlit" / "config.toml")
    assert "headless = true" in config
    lanceur = lire(RACINE / "lancer_reanimation.bat")
    assert "Start-Process 'http://" in lanceur
    assert "TcpClient" in lanceur, "l'attente doit guetter le port, pas compter les secondes"


def test_le_lanceur_utilise_le_python_de_l_environnement():
    """Pas le `python` du PATH : sur un poste ou un autre Python est installe,
    l'application demarrerait sans ses composants."""
    lanceur = lire(RACINE / "lancer_reanimation.bat")
    assert ".venv\\Scripts\\python.exe" in lanceur


def test_le_lanceur_prend_l_adresse_dans_config_py():
    """SPEC 2.4, invariant 5 : l'adresse est ecrite a un seul endroit."""
    lanceur = lire(RACINE / "lancer_reanimation.bat")
    assert "rea.config as c; print(c.HOTE)" in lanceur
    assert "rea.config as c; print(c.PORT)" in lanceur


def test_le_script_de_raccourci_est_en_ascii():
    """Windows PowerShell 5.1 lit un .ps1 sans BOM avec la page de codes
    ANSI, pas en UTF-8 : les accents y arriveraient abimes."""
    script = lire(RACINE / "outils" / "raccourcis.ps1")
    fautifs = sorted({c for c in script if ord(c) > 126})
    assert not fautifs, f"raccourcis.ps1 contient {fautifs}"


def test_le_script_de_raccourci_demande_le_bureau_a_windows():
    """Avec OneDrive — et le poste du service en a un — le Bureau n'est pas
    dans %USERPROFILE%\\Desktop, et une icone posee la n'apparait nulle part."""
    script = lire(RACINE / "outils" / "raccourcis.ps1")
    assert "[Environment]::GetFolderPath" in script
    assert "USERPROFILE\\Desktop" not in script


@pytest.mark.parametrize("fichier", [
    "installer.bat", "lancer_reanimation.bat", "outils/raccourcis.ps1",
])
def test_git_livrera_ces_fichiers_en_fins_de_ligne_windows(fichier):
    """On interroge git lui-meme, pas le texte de .gitattributes.

    La regle y etait ecrite, et pourtant sans effet : quand plusieurs lignes
    correspondent, git retient **la derniere**, et le fourre-tout
    `* text=auto eol=lf` place en bas annulait les deux exceptions. Lire le
    fichier n'aurait rien montre ; seul `git check-attr` le dit, et un clone
    frais livrait des .ps1 en fins de ligne Unix.
    """
    sortie = subprocess.run(
        ["git", "check-attr", "eol", "--", fichier],
        cwd=RACINE, capture_output=True, text=True, check=True,
    ).stdout
    assert sortie.strip().endswith("eol: crlf"), sortie.strip()


def test_le_reste_du_depot_reste_en_fins_de_ligne_unix():
    sortie = subprocess.run(
        ["git", "check-attr", "eol", "--", "rea_app.py"],
        cwd=RACINE, capture_output=True, text=True, check=True,
    ).stdout
    assert sortie.strip().endswith("eol: lf"), sortie.strip()


def test_le_lanceur_ne_refuse_pas_de_demarrer_si_la_sonde_echoue():
    """L'app lit elle-meme sa config ; ces valeurs ne servent qu'a ouvrir le
    navigateur. Une sonde qui echoue (dossier OneDrive, chemin avec espace) ne
    doit pas afficher « installation incomplete » alors que le logiciel demarre
    (signale par le service, 11 septembre)."""
    lanceur = lire(RACINE / "lancer_reanimation.bat")
    assert 'set "REA_HOTE=127.0.0.1"' in lanceur
    assert 'set "REA_PORT=8501"' in lanceur
    # L'ancien abandon a disparu : plus de "exit /b 1" declenche par la lecture
    # de config. Le seul refus qui reste est l'absence du venv (pas installe).
    apres_venv = lanceur.split('.venv\\Scripts\\python.exe" (', 1)[1]
    corps = apres_venv.split(")", 1)[1]  # apres le bloc "venv manquant"
    assert "exit /b 1" not in corps


def test_la_sonde_de_config_insere_le_dossier_dans_le_chemin():
    """Sans cela, « import rea » echoue quand l'icone lance le fichier depuis
    un repertoire courant qui n'est pas celui du programme."""
    lanceur = lire(RACINE / "lancer_reanimation.bat")
    assert "sys.path.insert(0, r'%~dp0')" in lanceur
    assert 'set "PYTHONPATH=%~dp0"' in lanceur
