"""Un bilan que le catalogue ne connaît pas encore (SPEC §8).

Le catalogue est du code : y ajouter la troponine demande une nouvelle version
du logiciel. Un service qui se met à doser quelque chose ne peut pas attendre
ça — il le noterait dans un commentaire libre, où le résultat ne se compare pas
d'un jour à l'autre, ne trace aucune courbe et ne sort dans aucune statistique.
"""

import pytest

from rea import analytes as cat
from rea.services import analytes_locaux, bilans, sejours

J1 = "2026-09-08"


@pytest.fixture()
def sejour(base):
    pid = sejours.creer_patient(base, matricule="M-AL", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission=J1,
                                lit_admission=7)


# -- le code ----------------------------------------------------------------

@pytest.mark.parametrize("libelle, attendu", [
    ("Troponine", "troponine"),
    ("D-dimères", "d_dimeres"),
    ("NT-proBNP", "nt_probnp"),
    ("  Ammoniémie  ", "ammoniemie"),
])
def test_le_code_se_deduit_du_libelle(libelle, attendu):
    """Sans accent : le code finit dans un export lu par un tableur dont on ne
    choisit pas l'encodage."""
    assert analytes_locaux.code_depuis_libelle(libelle) == attendu


# -- ajout ------------------------------------------------------------------

def test_un_analyte_ajoute_devient_saisissable(base):
    analytes_locaux.ajouter(base, libelle="Troponine", unite="ng/L")
    assert cat.connu("troponine")
    assert cat.analyte("troponine").libelle == "Troponine"
    assert cat.analyte("troponine").unite == "ng/L"


def test_un_analyte_ajoute_rejoint_les_bilans_non_systematiques(base):
    analytes_locaux.ajouter(base, libelle="Troponine", unite="ng/L")
    _courants, occasionnels = cat.groupes_de_saisie()
    groupe = occasionnels[-1]
    assert groupe.titre == "Autres bilans"
    assert [a.libelle for a in groupe.analytes] == ["Troponine"]


def test_sans_analyte_du_service_il_ny_a_pas_de_groupe_vide(base):
    """Un titre de groupe vide occupe une place sans rien apprendre."""
    analytes_locaux.charger_dans_le_catalogue(base)
    _courants, occasionnels = cat.groupes_de_saisie()
    assert all(g.titre != "Autres bilans" for g in occasionnels)


def test_un_code_deja_pris_est_refuse(base):
    """Deux analytes sous le même code, ce sont deux séries de valeurs
    mélangées, et rien ne permettrait ensuite de les démêler."""
    with pytest.raises(ValueError, match="existe déjà"):
        analytes_locaux.ajouter(base, libelle="CRP")
    analytes_locaux.ajouter(base, libelle="Troponine")
    with pytest.raises(ValueError, match="existe déjà"):
        analytes_locaux.ajouter(base, libelle="troponine")


def test_un_libelle_vide_est_refuse(base):
    with pytest.raises(ValueError, match="obligatoire"):
        analytes_locaux.ajouter(base, libelle="   ")


# -- ce que ça change pour un résultat --------------------------------------

def test_un_resultat_saisi_porte_le_libelle_dans_lobservation(base, sejour):
    analytes_locaux.ajouter(base, libelle="Troponine", unite="ng/L")
    bilans.enregistrer_resultats(base, sejour_id=sejour,
                                 date_heure=f"{J1}T08:00", valeurs={"troponine": 450})
    texte = bilans.texte_genere(base, sejour, J1)
    assert "Autres bilans" in texte
    assert "Troponine = 450 ng/L" in texte


def test_retirer_un_analyte_ne_perd_pas_les_valeurs_deja_mesurees(base, sejour):
    """Ce qui a été mesuré a été mesuré."""
    identifiant = analytes_locaux.ajouter(base, libelle="Troponine", unite="ng/L")
    bilans.enregistrer_resultats(base, sejour_id=sejour,
                                 date_heure=f"{J1}T08:00", valeurs={"troponine": 450})
    analytes_locaux.retirer(base, identifiant)
    assert analytes_locaux.tous(base) == []
    historique = bilans.historique_analyte(base, sejour, "troponine")
    assert [h["valeur_num"] for h in historique] == [450]


def test_un_code_inconnu_reste_lisible_au_lieu_de_tout_casser(base):
    """Une lecture qui plante fait disparaître tout l'écran, pas seulement la
    ligne fautive."""
    assert cat.analyte("code_disparu").libelle == "code_disparu"
    assert cat.connu("code_disparu") is False
