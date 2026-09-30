"""Chaque écran s'ouvre, pour chaque rôle — l'application entière, pas un module.

Pourquoi ce fichier (audit du 27 septembre) : après la réorganisation en
couches, `rea_app.py` importait encore `rea.domaine`, renommé `rea.models`.
L'application plantait **juste après la connexion**, et aucun des 1364 tests ne
l'a vu — ils testaient le métier, jamais le point d'entrée. Sur le poste du
service, l'ancien dossier restait en place et masquait l'erreur ; un poste
installé de neuf ne s'ouvrait plus.

Ici on lance le vrai `rea_app.py` avec le moteur de test de Streamlit, sur le
patient de démonstration chargé à fond, et on vérifie qu'aucun écran ne lève
d'exception. Ce n'est pas une recette — ça ne dit pas qu'un écran est juste —
mais un écran qui plante ne peut plus passer inaperçu.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "rea_app.py"

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

ROLES = ("admin", "senior", "interne", "surveillant", "infirmier")
ONGLETS_FICHE = ("Visite", "Identité", "Prescrit", "Explorations et actes",
                 "Bilans", "Évolution", "Sortie")
VUES_RECHERCHE = ("Tableau descriptif", "Indicateurs de service", "Mois par mois",
                  "Gravité et mortalité", "Croisements", "Délai d'apyrexie",
                  "Antibiotiques", "Qualité des données", "Méthode", "Export")


@pytest.fixture()
def service(base):
    """Une base de service : un compte par rôle et le patient de démonstration."""
    import rea.database as db
    from rea.services import utilisateurs

    sys.path.insert(0, str(RACINE / "outils"))
    import patient_demonstration

    db._BASE = base                      # l'application utilise cette base-ci
    comptes = {
        role: utilisateurs.creer(base, f"Test {role}", role, code="code-test-2026")
        for role in ROLES
    }
    sid = patient_demonstration.charger(base)
    yield comptes, sid
    db._BASE = None


def _ouvrir(comptes: dict, role: str, **etat) -> "AppTest":
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.session_state["utilisateur_id"] = comptes[role]
    at.session_state["utilisateur_nom"] = f"Test {role}"
    at.session_state["utilisateur_role"] = role
    for cle, valeur in etat.items():
        at.session_state[cle] = valeur
    at.run()
    erreurs = [str(e.value) for e in at.exception]
    assert not erreurs, f"{role} / {etat} : {erreurs}"
    return at


@pytest.mark.parametrize("role", ROLES)
def test_l_accueil_de_chaque_role_s_ouvre(service, role):
    comptes, _sid = service
    _ouvrir(comptes, role)


@pytest.mark.parametrize("onglet", ONGLETS_FICHE)
def test_chaque_onglet_de_la_fiche_s_ouvre(service, onglet):
    comptes, sid = service
    _ouvrir(comptes, "admin", accueil_pose=True, ecran="", sejour_id=sid,
            **{f"ecran_{sid}": onglet, f"segments_ecran_{sid}": onglet})


@pytest.mark.parametrize("vue", VUES_RECHERCHE)
def test_chaque_vue_de_la_recherche_s_ouvre(service, vue):
    comptes, _sid = service
    _ouvrir(comptes, "senior", accueil_pose=True, ecran="recherche",
            vue_recherche=vue, segments_recherche=vue)


@pytest.mark.parametrize("ecran,role", [
    ("administration", "admin"), ("supervision", "surveillant"), ("poste", "infirmier"),
])
def test_les_ecrans_de_service_s_ouvrent(service, ecran, role):
    comptes, _sid = service
    _ouvrir(comptes, role, accueil_pose=True, ecran=ecran)


def test_l_ecran_d_admission_s_ouvre(service):
    comptes, _sid = service
    _ouvrir(comptes, "interne", accueil_pose=True, ecran="",
            mode="nouvelle_admission", lit_admission_choisi=7)


def test_chaque_import_du_depot_designe_un_module_qui_existe():
    """Un `import rea.xxx` qui ne mène nulle part — module renommé, déplacé —
    ne se voit qu'à l'exécution de la ligne. On les vérifie tous, d'avance."""
    manquants = []
    fichiers = [APP, *RACINE.joinpath("rea").rglob("*.py"),
                *RACINE.joinpath("outils").glob("*.py")]
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        paquet = ".".join(fichier.relative_to(RACINE).with_suffix("").parts[:-1])
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ImportFrom):
                if noeud.level:
                    base_paquet = paquet.split(".")
                    base_paquet = base_paquet[:len(base_paquet) - noeud.level + 1]
                    module = ".".join(base_paquet + ([noeud.module] if noeud.module else []))
                else:
                    module = noeud.module or ""
                candidats = [module] if noeud.module or not noeud.level else []
                # `from . import x` : x est un sous-module (ou un nom du paquet).
                candidats += [f"{module}.{alias.name}" for alias in noeud.names
                              if importlib.util.find_spec(module) is not None
                              and not hasattr(importlib.import_module(module), alias.name)]
            elif isinstance(noeud, ast.Import):
                candidats = [alias.name for alias in noeud.names]
            else:
                continue
            for nom in candidats:
                if nom.split(".")[0] != "rea":
                    continue
                if importlib.util.find_spec(nom) is None:
                    manquants.append(f"{fichier.relative_to(RACINE)} : {nom}")
    assert not manquants, "Imports vers des modules inexistants :\n" + "\n".join(manquants)


def test_la_sortie_s_enregistre_avec_les_selecteurs_de_date(service, base):
    """La date et l'heure se choisissent : plus de chaîne « AAAA-MM-JJTHH:MM »
    à taper, dont la moindre faute faisait planter l'écran."""
    comptes, sid = service
    at = _ouvrir(comptes, "admin", accueil_pose=True, ecran="", sejour_id=sid,
                 **{f"ecran_{sid}": "Sortie", f"segments_ecran_{sid}": "Sortie"})
    bouton = next(b for b in at.button if b.label == "Clôturer le séjour")
    bouton.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    sortie = base.une_ligne("SELECT date_sortie FROM sejour WHERE id = ?", (sid,))
    assert sortie["date_sortie"] and len(sortie["date_sortie"]) == 16
    assert sortie["date_sortie"][10] == "T"


def test_la_demonstration_tient_dans_ses_blocs(service, base):
    """La démonstration montre une feuille remplie comme le service la
    remplit : trente lignes, chacune dans le bloc de sa voie — aucune n'est
    rangée dans un autre bloc (voie écrite en orange), aucune ne déborde."""
    from rea.printing import feuille
    from rea.services import feuille_dossier

    _comptes, sid = service
    sys.path.insert(0, str(RACINE / "outils"))
    import patient_demonstration

    dossier = feuille_dossier.rassembler(base, sid, patient_demonstration.AUJ)
    html = feuille.generer(dossier)
    assert feuille.COULEUR_VOIE_EMPRUNTEE not in html
    assert "⚠" not in feuille.contexte(dossier)["pied"]


def test_le_rappel_intubation_s_affiche_avec_son_bouton(service):
    """La démonstration pose une trachéotomie sur un patient encore intubé :
    l'écran Explorations et actes affiche le rappel, et le bouton qui clôt
    l'intubation au jour de la canule (motif « relais par trachéotomie »).

    Le clic lui-même n'est pas rejoué ici : le moteur de test de Streamlit ne
    sait pas resérialiser une liste déroulante à `format_func` (le motif de
    retrait) — l'effet du retrait est éprouvé dans tests/test_dispositifs.py."""
    comptes, sid = service
    at = _ouvrir(comptes, "admin", accueil_pose=True, ecran="", sejour_id=sid,
                 **{f"ecran_{sid}": "Explorations et actes",
                    f"segments_ecran_{sid}": "Explorations et actes"})
    assert any("retirer l'intubation" in e.value for e in at.error)
    assert any(b.label.startswith("Retirer l'intubation au") for b in at.button)


# -- la base de démonstration complète ------------------------------------------

@pytest.fixture()
def demonstration(base):
    """La base que charge l'icône « Réanimation - Démonstration »."""
    import rea.database as db

    sys.path.insert(0, str(RACINE / "outils"))
    import base_demonstration

    db._BASE = base
    ids = base_demonstration.construire(base)
    yield ids
    db._BASE = None


def _ouvrir_demo(ids, nom: str, role: str, **etat) -> "AppTest":
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.session_state["utilisateur_id"] = ids["comptes"][nom]
    at.session_state["utilisateur_nom"] = nom
    at.session_state["utilisateur_role"] = role
    for cle, valeur in etat.items():
        at.session_state[cle] = valeur
    at.run()
    erreurs = [str(e.value) for e in at.exception]
    assert not erreurs, f"{nom} / {etat} : {erreurs}"
    return at


@pytest.mark.parametrize("onglet", ONGLETS_FICHE)
def test_chaque_onglet_de_la_patiente_s_ouvre(demonstration, onglet):
    sid = demonstration["patiente"]
    _ouvrir_demo(demonstration, "Démo — Senior", "senior", accueil_pose=True, ecran="",
                 sejour_id=sid, **{f"ecran_{sid}": onglet, f"segments_ecran_{sid}": onglet})


@pytest.mark.parametrize("nom,role,ecran", [
    ("Démo — Infirmière de jour", "infirmier", "poste"),
    ("Démo — Surveillant", "surveillant", "supervision"),
    ("Démo — Administrateur", "admin", "administration"),
])
def test_les_ecrans_de_service_de_la_demonstration(demonstration, nom, role, ecran):
    _ouvrir_demo(demonstration, nom, role, accueil_pose=True, ecran=ecran)


@pytest.mark.parametrize("vue", VUES_RECHERCHE)
def test_la_recherche_de_la_demonstration(demonstration, vue):
    _ouvrir_demo(demonstration, "Démo — Senior", "senior", accueil_pose=True,
                 ecran="recherche", vue_recherche=vue, segments_recherche=vue)


def test_la_demonstration_s_annonce(demonstration, monkeypatch):
    """Sur chaque écran, et dès l'ouverture avec les comptes et leur code."""
    from rea import config

    monkeypatch.setattr(config, "DEMONSTRATION", True)
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()
    assert any("BASE DE DÉMONSTRATION" in w.value and "demo2026" in w.value
               for w in at.warning)
    at = _ouvrir_demo(demonstration, "Démo — Senior", "senior")
    assert any("BASE DE DÉMONSTRATION" in w.value for w in at.warning)
