"""Ce qu'on passe dans une perfusion, et ce qu'on ajoute dedans (SPEC §5.2).

Les deux étaient des champs libres. « SG5 », « G5% » et « sérum glucosé 5 »
désignaient le même soluté sans jamais se compter ensemble ; « KCl 2 »,
« 2 amp KCl » et « +2K » la même ampoule. Un champ libre ne se relit pas d'une
feuille à l'autre, et ce qui ne se relit pas ne se compte pas.
"""

import pytest

from rea import listes
from rea.domaine import prescription as dom
from rea.services import prescriptions, sejours


# -- composition du texte ----------------------------------------------------

def test_les_additifs_sont_groupes_derriere_un_seul_plus():
    """« + (1 NaCl + 2 KCl) » : un flacon chargé se lit d'un coup d'œil au lieu
    de s'étaler sur la largeur de la ligne."""
    assert dom.texte_additifs([("NaCl", 1), ("KCl", 2)]) == "+ (1 NaCl + 2 KCl)"


def test_un_seul_additif_garde_la_meme_forme():
    assert dom.texte_additifs([("KCl", 2)]) == "+ (2 KCl)"


def test_sans_additif_il_ny_a_pas_de_texte():
    """Un « + () » vide sur la pancarte se lit comme une omission."""
    assert dom.texte_additifs([]) is None
    assert dom.texte_additifs([("KCl", 0)]) is None
    assert dom.texte_additifs([("", 2)]) is None


def test_un_nombre_entier_ne_traine_pas_de_decimale():
    assert dom.texte_additifs([("KCl", 2.0)]) == "+ (2 KCl)"


# -- relecture ---------------------------------------------------------------

def test_le_texte_se_relit_pour_repeupler_le_formulaire():
    """Sans ce chemin de retour, modifier une perfusion obligerait à retaper
    ses additifs de mémoire — et un oubli les fait disparaître."""
    texte = dom.texte_additifs([("NaCl", 1), ("KCl", 2)])
    assert dom.analyser_additifs(texte) == [("NaCl", 1.0), ("KCl", 2.0)]


def test_lancienne_ecriture_libre_reste_lisible():
    """Les lignes écrites avant que la liste n'existe ne doivent pas être
    effacées par un analyseur trop strict."""
    assert dom.analyser_additifs("+ 3 KCl + 2 NaCl") == [("KCl", 3.0), ("NaCl", 2.0)]
    assert dom.analyser_additifs("vitamines") == [("vitamines", 1.0)]


def test_rien_a_relire_ne_rend_rien():
    assert dom.analyser_additifs(None) == []
    assert dom.analyser_additifs("   ") == []


# -- catalogue des entrées ---------------------------------------------------

@pytest.mark.parametrize("produit", [
    "Kabiven", "SmofKabiven", "Fresubin", "Sérum glucosé 5 %",
    "Sérum salé isotonique 0,9 %", "Ringer Lactate",
])
def test_les_produits_demandes_par_le_service_sont_au_catalogue(produit):
    assert produit in [e[1] for e in listes.PRODUITS_ENTREES]


@pytest.mark.parametrize("produit, attendu", [
    ("Ringer Lactate", "perfusion"),
    ("Kabiven", "nutrition_parenterale"),
    ("Fresubin", "nutrition_enterale"),
])
def test_le_catalogue_sait_si_cest_une_perfusion_ou_une_nutrition(produit, attendu):
    """Une nutrition entérale se prescrit en mL/24 h, une perfusion en cc/h :
    la case s'ouvre sur le bon type sans qu'on ait à y penser."""
    assert listes.sous_type_du_produit(produit) == attendu


def test_un_produit_hors_catalogue_ne_force_aucun_type():
    """La liste reste ouverte : un produit absent s'écrit à la main, et rien
    n'est deviné à sa place."""
    assert listes.sous_type_du_produit("Soluté du laboratoire") is None
    assert listes.sous_type_du_produit(None) is None


@pytest.mark.parametrize("additif", ["KCl", "NaCl", "Cernevit", "Phocytan", "Mg²⁺"])
def test_les_additifs_demandes_par_le_service_sont_au_catalogue(additif):
    assert additif in [e[1] for e in listes.ADDITIFS_PERFUSION]


# -- de bout en bout ---------------------------------------------------------

def test_les_additifs_suivent_la_ligne_jusqua_la_pancarte(base):
    pid = sejours.creer_patient(base, matricule="M-ADD", nom_affichage="Test",
                                date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-07",
                               lit_admission=1)
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="ENTREES", produit="Ringer Lactate",
        date_debut="2026-09-07", sous_type="perfusion", vitesse=60,
        rythme="continu", additifs=dom.texte_additifs([("NaCl", 1), ("KCl", 2)]),
    )
    ligne = prescriptions.lignes_actives_le(base, sid, "2026-09-08")[0]
    assert "+ (1 NaCl + 2 KCl)" in dom.libelle_ligne(ligne, "2026-09-08")
