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


# --- retirer un antécédent (demande du service, 8 septembre) ---------------

def test_supprimer_un_antecedent_le_retire_de_la_liste(base):
    """Un antécédent se saisit vite et se trompe vite : sans moyen de le
    retirer, il se recopie ensuite sur chaque feuille imprimée."""
    pid = _patient(base)
    aid = sejours.ajouter_antecedent(base, patient_id=pid, categorie="personnel",
                                     libelle="Diabète", code="diabete")
    sejours.ajouter_antecedent(base, patient_id=pid, categorie="personnel", libelle="HTA")

    sejours.supprimer_antecedent(base, aid)

    libelles = [a["libelle"] for a in sejours.antecedents_du_patient(base, pid)]
    assert libelles == ["HTA"]


def test_la_suppression_est_logique_jamais_physique(base):
    """Règle de conception 2 : la ligne reste en base, marquée supprimée."""
    pid = _patient(base)
    aid = sejours.ajouter_antecedent(base, patient_id=pid, categorie="personnel",
                                     libelle="Diabète")
    sejours.supprimer_antecedent(base, aid)
    ligne = base.une_ligne("SELECT supprime FROM antecedent WHERE id = ?", (aid,))
    assert ligne["supprime"] == 1


def test_retirer_le_dernier_antecedent_ramene_letat_a_non_renseigne(base):
    """Plus aucun antécédent réel : la réponse Oui/Non/Inconnu redevient
    ouverte, elle n'est pas figée sur « oui »."""
    pid = _patient(base)
    aid = sejours.ajouter_antecedent(base, patient_id=pid, categorie="personnel",
                                     libelle="Diabète")
    assert sejours.etat_antecedents(base, pid) == "oui"
    sejours.supprimer_antecedent(base, aid)
    assert sejours.etat_antecedents(base, pid) == "non_renseigne"


def test_une_allergie_supprimee_disparait_des_allergies(base):
    pid = _patient(base)
    aid = sejours.ajouter_antecedent(base, patient_id=pid, categorie="allergie",
                                     libelle="Pénicilline")
    assert len(sejours.allergies_du_patient(base, pid)) == 1
    sejours.supprimer_antecedent(base, aid)
    assert sejours.allergies_du_patient(base, pid) == []
