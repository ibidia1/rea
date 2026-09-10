"""La porte de secours des comptes (SPEC §2.5).

Les comptes se gèrent dans *Administration → Comptes*, écran réservé au droit
`comptes` — que seul un administrateur possède. Trois situations enferment
donc dehors : une base qui porte des comptes mais aucun administrateur, le
seul administrateur désactivé, son code perdu. Le service est tombé sur la
première en testant l'application (10 septembre) ; sans outil, le seul
recours était d'ouvrir la base SQLite à la main.

Ce que ces tests tiennent, c'est le contrat de l'outil : il retrouve un compte
**désactivé** (celui qu'on vient réactiver ne l'est plus par définition), il
lit le bon champ d'état, et il passe par les services — donc le journal
d'audit enregistre.
"""

import importlib
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _lancer(dossier, *arguments) -> str:
    """L'outil pour de vrai, dans son propre processus — c'est ainsi qu'il
    sera lancé sur le PC serveur."""
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "outils" / "administrateur.py"), *arguments],
        capture_output=True, text=True, cwd=str(RACINE),
        env={"REA_DIR": str(dossier), "PATH": "/usr/bin:/bin"},
    )
    assert resultat.returncode == 0, resultat.stderr
    return resultat.stdout


def _base_sans_admin(base):
    utilisateurs = _services("utilisateurs")
    utilisateurs.creer(base, "Dr Ben Salah", "senior")
    utilisateurs.creer(base, "Inf. Amel", "infirmier")


def test_une_base_sans_administrateur_le_dit(base, tmp_path):
    _base_sans_admin(base)
    sortie = _lancer(tmp_path, "--lister")
    assert "Aucun administrateur actif" in sortie
    assert "Dr Ben Salah" in sortie and "senior" in sortie


def test_promouvoir_rend_la_main(base, tmp_path):
    """Le geste qui débloque : un senior devient administrateur, et l'écran
    des comptes s'ouvre pour lui."""
    utilisateurs = _services("utilisateurs")
    _base_sans_admin(base)
    _lancer(tmp_path, "--promouvoir", "Dr Ben Salah")
    compte = utilisateurs.par_nom(base, "Dr Ben Salah")
    assert compte["role"] == "admin"
    assert utilisateurs.peut(base, compte["id"], "comptes")


def test_le_nom_se_retrouve_sans_la_casse(base, tmp_path):
    """Personne ne retape « Dr Ben Salah » avec les bonnes majuscules à 3 h
    du matin."""
    utilisateurs = _services("utilisateurs")
    _base_sans_admin(base)
    _lancer(tmp_path, "--promouvoir", "dr ben salah")
    assert utilisateurs.par_nom(base, "Dr Ben Salah")["role"] == "admin"


def test_un_compte_desactive_reste_trouvable(base, tmp_path):
    """C'est tout l'objet de `--reactiver` : le compte visé n'est pas actif.

    `utilisateurs.par_nom` ne regarde que les comptes actifs — juste pour
    l'écran d'ouverture, faux ici. L'outil cherche parmi tous.
    """
    utilisateurs = _services("utilisateurs")
    _base_sans_admin(base)
    cible = utilisateurs.par_nom(base, "Inf. Amel")
    utilisateurs.desactiver(base, cible["id"])
    assert utilisateurs.par_nom(base, "Inf. Amel") is None

    sortie = _lancer(tmp_path, "--lister")
    assert "désactivé" in sortie
    _lancer(tmp_path, "--reactiver", "Inf. Amel")
    assert utilisateurs.par_nom(base, "Inf. Amel") is not None


def test_un_nom_inconnu_ne_casse_pas_la_base(base, tmp_path):
    _base_sans_admin(base)
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "outils" / "administrateur.py"),
         "--promouvoir", "Dr Personne"],
        capture_output=True, text=True, cwd=str(RACINE),
        env={"REA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert resultat.returncode != 0
    assert "Aucun compte" in resultat.stderr + resultat.stdout


def test_le_geste_est_journalise(base, tmp_path):
    """Reprendre la main sur les comptes est une modification comme une
    autre : elle se retrouve dans le journal d'audit."""
    _base_sans_admin(base)
    avant = base.une_ligne(
        "SELECT COUNT(*) AS n FROM journal WHERE table_cible = 'utilisateur'")["n"]
    _lancer(tmp_path, "--promouvoir", "Dr Ben Salah")
    apres = base.une_ligne(
        "SELECT COUNT(*) AS n FROM journal WHERE table_cible = 'utilisateur'")["n"]
    assert apres > avant


def test_le_code_ne_se_passe_jamais_en_argument():
    """Un code sur la ligne de commande reste dans l'historique du terminal
    et dans la liste des processus — lisible par quelqu'un qui n'aurait
    jamais dû le voir. Il se tape, sans s'afficher."""
    source = (RACINE / "outils" / "administrateur.py").read_text(encoding="utf-8")
    assert "getpass" in source
    assert '"--code", metavar="NOM"' in source
