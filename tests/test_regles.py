"""Moteur de règles déclaratif (bloc 7, règle R4).

Ce qui est testé ici, ce n'est pas le contenu des règles — il appartient au
service et vit dans des fichiers — mais le fait que le moteur les applique
fidèlement, y compris quand un fait manque.
"""

import pytest

from rea import aides as fichiers_regles
from rea.domaine import regles


def _regle(**kw):
    base = {"code": "r", "libelle": "R", "message": "m"}
    base.update(kw)
    return regles.Regle.depuis_dict(base)


def test_condition_simple():
    r = _regle(conditions=[{"fait": "jours_kt_central", "op": ">=", "valeur": 7}])
    assert regles.declenchee(r, {"jours_kt_central": 8})
    assert not regles.declenchee(r, {"jours_kt_central": 6})


def test_fait_absent_ne_declenche_rien():
    """« On ne sait pas » n'est pas « anormal » (règle de conception 7)."""
    r = _regle(conditions=[{"fait": "kaliemie", "op": "<", "valeur": 3.0}])
    assert not regles.declenchee(r, {})
    assert not regles.declenchee(r, {"kaliemie": None})


def test_operateur_non_renseigne_se_declenche_sur_l_absence():
    r = _regle(conditions=[{"fait": "poids_kg", "op": "non_renseigne"}])
    assert regles.declenchee(r, {})
    assert not regles.declenchee(r, {"poids_kg": 70})


def test_combinaison_et_puis_ou():
    conditions = [
        {"fait": "jours_intubation", "op": ">=", "valeur": 2},
        {"fait": "sng_en_place", "op": "faux"},
    ]
    et = _regle(conditions=conditions)
    ou = _regle(conditions=conditions, combinaison="ou")
    faits = {"jours_intubation": 3, "sng_en_place": True}
    assert not regles.declenchee(et, faits)
    assert regles.declenchee(ou, faits)


def test_operateur_inconnu_leve_une_erreur():
    """Une règle mal écrite doit se voir, pas se taire."""
    r = _regle(conditions=[{"fait": "x", "op": "≈", "valeur": 1}])
    with pytest.raises(regles.ConditionInvalide):
        regles.declenchee(r, {"x": 1})


def test_regle_sans_condition_ne_se_declenche_jamais():
    assert not regles.declenchee(_regle(), {"tout": 1})


def test_tri_par_gravite():
    r_info = _regle(code="a", gravite="info", conditions=[{"fait": "x", "op": "vrai"}])
    r_alerte = _regle(code="b", gravite="alerte", conditions=[{"fait": "x", "op": "vrai"}])
    ordre = regles.declenchees([r_info, r_alerte], {"x": True})
    assert [r.code for r in ordre] == ["b", "a"]


# -- fichiers livrés ---------------------------------------------------------

def test_les_regles_livrees_se_chargent_et_s_evaluent():
    toutes = fichiers_regles.toutes_les_regles()
    assert toutes, "aucune règle chargée"
    faits_vides = {}
    for r in toutes:
        assert r.message
        regles.declenchee(r, faits_vides)  # ne doit jamais lever


def test_aucune_regle_livree_ne_parle_de_posologie():
    """SPEC §3.1 : le logiciel calcule des dates, des heures et des volumes,
    jamais une dose. Une règle qui proposerait une posologie franchirait la
    limite — ce test la rattrape."""
    interdits = ("mg/kg", "µg/kg", "mg/j", "UI/kg", "administrer", "injecter")
    for r in fichiers_regles.toutes_les_regles():
        message = r.message.lower()
        for mot in interdits:
            assert mot.lower() not in message, f"{r.code} : « {mot} »"


def test_checklist_fast_hug_a_sept_items():
    items = fichiers_regles.checklist().get("items", [])
    assert [i["lettre"] for i in items] == ["F", "A", "S", "T", "H", "U", "G"]


def test_checklist_distingue_non_renseigne_et_a_verifier():
    items = fichiers_regles.checklist()["items"]
    resultats = {i.code: i for i in regles.evaluer_checklist(items, {})}
    assert resultats["glucose"].etat == "non_renseigne"

    resultats = {
        i.code: i
        for i in regles.evaluer_checklist(items, {"glycemie_du_jour": 6.1,
                                                  "thromboprophylaxie_prescrite": False})
    }
    assert resultats["glucose"].etat == "ok"
    assert resultats["thrombo"].etat == "a_verifier"
