"""Chaque mode ventilatoire a ses paramètres, et rien qu'eux (SPEC §8).

Tous les champs étaient proposés quel que soit le mode : une PEP sous air
ambiant, une AI en VAC. Des cases qui n'existent pas cliniquement, et qu'un
interne de garde finit par remplir avec le paramètre d'à côté — après quoi la
valeur est en base, indiscernable d'une mesure.
"""

import re

import pytest

from rea import listes
from rea.printing import feuille
from rea.services import bilans, feuille_dossier, sejours

def _cellules(ligne) -> list[str]:
    """Le contenu des cases d'une ligne imprimée, sans son habillage."""
    return re.findall(r">([^<>]*)</div>", ligne["valeurs"].html)


AUJ = "2026-09-09"
J1 = "2026-09-08"


@pytest.fixture()
def sejour(base):
    pid = sejours.creer_patient(base, matricule="M-VENT", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission=J1,
                                lit_admission=3)


# -- ce que chaque mode déclare ---------------------------------------------

@pytest.mark.parametrize("mode, attendus", [
    ("air_ambiant", ()),
    ("lunette", ("debit_o2",)),
    ("masque", ("debit_o2",)),
    ("optiflow", ("debit_o2", "fio2")),
    ("vac", ("fio2", "pep", "fr", "vt")),
    ("vaci", ("fio2", "pep", "fr", "vt", "ai")),
    ("vs_ai", ("fio2", "pep", "ai", "vt")),
])
def test_les_parametres_de_chaque_mode(mode, attendus):
    assert listes.parametres_du_mode(mode) == attendus


def test_lair_ambiant_ne_demande_rien():
    """Ni débit, ni FiO₂, ni paramètre de ventilation : il n'y a pas de
    machine."""
    assert listes.parametres_du_mode("air_ambiant") == ()


def test_le_vac_ne_demande_pas_daide_inspiratoire():
    """En ventilation contrôlée, la machine impose tout : une aide
    inspiratoire n'y a pas de sens."""
    assert "ai" not in listes.parametres_du_mode("vac")


def test_la_vs_ai_ne_demande_pas_de_frequence_imposee():
    """En ventilation spontanée, la fréquence est celle du patient — elle se
    relève sur la pancarte, elle ne se règle pas."""
    assert "fr" not in listes.parametres_du_mode("vs_ai")


def test_loptiflow_demande_son_debit_et_sa_fio2():
    """C'est ce qui le distingue d'un masque : le débit ET la fraction
    inspirée sont réglés."""
    assert listes.parametres_du_mode("optiflow") == ("debit_o2", "fio2")


def test_un_mode_inconnu_ne_demande_rien_plutot_que_de_planter():
    assert listes.parametres_du_mode(None) == ()
    assert listes.parametres_du_mode("mode_du_futur") == ()


# -- le libellé -------------------------------------------------------------

def test_le_sigle_court_est_celui_du_service():
    """La liste déroulante montre le nom complet — un interne de première
    garde ne connaît pas encore les sigles. La feuille montre le sigle, où la
    place est comptée."""
    assert listes.libelle_mode_court("vac") == "VAC"
    assert listes.libelle_mode_court("vs_ai") == "VS-AI"
    assert listes.libelle_mode_court("optiflow") == "Optiflow"


# -- ce qui s'imprime -------------------------------------------------------

def test_la_feuille_imprime_le_sigle_pas_le_code(base, sejour):
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                   mode_ventilatoire="vs_ai", pep=6, ai=12, vt=450)
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    ligne = next(l for l in contexte["gdsVent"] if l["libelle"] == "Mode")
    assert "VS-AI" in ligne["valeurs"].html
    assert "vs_ai" not in ligne["valeurs"].html


def test_un_parametre_etranger_au_mode_nest_pas_imprime(base, sejour):
    """Une PEP sous air ambiant ne peut venir que d'une saisie antérieure au
    filtrage : elle ne doit pas ressortir comme une mesure."""
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                   mode_ventilatoire="air_ambiant", pep=8, ph=7.4)
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    pep = next(l for l in contexte["gdsVent"] if l["libelle"] == "PEP")
    assert [c for c in _cellules(pep) if c] == []
    # Le gaz du sang lui-même reste imprimé : il ne dépend d'aucun mode.
    ph = next(l for l in contexte["gdsGaz"] if l["libelle"] == "pH")
    assert "7,4" in _cellules(ph)


def test_la_ligne_dobservation_ne_reprend_que_les_parametres_du_mode(base, sejour):
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                   mode_ventilatoire="vac", pep=6, fr=18, vt=420,
                                   fio2=50, ai=99)
    texte = bilans.texte_genere(base, sejour, J1)
    assert "PEP = 6" in texte and "FR = 18" in texte
    assert "AI" not in texte          # la VAC n'a pas d'aide inspiratoire


# -- migration d'une base écrite avant les codes ----------------------------

def test_un_mode_enregistre_sous_son_libelle_est_traduit(base, sejour):
    """Sans ce rattrapage, un gaz écrit par la version précédente garderait
    « VAC » là où le programme attend « vac » : ses paramètres ne seraient plus
    reconnus, et la ligne d'observation cesserait de les afficher sans rien
    dire."""
    identifiant = bilans.enregistrer_gaz_du_sang(
        base, sejour, f"{J1}T08:00", mode_ventilatoire="vac", pep=6)
    base.executer("UPDATE gaz_du_sang SET mode_ventilatoire = 'VAC' WHERE id = ?",
                  (identifiant,))
    base._rattraper_modes_ventilatoires()
    ligne = base.une_ligne("SELECT mode_ventilatoire FROM gaz_du_sang WHERE id = ?",
                           (identifiant,))
    assert ligne["mode_ventilatoire"] == "vac"



# -- la FiO₂ et le rapport PaO₂/FiO₂ ne se contredisent jamais --------------
# Démonstration du 29 septembre : un gaz enregistré sous « VAC », code inconnu,
# ne déclarait aucun paramètre. La ligne FiO₂ restait vide, et la ligne
# PaO₂/FiO₂ juste en dessous imprimait 80, 103, 176 — calculés avec elle.

def _fio2_et_pf(base, sejour) -> tuple[list[str], list[str]]:
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    fio2 = next(l for l in contexte["gdsGaz"] if l["libelle"] == "FiO₂")
    pf = re.findall(r">([^<>]*)</div>", contexte["pfRow"].html)
    return [c for c in _cellules(fio2) if c], [c for c in pf if c]


def test_un_mode_inconnu_est_refuse(base, sejour):
    with pytest.raises(ValueError):
        bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                       mode_ventilatoire="VNI-X", pao2=80, fio2=50)


def test_un_ancien_libelle_est_enregistre_sous_son_code(base, sejour):
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                   mode_ventilatoire="VAC", pao2=80, fio2=50)
    ligne = base.une_ligne("SELECT mode_ventilatoire FROM gaz_du_sang")
    assert ligne["mode_ventilatoire"] == "vac"
    assert _fio2_et_pf(base, sejour) == (["50"], ["160"])


def test_ce_que_le_mode_ne_declare_pas_n_est_pas_enregistre(base, sejour):
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00", mode_ventilatoire="lunette",
                                   debit_o2=3, fio2=40, pep=5, pao2=70)
    ligne = base.une_ligne("SELECT * FROM gaz_du_sang")
    assert ligne["debit_o2"] == 3 and ligne["pao2"] == 70
    assert ligne["fio2"] is None and ligne["pep"] is None


def test_pas_de_rapport_pf_sans_la_fio2_imprimee(base, sejour):
    """Une FiO₂ restée en base sous lunettes (saisie antérieure au filtrage) :
    ni imprimée, ni utilisée — sur la feuille comme dans l'observation."""
    identifiant = bilans.enregistrer_gaz_du_sang(
        base, sejour, f"{J1}T08:00", mode_ventilatoire="lunette", debit_o2=3, pao2=70)
    base.executer("UPDATE gaz_du_sang SET fio2 = 40 WHERE id = ?", (identifiant,))
    assert _fio2_et_pf(base, sejour) == ([], [])
    assert "PaO₂/FiO₂" not in bilans.texte_genere(base, sejour, J1)


def test_chaque_rapport_pf_a_sa_fio2_au_dessus(base, sejour):
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T06:00",
                                   mode_ventilatoire="vac", pao2=80, fio2=50, pep=6)
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T14:00",
                                   mode_ventilatoire="optiflow", pao2=90, fio2=60, debit_o2=50)
    assert _fio2_et_pf(base, sejour) == (["50", "60"], ["160", "150"])



def test_sous_oxygene_le_mode_porte_son_debit(base, sejour):
    """« Masque 6L » : sans le débit, un masque ne dit rien de l'oxygène
    reçu — et ce gaz-là n'a pas de FiO₂ pour le dire à sa place."""
    bilans.enregistrer_gaz_du_sang(base, sejour, f"{J1}T08:00",
                                   mode_ventilatoire="masque", debit_o2=6, pao2=80)
    contexte = feuille.contexte(feuille_dossier.rassembler(base, sejour, AUJ))
    mode = next(l for l in contexte["gdsVent"] if l["libelle"] == "Mode")
    assert "Masque 6L" in _cellules(mode)
