"""Actes de réanimation : transfusion, ALR, syndrome radiologique, antidatage.

Ce qui est vérifié ici, c'est surtout que les saisies restent **fermées** là
où elles doivent l'être. « alvéolaire », « alvéolaires » et « sd alvéolaire »
décrivaient la même radio sans jamais se compter ensemble ; un produit sanguin
écrit à la main ne se retrouve pas dans une revue de morbidité.
"""

import pytest

from rea import listes
from rea.rendu import feuille
from rea.services import dispositifs, explorations, feuille_dossier, sejours

AUJ = "2026-09-08"
J1 = "2026-09-07"
J2 = "2026-09-06"


@pytest.fixture()
def sejour(base):
    pid = sejours.creer_patient(base, matricule="M-ACT", nom_affichage="Test",
                                date_naissance="1975-05-05", sexe="M")
    return sejours.creer_sejour(base, patient_id=pid, date_admission=J2,
                                lit_admission=2, poids_kg=70)


def _dossier(base, sid, jour=AUJ):
    return feuille_dossier.rassembler(base, sid, jour)


# -- antidater ---------------------------------------------------------------

def test_un_acte_de_la_nuit_se_range_a_son_heure(base, sejour):
    """Un acte fait à 3 h et saisi à la relève appartient à la nuit, pas au
    jour de la frappe."""
    explorations.enregistrer(base, sejour_id=sejour, date_heure=f"{J1}T03:00",
                             type_="radio_thorax", conclusion="Contrôle du drain")
    ligne = explorations.du_sejour(base, sejour)[0]
    assert ligne["date_heure"].startswith(J1)
    assert "03:00" in ligne["date_heure"]


# -- radiographie thoracique -------------------------------------------------

def test_le_syndrome_radiologique_est_une_liste_fermee():
    options = {c["cle"]: c for c in listes.champs_exploration("radio_thorax")}
    assert options["syndrome"]["type"] == "liste"
    for attendu in ("Syndrome alvéolaire", "Syndrome interstitiel", "Opacité",
                    "Clarté (pneumothorax)"):
        assert attendu in options["syndrome"]["options"]
    assert options["localisation"]["options"] == (
        "Droit", "Gauche", "Bilatéral", "Diffus")


def test_le_syndrome_et_sa_localisation_se_relisent_ensemble(base, sejour):
    explorations.enregistrer(
        base, sejour_id=sejour, date_heure=f"{J1}T08:00", type_="radio_thorax",
        valeurs={"syndrome": "Syndrome alvéolaire", "localisation": "Droit"},
    )
    ligne = explorations.du_sejour(base, sejour)[0]
    texte = explorations.texte_exploration(base, ligne)
    assert "Syndrome alvéolaire" in texte
    assert "Droit" in texte


# -- transfusion -------------------------------------------------------------

def test_la_transfusion_note_son_produit_ses_poches_et_son_heure(base, sejour):
    explorations.enregistrer(
        base, sejour_id=sejour, date_heure=f"{J1}T14:30", type_="transfusion",
        valeurs={"produit": "CGR (culot globulaire)", "nb_poches": 2,
                 "complication": "Absent"},
    )
    ligne = explorations.du_sejour(base, sejour)[0]
    texte = explorations.texte_exploration(base, ligne)
    assert "CGR" in texte and "2" in texte
    assert "14:30" in ligne["date_heure"]


def test_une_complication_transfusionnelle_se_precise_en_texte(base, sejour):
    explorations.enregistrer(
        base, sejour_id=sejour, date_heure=f"{J1}T14:30", type_="transfusion",
        valeurs={"produit": "PFC (plasma frais congelé)", "nb_poches": 1,
                 "complication": "Présent",
                 "complication_detail": "Frissons et fièvre à 39 °C"},
    )
    texte = explorations.texte_exploration(base, explorations.du_sejour(base, sejour)[0])
    assert "Frissons et fièvre à 39 °C" in texte


def test_les_produits_sanguins_sont_une_liste_fermee():
    """Un produit écrit à la main ne se retrouve pas dans une revue de
    morbidité."""
    produit = next(c for c in listes.champs_exploration("transfusion")
                   if c["cle"] == "produit")
    assert produit["type"] == "liste"
    for attendu in ("CGR", "PFC", "CUP"):
        assert any(attendu in o for o in produit["options"])


# -- anesthésie locorégionale ------------------------------------------------

def test_un_bloc_en_une_fois_se_note_comme_acte_avec_sa_dose(base, sejour):
    """Il n'est pas laissé en place : ce n'est pas un dispositif."""
    explorations.enregistrer(
        base, sejour_id=sejour, date_heure=f"{J1}T10:00", type_="alr",
        valeurs={"technique": "Bloc serratus", "cote": "Droit",
                 "anesthesique": "Ropivacaïne 0,2 %", "dose": 75, "volume": 20},
    )
    texte = explorations.texte_exploration(base, explorations.du_sejour(base, sejour)[0])
    assert "Bloc serratus" in texte
    assert "75" in texte


def test_une_peridurale_apparait_dans_le_bloc_pse_avec_son_anesthesique(base, sejour):
    """Ce qui coule en continu est une consigne infirmière : ça doit être là où
    les seringues se règlent, pas seulement dans la case des dispositifs."""
    dispositifs.poser(
        base, sejour_id=sejour, type_="peridurale", date_pose=J1,
        site="Thoracique haute (T4-T6)",
        details={"molecules": "Ropivacaïne 0,2 %", "vitesse": 6},
    )
    lignes = feuille.contexte(_dossier(base, sejour))["pseRows"]
    ligne = next(l for l in lignes if l["produit"] and "Ropivacaïne" in str(l["produit"].html
                 if hasattr(l["produit"], "html") else l["produit"]))
    assert "péridurale" in ligne["produit"].html
    assert ligne["dose"] == "6 cc/h"


def test_la_sedation_reste_dans_le_bloc_pse(base, sejour):
    """Le cas d'origine ne doit pas se perdre en généralisant."""
    dispositifs.poser(base, sejour_id=sejour, type_="sedation", date_pose=J1,
                      details={"molecules": "Midazolam", "vitesse": 4})
    lignes = feuille.contexte(_dossier(base, sejour))["pseRows"]
    ligne = next(l for l in lignes if l["produit"] and "Midazolam" in str(
        l["produit"].html if hasattr(l["produit"], "html") else l["produit"]))
    assert "sédation" in ligne["produit"].html


def test_un_dispositif_qui_ne_coule_pas_ne_va_pas_en_pse(base, sejour):
    dispositifs.poser(base, sejour_id=sejour, type_="kt_central", date_pose=J1,
                      site="Jugulaire interne droite", details={"nb_voies": 3})
    lignes = feuille.contexte(_dossier(base, sejour))["pseRows"]
    remplies = [l for l in lignes if l["produit"]]
    assert remplies == []


def test_la_ligne_pse_ne_repete_pas_le_site(base, sejour):
    """Il est déjà sur le bandeau des abords, en haut de la même page.
    L'écrire deux fois faisait passer la ligne sur deux hauteurs et cassait la
    grille des seringues."""
    dispositifs.poser(
        base, sejour_id=sejour, type_="peridurale", date_pose=J1,
        site="Thoracique haute (T4-T6)",
        details={"molecules": "Ropivacaïne 0,2 %", "vitesse": 6},
    )
    contexte = feuille.contexte(_dossier(base, sejour))
    ligne = next(l for l in contexte["pseRows"] if l["produit"])
    assert ligne["produit"].html.startswith("Ropivacaïne 0,2 % <span")
    assert "T4-T6" not in ligne["produit"].html
    # Mais le site reste lisible là où il répond à « où » : les abords.
    assert "T4-T6" in " ".join(a["texte"] for a in contexte["abords"])
