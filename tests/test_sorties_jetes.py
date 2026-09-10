"""Les jetés — ce qui est recueilli puis jeté au lieu d'être réinjecté.

Le liquide gastrique aspiré, avant tout. Un patient sous sonde gastrique en
perd huit cents millilitres par jour sans que rien ne l'écrive : sa diurèse
est correcte, ses drains ne donnent pas, et le bilan hydrique le déclare en
excès de deux litres alors qu'il se déshydrate (demande du service,
10 septembre).

Trois choses à tenir, et chacune casse le bilan à sa façon :

* les jetés **entrent dans le total des pertes**, sinon la ligne n'est que
  décorative ;
* une case vide vaut zéro **pour eux seulement** — la plupart des patients
  n'ont rien à jeter, alors que la diurèse est mesurée chez tout le monde et
  qu'un bilan sans elle n'existe pas ;
* la somme de la journée est proposée au médecin, jamais écrite à sa place :
  un relevé à trous n'est pas une mesure des 24 h.
"""

import importlib

import pytest


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _sejour(base, poids=70.0):
    sejours = _services("sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1)
    base.mettre_a_jour("sejour", sid, {"poids_kg": poids})
    return sid


# -- le domaine -------------------------------------------------------------

def test_les_jetes_entrent_dans_le_total_des_pertes():
    dom = importlib.import_module("rea.domaine.prescription")
    sans = dom.bilan_hydrique([], diurese_ml=1000, poids_kg=70,
                              temperature_c=37.0, date_jour="2026-09-01")
    avec = dom.bilan_hydrique([], diurese_ml=1000, jetes_ml=800, poids_kg=70,
                              temperature_c=37.0, date_jour="2026-09-01")
    assert avec.sorties_ml == sans.sorties_ml + 800
    # Et le net suit : c'est tout l'objet de la ligne.
    assert avec.net_ml == sans.net_ml - 800


def test_des_jetes_absents_ne_privent_pas_de_bilan():
    """La plupart des patients n'ont rien à jeter. Exiger la case priverait
    de bilan les trois quarts du service."""
    dom = importlib.import_module("rea.domaine.prescription")
    bilan = dom.bilan_hydrique([], diurese_ml=1000, poids_kg=70,
                               temperature_c=37.0, date_jour="2026-09-01")
    assert bilan.jetes_ml is None
    assert bilan.net_ml is not None


def test_une_diurese_absente_prive_de_bilan_meme_avec_des_jetes():
    """L'asymétrie est voulue : la diurèse est mesurée chez tout le monde."""
    dom = importlib.import_module("rea.domaine.prescription")
    bilan = dom.bilan_hydrique([], diurese_ml=None, jetes_ml=800, poids_kg=70,
                               temperature_c=37.0, date_jour="2026-09-01")
    assert bilan.net_ml is None
    assert "diurèse" in bilan.motif_indisponible


# -- le relevé horaire ------------------------------------------------------

def test_le_total_du_jour_additionne_les_heures(base):
    constantes = _services("constantes")
    sid = _sejour(base)
    for heure, volume in ((8, 120.0), (9, 80.0), (10, 200.0)):
        constantes.enregistrer(base, sid, "2026-09-09", heure, {"jetes": volume})
    assert constantes.total_du_jour(base, sid, "2026-09-09", "jetes") == 400.0
    assert constantes.heures_relevees(base, sid, "2026-09-09", "jetes") == 3


def test_rien_de_releve_n_est_pas_zero(base):
    """None et 0 ne disent pas la même chose, et l'écart se paie dans le
    bilan : « rien de relevé » n'est pas « rien de perdu »."""
    constantes = _services("constantes")
    sid = _sejour(base)
    assert constantes.total_du_jour(base, sid, "2026-09-09", "jetes") is None
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"jetes": 0.0})
    assert constantes.total_du_jour(base, sid, "2026-09-09", "jetes") == 0.0


def test_on_refuse_de_sommer_ce_qui_ne_se_somme_pas(base):
    """La somme des températures d'une journée n'est pas une température."""
    constantes = _services("constantes")
    sid = _sejour(base)
    with pytest.raises(ValueError):
        constantes.total_du_jour(base, sid, "2026-09-09", "temperature")


def test_les_jetes_sont_une_sortie_pas_une_constante_vitale(base):
    constantes = _services("constantes")
    assert "jetes" in [c for c, _l, _u in constantes.SORTIES]
    assert "jetes" not in [c for c, _l, _u in constantes.VITALES]
    assert "jetes" in constantes.CLES_SOMMABLES
    # Les vitales ne s'additionnent jamais.
    for cle, _l, _u in constantes.VITALES:
        assert cle not in constantes.CLES_SOMMABLES


# -- le chaînage jusqu'au bilan --------------------------------------------

def test_le_bilan_du_service_lit_les_jetes_saisis_dans_l_evolution(base):
    evolution = _services("evolution")
    sid = _sejour(base)
    evolution.enregistrer_elements(base, sid, "2026-09-09", {
        "diurese_24h": 1000.0, "temperature": 37.0,
    })
    sans = evolution.bilan_hydrique(base, sid, "2026-09-09")
    evolution.enregistrer_elements(base, sid, "2026-09-09", {"jetes_24h": 800.0})
    avec = evolution.bilan_hydrique(base, sid, "2026-09-09")
    assert avec.jetes_ml == 800.0
    assert avec.sorties_ml == sans.sorties_ml + 800


def test_les_jetes_ont_leur_ligne_sur_la_feuille_imprimee():
    referentiels = importlib.import_module("rea.referentiels")
    lignes = referentiels.charger("feuille_lignes")["sorties_drains"]
    codes = [c for c, _l in lignes]
    assert "jetes" in codes
    # Avant le total des pertes, qui ferme le bloc.
    assert codes.index("jetes") < codes.index("total_pertes")


def test_les_jetes_ont_leur_case_dans_le_plan_hemodynamique():
    referentiels = importlib.import_module("rea.referentiels")
    hemo = referentiels.charger("elements_plan")["hemodynamique"]
    codes = [c[0] for c in hemo]
    assert "jetes_24h" in codes
    assert codes.index("jetes_24h") == codes.index("diurese_24h") + 1
