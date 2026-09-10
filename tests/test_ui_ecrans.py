"""Les écrans, maintenant qu'ils sont des modules ordinaires.

Tant que tout tenait dans `rea_app.py`, rien de tout ceci n'était atteignable :
importer ce fichier exécutait la page Streamlit entière. Les écrans découpés
s'importent isolément, donc se vérifient.

On ne rejoue pas ici l'affichage — Streamlit s'en charge, et le parcours réel
est fait au navigateur. On vérifie ce qui casse silencieusement : qu'un écran
s'importe, et que les petites lectures de champs partagées se comportent comme
le reste du logiciel l'attend. Les règles d'isolation entre couches, elles,
sont dans `test_architecture.py`.
"""

import ast
import importlib
import pathlib
import re

import pytest

from rea import referentiels
from rea.ui import champs

ECRANS = [
    "champs", "contexte", "lits", "admission", "identite", "prescrit",
    "bilans", "evolution", "actes", "sortie", "visite", "fiche",
    "infirmier", "surveillant", "surveillance", "bandeau", "comptes",
    "utilisateur",
    "recherche", "administration",
]


# -- montage ---------------------------------------------------------------

@pytest.mark.parametrize("nom", ECRANS)
def test_chaque_ecran_s_importe_seul(nom):
    """Un écran qui ne s'importe pas seul ne se teste pas, et casse au premier
    clic sans que rien ne l'ait signalé avant."""
    assert importlib.import_module(f"rea.ui.{nom}") is not None


def test_le_point_d_entree_ne_contient_plus_d_ecran():
    """rea_app.py ne doit plus être qu'un montage : page, barre latérale,
    aiguillage. C'est ce qui garde les écrans testables."""
    source = pathlib.Path(__file__).resolve().parent.parent / "rea_app.py"
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    fonctions = [n.name for n in arbre.body if isinstance(n, ast.FunctionDef)]
    assert fonctions == [], f"écrans restés dans rea_app.py : {fonctions}"
    assert len(source.read_text(encoding="utf-8").splitlines()) < 120


# -- lectures de champs partagées -----------------------------------------

@pytest.mark.parametrize("saisi, attendu", [
    ("9,2", 9.2),          # au lit du malade on tape une virgule
    ("9.2", 9.2),
    ("  40 ", 40.0),
    ("1 200", 1200.0),     # espace de milliers
    ("0", 0.0),            # zéro est une valeur, pas une absence
])
def test_nombre_saisi_lit_ce_qui_est_tape(saisi, attendu):
    assert champs.nombre_saisi(saisi) == attendu


@pytest.mark.parametrize("saisi", ["", "   ", None, "abc", "12,3,4"])
def test_nombre_saisi_rend_non_renseigne_plutot_que_zero(saisi):
    """Règle de conception 6 : vide et zéro ne sont pas la même chose. Un
    champ laissé blanc ne doit jamais devenir 0 dans un calcul de score."""
    assert champs.nombre_saisi(saisi) is None


@pytest.mark.parametrize("valeur, attendu", [
    (None, "—"),           # non renseigné se voit
    (8.0, "8"),            # pas de « 8.0 » sur une feuille imprimée
    (8.2, "8.2"),
    (215.0, "215"),
])
def test_format_valeur_affiche_sans_decimale_inutile(valeur, attendu):
    assert champs.format_valeur(valeur) == attendu


# -- mode visite : il lit, il n'écrit pas -----------------------------------

def test_lecran_de_visite_nappelle_aucune_ecriture():
    """À la visite on lit et on discute, on ne prescrit pas d'une main en
    tenant un chariot de l'autre. Un bouton d'arrêt de traitement à portée de
    manche est un traitement arrêté par erreur.

    Vérifié sur le code : aucun appel de service dont le nom dit qu'il écrit.
    """
    source = (pathlib.Path(referentiels.__file__).parent / "ui" / "visite.py").read_text(
        encoding="utf-8"
    )
    arbre = ast.parse(source)
    ecritures = []
    prefixes = ("enregistrer", "ajouter", "modifier", "arreter", "supprimer",
                "poser", "retirer", "creer", "definir", "demander", "changer",
                "regler", "imprimer", "obtenir_ou_creer")
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call) or not isinstance(noeud.func, ast.Attribute):
            continue
        if noeud.func.attr.startswith(prefixes):
            ecritures.append(ast.unparse(noeud.func))
    assert not ecritures, (
        f"L'écran de visite appelle {', '.join(sorted(set(ecritures)))} : "
        "il doit rester en lecture seule."
    )


# -- versions de Streamlit -------------------------------------------------

def test_le_composant_html_marche_sans_st_iframe(monkeypatch):
    """`st.components.v1.html` est déprécié depuis la 1.63 au profit de
    `st.iframe`. Avoir suivi l'avertissement a cassé l'écran Évolution sur le
    poste du service, qui tourne une version antérieure : `AttributeError`, et
    l'écran ne s'affichait plus du tout.

    Le poste n'est pas mis à jour d'un clic — il est hors ligne, et on ne
    touche pas à son environnement pendant qu'il porte les patients. Les deux
    noms doivent donc marcher.
    """
    import streamlit as st

    evolution = importlib.import_module("rea.ui.evolution")

    monkeypatch.delattr(st, "iframe", raising=False)
    assert evolution._composant_html() is st.components.v1.html

    sentinelle = object()
    monkeypatch.setattr(st, "iframe", sentinelle, raising=False)
    assert evolution._composant_html() is sentinelle


def test_le_socle_streamlit_couvre_les_appels_utilises():
    """`requirements.txt` annonçait 1.36 alors que les écrans appellent
    `st.segmented_control`, arrivé en 1.40. Un plancher faux ne se voit qu'à
    l'installation sur un poste neuf, écran blanc à l'appui."""
    racine = pathlib.Path(__file__).resolve().parent.parent
    exigences = (racine / "requirements.txt").read_text(encoding="utf-8")
    plancher = re.search(r"streamlit\s*>=\s*(\d+)\.(\d+)", exigences)
    assert plancher, "requirements.txt doit fixer une version minimale de Streamlit"
    majeure, mineure = int(plancher[1]), int(plancher[2])
    assert (majeure, mineure) >= (1, 40), (
        "st.segmented_control (rea/ui/fiche.py, rea/ui/prescrit.py) demande "
        "Streamlit 1.40 au minimum"
    )


# -- survivre à un référentiel qui change ---------------------------------
#
# Vécu, pas théorique : un bilan enregistré sous le code `gaz_du_sang`, code
# disparu depuis du référentiel des examens, rendait l'écran Prescrit
# entièrement inaccessible pour ce patient — Streamlit refuse une valeur par
# défaut absente des options, et l'exception emporte tout l'écran. Le dossier
# était intact, mais on ne pouvait plus prescrire.

def test_une_valeur_disparue_du_referentiel_ne_fait_pas_tomber_l_ecran():
    options = ["nfs", "iono", "crp"]
    assert champs.index_ou_zero(options, "iono") == 1
    assert champs.index_ou_zero(options, "gaz_du_sang") == 0
    assert champs.index_ou_zero(options, None) == 0
    assert champs.index_ou_zero([], "quoi que ce soit") == 0


def test_seules_les_valeurs_encore_connues_sont_recochees():
    options = ["nfs", "iono", "crp"]
    gardees = champs.valeurs_connues(options, {"crp", "gaz_du_sang", "nfs"})
    assert gardees == ["nfs", "crp"], "et dans l'ordre des options"


def test_ce_qui_a_disparu_est_dit_et_non_tu():
    """Une case qui se décoche toute seule entre deux ouvertures est pire
    qu'un message qui explique pourquoi."""
    options = ["nfs", "iono"]
    assert champs.valeurs_oubliees(options, ["nfs", "gaz_du_sang"]) == ["gaz_du_sang"]
    assert champs.valeurs_oubliees(options, ["nfs"]) == []


def test_libelle_tolere_une_liste_plate():
    """`UNITES` est une liste de chaînes — « mg », « g » — et non des paires.
    `entree[0]` y lit la première lettre, `entree[1]` la deuxième : une unité
    d'une seule lettre levait `IndexError` et emportait l'écran des
    protocoles. Trouvé en ouvrant chaque écran de chaque rôle."""
    from rea import listes

    assert listes.libelle(listes.UNITES, "g") == "g"
    assert listes.libelle(listes.UNITES, "mg") == "mg"
    assert listes.libelle(listes.UNITES, "inconnu") == "inconnu"
    assert listes.libelle(listes.ROLES, "senior") == "Senior"
