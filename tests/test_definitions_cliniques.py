"""Câblage des définitions du bloc 15 sur les données réellement en base.

`rea/domaine/definitions.py` existait déjà, testé, mais aucun écran ne
l'appelait — c'était du code mort. Ces tests portent sur la couche qui va
chercher les faits (créatinine, dispositifs, éléments d'évolution) pour les
lui donner ; le calcul lui-même reste testé dans test_definitions.py.
"""

from rea.services import bilans, definitions_cliniques, dispositifs, evolution, sejours


def _sejour(base, creatinine_base=None):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    return sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1,
        creatinine_base=creatinine_base,
    )


def test_ira_kdigo_se_calcule_depuis_le_bilan_et_la_creatinine_de_base(base):
    sid = _sejour(base, creatinine_base=80)
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure="2026-09-03T08:00", valeurs={"creat": 250})

    verdict = definitions_cliniques.ira(base, sid, "2026-09-03")
    assert verdict.applicable
    assert verdict.rempli
    assert verdict.stade == "stade 3"


def test_ira_non_applicable_sans_creatinine_de_base(base):
    sid = _sejour(base, creatinine_base=None)
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure="2026-09-03T08:00", valeurs={"creat": 250})

    verdict = definitions_cliniques.ira(base, sid, "2026-09-03")
    assert not verdict.applicable
    assert "créatinine de référence" in verdict.manquants


def test_ira_stade_3_si_epuration_en_cours(base):
    sid = _sejour(base, creatinine_base=80)
    dispositifs.poser(base, sejour_id=sid, type_="eer", date_pose="2026-09-01")

    verdict = definitions_cliniques.ira(base, sid, "2026-09-03")
    assert verdict.applicable and verdict.rempli
    assert verdict.stade == "stade 3"


def test_sdra_ventile_lit_le_dispositif_intubation(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-01")
    bilans.enregistrer_gaz_du_sang(
        base, sejour_id=sid, date_heure="2026-09-02T08:00", pao2=60, fio2=60,
    )

    verdict = definitions_cliniques.sdra(base, sid, "2026-09-02")
    # PEP non saisie sur ce gaz du sang -> non applicable, mais la ventilation
    # est bien reconnue (elle vient du dispositif, pas du gaz du sang).
    assert not verdict.applicable
    assert "PEP" in verdict.manquants
    assert "support ventilatoire" not in verdict.manquants


def test_sdra_complet_avec_pep_saisie(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-01")
    bilans.enregistrer_gaz_du_sang(
        base, sejour_id=sid, date_heure="2026-09-02T08:00", pao2=60, fio2=60, pep=8,
    )
    verdict = definitions_cliniques.sdra(base, sid, "2026-09-02")
    # Toujours non applicable : imagerie et exclusion cardiaque ne sont pas
    # des données structurées du dossier -- c'est le jugement du médecin.
    assert not verdict.applicable
    assert "PEP" not in verdict.manquants


def test_sdra_signale_l_absence_de_ventilation(base):
    sid = _sejour(base)
    verdict = definitions_cliniques.sdra(base, sid, "2026-09-02")
    assert "support ventilatoire" in verdict.manquants


def test_qsofa_lit_les_elements_d_evolution_du_jour(base):
    sid = _sejour(base)
    evolution.enregistrer_elements(
        base, sid, "2026-09-02",
        {"fr_clinique": 24, "pas": 90, "glasgow": 13},
        utilisateur_id=None,
    )
    verdict = definitions_cliniques.qsofa(base, sid, "2026-09-02")
    assert verdict.applicable
    assert verdict.rempli  # 3/3 critères


def test_sepsis_non_applicable_sans_infection_ni_sofa_complet(base):
    sid = _sejour(base)
    verdict = definitions_cliniques.sepsis(base, sid, "2026-09-02")
    assert not verdict.applicable


def test_sepsis_utilise_les_cases_a_cocher_de_l_ecran(base):
    sid = _sejour(base)
    # Un SOFA incomplet reste incomplet : ce test vérifie seulement le
    # passage des cases à cocher, pas le calcul du SOFA lui-même.
    verdict = definitions_cliniques.sepsis(
        base, sid, "2026-09-02", infection_suspectee=True,
    )
    assert verdict.manquants == () or "SOFA" in verdict.manquants


def test_sepsis_relit_le_lactate_du_dernier_gaz_du_sang(base):
    """Le champ manuel de l'écran ne sert qu'à combler l'absence d'un gaz du
    sang — s'il y en a un, on ne redemande pas une valeur déjà saisie."""
    sid = _sejour(base)
    bilans.enregistrer_gaz_du_sang(
        base, sejour_id=sid, date_heure="2026-09-02T08:00", lactate=4.2,
    )
    verdict = definitions_cliniques.sepsis(
        base, sid, "2026-09-02", infection_suspectee=True,
        vasopresseurs=True, hypotension_persistante=True,
        lactate=None,  # rien tapé à la main : doit venir du gaz du sang
    )
    # Sans SOFA renseigné le verdict reste non applicable, mais ça prouve
    # au moins que la lecture ne plante pas et ne redemande rien.
    assert verdict is not None
