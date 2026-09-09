"""Les avis demandés aux autres spécialités (SPEC §7).

« Refaire la TDM à 48 h » est une consigne datée et signée, et c'est sur elle
qu'on décide trois jours plus tard. Écrite dans le texte libre du plan
infectieux, elle disparaissait à la première réécriture du plan — et personne
ne savait plus qui avait dit quoi, ni quand.
"""

import pytest

from rea.domaine import avis as dom
from rea.rendu import feuille
from rea.services import avis, feuille_dossier, sejours

AUJ = "2026-09-10"


@pytest.fixture()
def sejour(base):
    pid = sejours.creer_patient(base, matricule="M-AV", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-08",
                                lit_admission=6)


# -- la forme demandée par le service ---------------------------------------

def test_la_ligne_dun_avis_suit_la_forme_du_service():
    ligne = dom.ligne_avis({
        "specialite": "ccvt", "date_avis": "2026-09-09", "nom": "X",
        "grade": "resident",
        "texte": "Pas d'indication chirurgicale , adresser C.externe",
    })
    assert ligne == ("Avis CCVT (09/09) : Rsdt X : "
                     "Pas d'indication chirurgicale , adresser C.externe")


def test_un_avis_de_senior_se_distingue_dun_avis_de_resident():
    """Les deux n'engagent pas la même chose, et c'est sur cette ligne qu'on
    décide de rappeler ou non le service."""
    ligne = dom.ligne_avis({
        "specialite": "neurochirurgie", "date_avis": "2026-09-10", "nom": "X",
        "grade": "senior", "texte": "Refaire TDM après 48H",
    })
    assert ligne == "Avis Neurochir (10/09) : Dr X : Refaire TDM après 48H"


def test_un_avis_sans_nom_reste_lisible():
    ligne = dom.ligne_avis({"specialite": "orthopedie", "date_avis": "2026-09-09",
                            "texte": "Immobilisation 6 semaines"})
    assert ligne == "Avis Orthopédie (09/09) : Immobilisation 6 semaines"


# -- ce qui est conservé -----------------------------------------------------

def test_un_second_avis_de_la_meme_specialite_nefface_pas_le_premier(base, sejour):
    """C'est la suite des avis qui raconte l'évolution d'une décision
    chirurgicale : le second ne se comprend souvent qu'à la lumière du
    premier."""
    avis.demander(base, sejour_id=sejour, specialite="neurochirurgie",
                  date_avis="2026-09-08", nom="A", grade="senior",
                  texte="Abstention, surveiller")
    avis.demander(base, sejour_id=sejour, specialite="neurochirurgie",
                  date_avis="2026-09-10", nom="B", grade="senior",
                  texte="Indication opératoire retenue")
    lignes = avis.lignes_imprimees(base, sejour)
    assert len(lignes) == 2
    assert "Abstention, surveiller" in lignes[0]
    assert "Indication opératoire retenue" in lignes[1]


def test_les_avis_sont_rendus_dans_lordre_chronologique(base, sejour):
    """Une suite de décisions se lit dans le sens où elle s'est produite."""
    for jour, texte in (("2026-09-10", "troisième"), ("2026-09-08", "premier"),
                        ("2026-09-09", "deuxième")):
        avis.demander(base, sejour_id=sejour, specialite="ccvt",
                      date_avis=jour, texte=texte)
    lignes = avis.lignes_imprimees(base, sejour)
    assert [l.split(" : ")[-1] for l in lignes] == ["premier", "deuxième", "troisième"]


def test_un_avis_saisi_par_erreur_seffce_logiquement(base, sejour):
    """Ce qui a été écrit sur un dossier y reste traçable."""
    identifiant = avis.demander(base, sejour_id=sejour, specialite="urologie",
                                date_avis=AUJ, texte="Mauvais patient")
    avis.supprimer(base, identifiant)
    assert avis.du_sejour(base, sejour) == []
    reste = base.une_ligne("SELECT supprime FROM avis_specialise WHERE id = ?",
                           (identifiant,))
    assert reste["supprime"] == 1


def test_un_avis_peut_etre_antidate(base, sejour):
    """Donné hier soir, saisi ce matin : c'est sa date qui compte."""
    avis.demander(base, sejour_id=sejour, specialite="ccvt",
                  date_avis="2026-09-09", texte="Vu cette nuit")
    assert avis.du_sejour(base, sejour)[0]["date_avis"] == "2026-09-09"


# -- sur la feuille imprimée -------------------------------------------------

def test_les_avis_sont_imprimes_sur_la_feuille(base, sejour):
    avis.demander(base, sejour_id=sejour, specialite="ccvt", date_avis="2026-09-09",
                  nom="X", grade="resident", texte="Pas d'indication chirurgicale")
    avis.demander(base, sejour_id=sejour, specialite="neurochirurgie",
                  date_avis="2026-09-10", nom="Y", grade="senior",
                  texte="Refaire TDM après 48H")
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    html = contexte["avisRows"].html
    assert "Avis CCVT (09/09) : Rsdt X" in html
    assert "Avis Neurochir (10/09) : Dr Y" in html
    assert html.index("CCVT") < html.index("Neurochir")     # chronologique


def test_sans_avis_le_bloc_reste_du_papier_regle(base, sejour):
    """La conduite à tenir s'y écrit à la main : rien ne doit occuper la
    place pour rien."""
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    assert contexte["avisRows"].html == ""
