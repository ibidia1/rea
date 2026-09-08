"""Un changement de dose n'est pas un nouveau traitement (SPEC §5.1).

Le cas qui a motivé ces deux niveaux : Tienam 1 g × 3/j introduit à J1, passé
à 500 mg × 3/j à J4 pour une insuffisance rénale. Avant, il fallait choisir
entre deux erreurs — modifier la ligne et perdre la posologie initiale, ou en
ouvrir une seconde et faire repartir le compteur à J1. La durée
d'antibiothérapie rendue au comité des infections était fausse dans les deux
cas, et c'est un chiffre qui sort du service.
"""

from datetime import date, timedelta

import pytest

from rea.domaine import prescription as dom
from rea.services import prescriptions, sejours, statistiques

J1 = "2026-09-01"
J4 = "2026-09-04"
J7 = "2026-09-07"


@pytest.fixture()
def sejour(base):
    pid = sejours.creer_patient(base, matricule="M-EP", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission=J1,
                                lit_admission=1)


@pytest.fixture()
def tienam(base, sejour):
    return prescriptions.ajouter_ligne(
        base, sejour_id=sejour, voie="IV", produit="Tienam", date_debut=J1,
        dose=1, unite="g", rythme="x3/j", duree_prevue_jours=7,
        indication="pneumopathie nosocomiale",
    )


# -- le compteur ne repart pas ----------------------------------------------

def test_le_compteur_de_jours_ne_repart_pas_apres_un_changement_de_dose(
    base, sejour, tienam
):
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500,
                                    unite="mg", motif="adaptation rénale")
    ligne = prescriptions.lignes_actives_le(base, sejour, J4)[0]
    assert dom.etiquette_jour(ligne, J4).texte == "J4/7"


def test_la_posologie_initiale_reste_lisible(base, sejour, tienam):
    """Relire la pancarte de J2 doit montrer ce qui a été donné à J2."""
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500,
                                    unite="mg")
    hier = prescriptions.lignes_actives_le(base, sejour, "2026-09-02")[0]
    assert (hier["dose"], hier["unite"]) == (1, "g")
    apres = prescriptions.lignes_actives_le(base, sejour, J4)[0]
    assert (apres["dose"], apres["unite"]) == (500, "mg")


def test_un_seul_episode_pour_deux_posologies(base, sejour, tienam):
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500, unite="mg")
    assert len(prescriptions.episodes(base, sejour)) == 1
    assert len(prescriptions.posologies(base, tienam)) == 2


# -- la durée d'antibiothérapie ---------------------------------------------

def test_la_duree_dantibiotherapie_court_depuis_la_premiere_dose(base, sejour, tienam):
    """Le chiffre qui sort du service : sept jours de traitement, quel que
    soit le nombre de fois où la dose a été adaptée."""
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500, unite="mg")
    prescriptions.changer_posologie(base, tienam, a_partir_du="2026-09-05", dose=250,
                                    unite="mg")
    prescriptions.arreter_ligne(base, tienam, date_arret=J7, motif_arret="fin de cure")
    lignes = [base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sejour,))]
    consommation = statistiques.consommation_antibiotiques(base, lignes)
    assert consommation["jours_de_traitement"] == 7


# -- ce qu'une version décide, et ce qu'elle ne décide pas -------------------

def test_changer_la_dose_ne_touche_pas_a_lidentite_du_traitement(base, tienam):
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500, unite="mg")
    episode = base.une_ligne("SELECT * FROM prescription_ligne WHERE id = ?", (tienam,))
    assert episode["produit"] == "Tienam"
    assert episode["indication"] == "pneumopathie nosocomiale"
    assert episode["date_debut"] == J1
    # La posologie d'introduction reste écrite sur l'épisode, telle qu'au
    # premier jour : c'est ce qui permet de la relire sans reconstituer
    # l'historique.
    assert episode["dose"] == 1


def test_les_champs_non_fournis_sont_repris_de_la_version_en_cours(base, tienam):
    """On change une dose, pas toute la prescription : le rythme suit."""
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500, unite="mg")
    version = prescriptions.posologies(base, tienam)[-1]
    assert version["rythme"] == "x3/j"


def test_reenregistrer_la_meme_dose_ne_cree_pas_de_version(base, tienam):
    """« J4 : dose inchangée » n'apprend rien et rend l'historique illisible."""
    assert prescriptions.changer_posologie(
        base, tienam, a_partir_du=J4, dose=1, unite="g", rythme="x3/j") is None
    assert len(prescriptions.posologies(base, tienam)) == 1


def test_une_correction_le_jour_meme_remplace_la_version_du_jour(base, tienam):
    """Deux versions le même jour, c'est une seule posologie appliquée et une
    ligne d'historique de trop."""
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500, unite="mg")
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=750, unite="mg")
    versions = prescriptions.posologies(base, tienam)
    assert len(versions) == 2
    assert versions[-1]["dose"] == 750


def test_modifier_la_dose_sans_version_est_refuse(base, tienam):
    """Le garde-fou : écraser la dose écraserait aussi les jours passés."""
    with pytest.raises(ValueError, match="changer_posologie"):
        prescriptions.modifier_ligne(base, tienam, {"dose": 500})
    with pytest.raises(ValueError, match="changer_posologie"):
        prescriptions.modifier_ligne(base, tienam, {"rythme": "x2/j"})
    # L'identité, elle, reste corrigeable.
    prescriptions.modifier_ligne(base, tienam, {"indication": "PAVM"})
    assert base.une_ligne("SELECT indication FROM prescription_ligne WHERE id = ?",
                          (tienam,))["indication"] == "PAVM"


# -- ce que voit la pancarte -------------------------------------------------

def test_une_version_ne_sapplique_pas_retroactivement(base, sejour, tienam):
    prescriptions.changer_posologie(base, tienam, a_partir_du=J7, dose=500, unite="mg")
    for jour in ("2026-09-01", "2026-09-03", "2026-09-06"):
        assert prescriptions.lignes_actives_le(base, sejour, jour)[0]["dose"] == 1
    assert prescriptions.lignes_actives_le(base, sejour, J7)[0]["dose"] == 500


def test_la_ligne_dit_depuis_quand_sa_posologie_court(base, sejour, tienam):
    """Sans ça, « 500 mg » à J6 ne dit pas si c'est nouveau ou pas."""
    prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dose=500,
                                    unite="mg", motif="adaptation rénale")
    ligne = prescriptions.lignes_actives_le(base, sejour, "2026-09-06")[0]
    assert ligne["posologie_depuis"] == J4
    assert ligne["posologie_motif"] == "adaptation rénale"


def test_lheure_de_prise_deplacee_ouvre_une_version(base, tienam):
    """L'heure de prise fait partie de la posologie."""
    prescriptions.horaires_ligne(base, tienam, "6,14,22", a_partir_du=J4)
    assert len(prescriptions.posologies(base, tienam)) == 2
    assert prescriptions.posologies(base, tienam)[-1]["horaires_override"] == "6,14,22"


def test_une_ligne_du_jour_saffiche_avec_sa_dose_sans_date_demandee(base, sejour):
    """`toutes_les_lignes` sans date : la dernière posologie connue."""
    aujourdhui = date.today().isoformat()
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sejour, voie="PO", produit="Kardégic",
        date_debut=aujourdhui, dose=75, unite="mg", rythme="x1/j")
    demain = (date.today() + timedelta(days=1)).isoformat()
    prescriptions.changer_posologie(base, ligne_id, a_partir_du=demain, dose=160)
    ligne = next(l for l in prescriptions.toutes_les_lignes(base, sejour)
                 if l["produit"] == "Kardégic")
    assert ligne["dose"] == 75


def test_un_champ_de_posologie_mal_orthographie_est_refuse(base, tienam):
    """Sans ce refus, `dosee=500` passerait pour un changement de rien : la
    fonction rendrait None, l'écran dirait « posologie inchangée », et la dose
    ne changerait jamais."""
    with pytest.raises(ValueError, match="inconnu"):
        prescriptions.changer_posologie(base, tienam, a_partir_du=J4, dosee=500)
