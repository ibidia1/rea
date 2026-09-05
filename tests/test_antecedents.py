"""« Le patient a-t-il des antécédents ? » Oui / Non / Inconnu (SPEC §4.2
bis) — trois états, comme partout ailleurs dans ce logiciel : « inconnu »
n'est pas « non », même si les deux s'affichent comme « sans antécédent »."""

from rea.services import sejours


def _patient(base):
    return sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)


def test_etat_par_defaut_est_non_renseigne(base):
    pid = _patient(base)
    assert sejours.etat_antecedents(base, pid) == "non_renseigne"


def test_definir_absent(base):
    pid = _patient(base)
    sejours.definir_etat_antecedents(base, pid, "absent")
    assert sejours.etat_antecedents(base, pid) == "absent"
    assert sejours.antecedents_du_patient(base, pid) == []


def test_definir_non_renseigne_puis_absent_ne_duplique_pas(base):
    pid = _patient(base)
    sejours.definir_etat_antecedents(base, pid, "non_renseigne")
    sejours.definir_etat_antecedents(base, pid, "absent")
    assert sejours.etat_antecedents(base, pid) == "absent"


def test_ajout_d_un_antecedent_reel_l_emporte_sur_absent(base):
    pid = _patient(base)
    sejours.definir_etat_antecedents(base, pid, "absent")
    sejours.ajouter_antecedent(base, patient_id=pid, categorie="familial", libelle="Diabète (mère)")
    assert sejours.etat_antecedents(base, pid) == "oui"


def test_la_note_d_evaluation_n_apparait_jamais_dans_les_antecedents(base):
    pid = _patient(base)
    sejours.definir_etat_antecedents(base, pid, "non_renseigne")
    sejours.ajouter_antecedent(base, patient_id=pid, categorie="familial", libelle="Diabète (mère)")
    libelles = [a["libelle"] for a in sejours.antecedents_du_patient(base, pid)]
    assert libelles == ["Diabète (mère)"]


def test_tabagisme_avec_paquets_annees(base):
    pid = _patient(base)
    sejours.ajouter_antecedent(
        base, patient_id=pid, categorie="habitude", libelle="Tabagisme", code="tabagisme",
        quantification_valeur=20.0, quantification_unite="paquets-année",
    )
    atcd = sejours.antecedents_du_patient(base, pid)[0]
    assert atcd["quantification_valeur"] == 20.0
    assert atcd["quantification_unite"] == "paquets-année"


def test_toxicomanie_avec_substances_en_precision(base):
    pid = _patient(base)
    sejours.ajouter_antecedent(
        base, patient_id=pid, categorie="habitude", libelle="Toxicomanie", code="toxicomanie",
        precision="cannabis, cocaïne",
    )
    atcd = sejours.antecedents_du_patient(base, pid)[0]
    assert atcd["precision"] == "cannabis, cocaïne"


def test_etat_invalide_refuse(base):
    import pytest

    pid = _patient(base)
    with pytest.raises(ValueError):
        sejours.definir_etat_antecedents(base, pid, "present")
