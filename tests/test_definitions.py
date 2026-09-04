"""Définitions standard (bloc 15).

Ce qui compte ici autant que le classement correct : qu'une définition qu'on
ne peut pas appliquer ne soit jamais comptée comme un cas négatif.
"""

from rea.domaine import definitions as d


# -- Berlin ------------------------------------------------------------------

def _berlin(pf, **kw):
    params = dict(pao2_fio2=pf, peep=8, ventile=True, delai_jours=2,
                  imagerie_bilaterale=True, origine_cardiaque_exclue=True)
    params.update(kw)
    return d.sdra_berlin(**params)


def test_berlin_les_trois_stades():
    assert _berlin(250).stade == "léger"
    assert _berlin(150).stade == "modéré"
    assert _berlin(80).stade == "sévère"


def test_berlin_bornes_exactes():
    assert _berlin(300).stade == "léger"
    assert _berlin(301).rempli is False
    assert _berlin(200).stade == "modéré"
    assert _berlin(100).stade == "sévère"


def test_berlin_exige_une_pep_suffisante():
    assert _berlin(150, peep=3).rempli is False


def test_berlin_sans_gaz_du_sang_est_non_applicable():
    verdict = _berlin(None)
    assert verdict.applicable is False
    assert verdict.rempli is False
    assert "PaO₂/FiO₂" in verdict.manquants


def test_berlin_imagerie_inconnue_est_non_applicable():
    """« On ne sait pas » n'est pas « pas de SDRA »."""
    assert _berlin(150, imagerie_bilaterale=None).applicable is False


# -- KDIGO -------------------------------------------------------------------

def test_kdigo_stades_par_creatinine():
    assert d.ira_kdigo(creatinine=100, creatinine_base=70).stade == "stade 1"
    assert d.ira_kdigo(creatinine=160, creatinine_base=70).stade == "stade 2"
    assert d.ira_kdigo(creatinine=250, creatinine_base=70).stade == "stade 3"


def test_kdigo_hausse_absolue_suffit_au_stade_1():
    verdict = d.ira_kdigo(creatinine=100, creatinine_base=72)
    assert verdict.stade == "stade 1"


def test_kdigo_epuration_vaut_stade_3():
    verdict = d.ira_kdigo(creatinine=None, creatinine_base=None,
                          epuration_en_cours=True)
    assert verdict.stade == "stade 3"
    assert verdict.applicable


def test_kdigo_sans_creatinine_de_reference_est_non_applicable():
    """C'est la raison d'être de la créatinine antérieure demandée à
    l'admission : elle ne se retrouve pas après coup."""
    verdict = d.ira_kdigo(creatinine=200, creatinine_base=None)
    assert verdict.applicable is False
    assert "créatinine de référence" in verdict.manquants


def test_kdigo_prend_le_stade_le_plus_severe_des_deux_criteres():
    verdict = d.ira_kdigo(creatinine=100, creatinine_base=70,
                          diurese_ml_kg_h=0.2, duree_oligurie_h=26)
    assert verdict.stade == "stade 3"


def test_kdigo_fonction_normale():
    verdict = d.ira_kdigo(creatinine=70, creatinine_base=70)
    assert verdict.applicable and not verdict.rempli


# -- Sepsis-3 ----------------------------------------------------------------

def test_qsofa_deux_criteres_sur_trois():
    verdict = d.qsofa(frequence_respiratoire=24, pas=95, glasgow=15)
    assert verdict.rempli and verdict.stade == "2/3"


def test_qsofa_incomplet_reste_non_applicable():
    verdict = d.qsofa(frequence_respiratoire=24, pas=None, glasgow=15)
    assert verdict.applicable is False


def test_sepsis3_demande_une_hausse_de_deux_points():
    assert d.sepsis3(infection_suspectee=True, sofa_actuel=3, sofa_initial=2).rempli is False
    assert d.sepsis3(infection_suspectee=True, sofa_actuel=4, sofa_initial=2).stade == "sepsis"


def test_sepsis3_choc_septique():
    verdict = d.sepsis3(
        infection_suspectee=True, sofa_actuel=6, sofa_initial=0,
        lactate=3.2, vasopresseurs=True, hypotension_persistante=True,
    )
    assert verdict.stade == "choc septique"


def test_sepsis3_sans_infection_suspectee_est_non_applicable():
    verdict = d.sepsis3(infection_suspectee=None, sofa_actuel=6)
    assert verdict.applicable is False


def test_toutes_les_definitions_portent_leur_reference():
    verdicts = [
        _berlin(150),
        d.ira_kdigo(creatinine=200, creatinine_base=70),
        d.qsofa(frequence_respiratoire=24, pas=95, glasgow=15),
        d.sepsis3(infection_suspectee=True, sofa_actuel=4),
    ]
    for v in verdicts:
        assert v.reference and "JAMA" in v.reference or "Kidney" in v.reference
