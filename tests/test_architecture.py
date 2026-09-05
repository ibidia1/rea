"""Les règles d'isolation entre couches, vérifiées plutôt que documentées.

La feuille de route pose R1 à R5. Elles ont toutes été enfreintes au moins une
fois pendant le développement, et à chaque fois ce sont des heures de
débogage : une règle qu'aucun test ne tient finit par ne plus être vraie.

Ces tests lisent le code, ils ne l'exécutent pas.
"""

import ast
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
DOMAINE = RACINE / "rea" / "domaine"
RENDU = RACINE / "rea" / "rendu"
UI = RACINE / "rea" / "ui"


def _imports(chemin: pathlib.Path) -> set[str]:
    """Les modules importés par un fichier, en notation pointée."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    vus = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            vus.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = "." * n.level + (n.module or "")
            vus.add(base)
            vus.update(f"{base}.{a.name}" for a in n.names)
    return vus


def _fichiers(dossier: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in dossier.glob("*.py") if p.name != "__init__.py")


# -- R3 : le rendu reçoit, il ne va pas chercher --------------------------

@pytest.mark.parametrize("chemin", _fichiers(RENDU), ids=lambda p: p.name)
def test_le_rendu_n_ouvre_pas_la_base_ni_n_appelle_un_service(chemin):
    """Règle R3. `rendu/feuille.py` importait `db.Base` et six services : il
    décidait quoi lire, alors qu'il ne doit que remplir une maquette avec ce
    qu'on lui donne. C'était la dépendance la plus lourde du dépôt, et elle
    obligeait `services/pancarte.py` à un import différé pour éviter le cycle.
    """
    interdits = [
        i for i in _imports(chemin)
        if "services" in i or i.endswith("db") or i.endswith("db.Base")
    ]
    assert not interdits, (
        f"{chemin.name} va chercher ses données lui-même : {sorted(interdits)}. "
        "Le rendu doit recevoir un dossier déjà rassemblé (services/feuille_dossier.py)."
    )


def test_le_dossier_de_feuille_ne_contient_aucune_mise_en_forme():
    """L'inverse de R3 : le service qui rassemble ne doit pas se mettre à
    fabriquer du HTML, sinon la frontière se brouille dans l'autre sens."""
    source = (RACINE / "rea" / "services" / "feuille_dossier.py").read_text(encoding="utf-8")
    for marqueur in ("<div", "<span", "<table", "&nbsp;", "Brut("):
        assert marqueur not in source, f"mise en forme dans le rassembleur : {marqueur}"


# -- R1 : une seule couche écrit -------------------------------------------

@pytest.mark.parametrize("chemin", _fichiers(UI), ids=lambda p: p.name)
def test_aucun_ecran_n_ecrit_directement_en_base(chemin):
    """Règle R1. Un écran passe par un service ; sinon l'écriture échappe au
    journal d'audit et à la transaction qui l'entoure."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    ecritures = [
        n.lineno for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("inserer", "mettre_a_jour", "supprimer_logiquement")
    ]
    assert not ecritures, f"{chemin.name} écrit en base (lignes {ecritures})"


# -- le domaine reste pur ---------------------------------------------------

@pytest.mark.parametrize("chemin", _fichiers(DOMAINE), ids=lambda p: p.name)
def test_le_domaine_ignore_la_base_et_les_services(chemin):
    """C'est la propriété la plus précieuse du dépôt : tout le calcul médical
    (scores, cohérence, prescription, règles) se teste sans base."""
    interdits = [
        i for i in _imports(chemin)
        if "services" in i or "streamlit" in i or i.endswith("db")
    ]
    assert not interdits, f"{chemin.name} dépend de : {sorted(interdits)}"


# -- pas de cycle -----------------------------------------------------------

def test_aucun_cycle_d_import_dans_le_paquet():
    """Un cycle se contourne d'habitude par un import différé au milieu d'une
    fonction — ça marche, et ça cache le problème de conception."""
    paquet = RACINE / "rea"
    graphe: dict[str, set[str]] = {}
    for chemin in paquet.rglob("*.py"):
        module = ".".join(chemin.relative_to(RACINE).with_suffix("").parts)
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        cibles = set()
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ImportFrom) or not n.level:
                continue
            dossier = chemin.parent
            for _ in range(n.level - 1):
                dossier = dossier.parent
            prefixe = ".".join(dossier.relative_to(RACINE).parts)
            base = f"{prefixe}.{n.module}" if n.module else prefixe
            for a in n.names:
                candidat = f"{base}.{a.name}"
                chemin_candidat = RACINE / (candidat.replace(".", "/") + ".py")
                cibles.add(candidat if chemin_candidat.exists() else base)
        graphe[module] = cibles

    chemin_courant: list[str] = []
    vus: set[str] = set()
    cycles: list[list[str]] = []

    def descendre(module: str) -> None:
        if module in chemin_courant:
            cycles.append(chemin_courant[chemin_courant.index(module):] + [module])
            return
        if module in vus:
            return
        vus.add(module)
        chemin_courant.append(module)
        for suivant in sorted(graphe.get(module, ())):
            descendre(suivant)
        chemin_courant.pop()

    for module in sorted(graphe):
        descendre(module)

    assert not cycles, "cycles d'import : " + "; ".join(
        " -> ".join(c) for c in cycles[:5]
    )
