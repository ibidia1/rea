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


# =========================================================================
# §2.4 — contraintes d'architecture
#
# Un poste unique, un utilisateur à la fois, pas de réseau. Le §2.4 pose des
# invariants dont l'intérêt est justement de tenir *avant* qu'on en ait
# besoin : le jour du multi-postes, aucun d'eux ne doit demander une migration
# sur des données cliniques réelles. Un invariant qu'aucun test ne tient finit
# par ne plus être vrai — et celui-là ne se remarquerait que trop tard.
# =========================================================================

import re  # noqa: E402
import tomllib  # noqa: E402

SCHEMA = (RACINE / "rea" / "schema.sql").read_text(encoding="utf-8")

# Quatre tables hors du dispositif de traçabilité, chacune pour sa raison —
# voir l'en-tête de schema.sql.
HORS_TRACABILITE = {"meta", "pancarte_snapshot", "journal", "sauvegarde"}
TRACABILITE = ("version", "cree_le", "cree_par", "modifie_le", "modifie_par", "supprime")


def _tables_du_schema() -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in re.finditer(
            r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", SCHEMA, re.S
        )
    }


def _tables_tracees() -> list[str]:
    return [t for t in _tables_du_schema() if t not in HORS_TRACABILITE]


@pytest.mark.parametrize("table", _tables_tracees())
@pytest.mark.parametrize("colonne", TRACABILITE)
def test_chaque_table_modifiable_porte_la_tracabilite(table, colonne):
    """§2.4, invariant 1 — aucune hypothèse « un seul utilisateur ».

    Ces six colonnes coûtent une minute aujourd'hui et une migration sur des
    dossiers réels demain. C'est le dernier moment où elles sont bon marché.
    """
    corps = _tables_du_schema()[table]
    assert re.search(rf"^\s*{colonne}\s", corps, re.M), (
        f"{table} n'a pas de colonne {colonne}"
    )


def test_la_table_utilisateur_porte_un_pin():
    """§2.4, invariant 1 — vide aujourd'hui (AUTH_REQUISE = False), présent
    pour que le jour du multi-postes ne touche pas au schéma."""
    assert re.search(r"^\s*pin\s+TEXT", _tables_du_schema()["utilisateur"], re.M)


def test_la_version_sincremente_a_chaque_ecriture(base):
    """Personne ne la lit encore : c'est justement pour ça qu'un test doit la
    tenir, sinon elle cesserait d'être juste sans que rien ne le signale."""
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="V1", nom_affichage="V",
                                date_naissance=None)
    lire = lambda: base.une_ligne("SELECT version FROM patient WHERE id = ?", (pid,))["version"]  # noqa: E731
    assert lire() == 1
    sejours.modifier_identite(base, pid, matricule="V2", nom_affichage="V",
                              date_naissance=None, sexe="M", groupe_sanguin=None)
    assert lire() == 2
    sejours.modifier_identite(base, pid, matricule="V3", nom_affichage="V",
                              date_naissance=None, sexe="M", groupe_sanguin=None)
    assert lire() == 3


def test_une_suppression_logique_incremente_aussi_la_version(base):
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="V9", nom_affichage="V",
                                date_naissance=None)
    aid = sejours.ajouter_antecedent(base, patient_id=pid, categorie="personnel",
                                     libelle="Diabète")
    sejours.supprimer_antecedent(base, aid)
    ligne = base.une_ligne("SELECT version, supprime FROM antecedent WHERE id = ?", (aid,))
    assert (ligne["version"], ligne["supprime"]) == (2, 1)


def test_le_numero_dimpression_dune_feuille_nest_pas_un_compteur_de_version(base):
    """`pancarte_snapshot.version` désigne le numéro d'impression (v1, v2 de la
    même feuille). L'incrémenter à chaque écriture renumérote des feuilles déjà
    sorties de l'imprimante : la table est explicitement exclue."""
    from rea.db import TABLES_SANS_COMPTEUR_DE_VERSION

    assert "pancarte_snapshot" in TABLES_SANS_COMPTEUR_DE_VERSION


def test_aucune_suppression_physique_dans_le_code():
    """§2.4 rappelle la règle de conception 2 : rien ne s'efface, tout se
    marque supprimé. Un DELETE sur un dossier clinique est irrattrapable."""
    fautifs = []
    for chemin in (RACINE / "rea").rglob("*.py"):
        texte = chemin.read_text(encoding="utf-8")
        if re.search(r"\bDELETE\s+FROM\b", texte, re.I):
            fautifs.append(chemin.name)
    assert not fautifs, f"DELETE FROM trouvé dans : {fautifs}"


@pytest.mark.parametrize("chemin", _fichiers(UI), ids=lambda p: p.name)
def test_aucun_ecran_ne_contient_de_sql(chemin):
    """§2.4, invariant 3 — les vues appellent des fonctions métier, jamais une
    requête. Une requête écrite dans un écran échappe aux tests et se recopie
    au prochain écran qui en a besoin."""
    texte = chemin.read_text(encoding="utf-8")
    trouve = re.findall(r"\b(SELECT\s+\w|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
                        texte, re.I)
    assert not trouve, f"{chemin.name} contient du SQL : {trouve}"


def test_le_reglage_reseau_du_depot_reste_la_boucle_locale():
    """Ce que le dépôt livre : un poste isolé.

    Ouvrir l'écoute est une décision d'installation — la variable
    `REA_HOTE` sur le poste du service — et non un réglage qui part dans
    le dépôt. Livrer « 0.0.0.0 » exposerait le dossier de tout service qui
    installe le logiciel sans y penser.
    """
    from rea import config

    reglages = tomllib.loads((RACINE / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert reglages["server"]["address"] == "127.0.0.1"
    assert config.HOTE == "127.0.0.1", (
        "REA_HOTE ne doit pas être positionné pendant les tests"
    )
    assert reglages["server"]["port"] == config.PORT


def test_ouvrir_le_reseau_exige_l_authentification():
    """La règle du §2.4, tenue par le code et non par la vigilance.

    « HOTE s'ouvre et AUTH passe à True — les deux ensemble, jamais l'un
    sans l'autre » était un commentaire. Un commentaire s'oublie : c'est
    maintenant une conséquence calculée, et ce test le vérifie sur les deux
    branches.
    """
    import importlib
    import os

    from rea import config

    assert not config.AUTH_EXIGEE, "boucle locale : pas d'authentification exigée"

    ancien = os.environ.get("REA_HOTE")
    os.environ["REA_HOTE"] = "0.0.0.0"
    try:
        ouvert = importlib.reload(config)
        assert ouvert.AUTH_EXIGEE, (
            "écoute sur le réseau sans authentification exigée : "
            "le dossier serait lisible depuis n'importe quel téléphone"
        )
        assert ouvert.LONGUEUR_CODE_MINIMALE >= 6
        assert ouvert.ESSAIS_AVANT_BLOCAGE <= 10
    finally:
        if ancien is None:
            os.environ.pop("REA_HOTE", None)
        else:
            os.environ["REA_HOTE"] = ancien
        importlib.reload(config)
