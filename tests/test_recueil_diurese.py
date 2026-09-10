"""Des niveaux lus dans un sac, une diurèse (SPEC §5.8).

L'infirmier ne mesure pas ce qui sort : il lit **ce que le sac contient**, et
il le jette quand il est presque plein ou pour ne pas perdre le compte
(pratique du service, 10 septembre). Le logiciel additionnait ces cases —
faux deux fois, et les deux erreurs vont dans le sens qui rassure.

Chaque test ici tient un chiffre qu'un médecin lirait, et chacun serait faux
sans lui.
"""

import importlib
from datetime import datetime, timedelta

import pytest


def _dom():
    return importlib.import_module("rea.domaine.recueil")


def _releves(*paires, depart=datetime(2026, 9, 9, 8)):
    """(niveau, jeté) heure par heure à partir de 8 h."""
    recueil = _dom()
    return [
        recueil.Releve(instant=depart + timedelta(hours=i), niveau_ml=float(n),
                       sac_jete=jete)
        for i, (n, jete) in enumerate(paires)
    ]


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _sejour(base):
    sejours = _services("sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1)
    base.mettre_a_jour("sejour", sid, {"poids_kg": 70.0})
    return sid


# -- l'erreur qu'on corrige ------------------------------------------------

def test_additionner_les_niveaux_donnerait_six_fois_trop():
    """Le chiffre qui a motivé toute cette reprise.

    Douze relevés d'un patient qui fait 100 mL/h : il a produit 1 200 mL, et
    la somme des cases en annonce 7 800. L'erreur grandit avec le nombre
    d'heures relevées — l'équipe la plus consciencieuse fausserait le plus le
    bilan.
    """
    recueil = _dom()
    niveaux = [(100 * i, False) for i in range(1, 13)]
    calcule = recueil.total(
        recueil.sorties(_releves(*niveaux)),
        datetime(2026, 9, 9, 7), datetime(2026, 9, 10, 7),
    )
    assert sum(n for n, _j in niveaux) == 7800        # ce que faisait l'ancien code
    assert calcule.volume_ml == 1100                  # 11 différences de 100
    # La première heure n'est pas comptée : elle n'a rien à quoi se comparer.
    assert calcule.heures_sans_reference == 1


def test_le_premier_releve_n_est_pas_une_sortie():
    """Le sac contenait déjà quelque chose. L'attribuer à l'heure où on a
    commencé à regarder inventerait une diurèse."""
    recueil = _dom()
    sorties = recueil.sorties(_releves((300, False), (400, False)))
    assert sorties[0].volume_ml is None
    assert sorties[1].volume_ml == 100


# -- le sac jeté -----------------------------------------------------------

def test_un_sac_jete_fait_repartir_le_compte_de_zero():
    """Sans le drapeau, 900 puis 40 se lirait comme une diurèse effondrée —
    et la journée perdrait les 900 mL du sac."""
    recueil = _dom()
    sorties = recueil.sorties(_releves(
        (500, False), (900, True), (40, False), (180, False),
    ))
    assert [s.volume_ml for s in sorties] == [None, 400, 40, 140]


def test_rien_n_est_perdu_au_changement_de_sac():
    """Le même patient, le même débit, avec et sans changement de sac : le
    total de la journée doit être identique. C'est tout l'objet du drapeau."""
    recueil = _dom()
    fenetre = (datetime(2026, 9, 9, 7), datetime(2026, 9, 10, 7))
    sans = recueil.total(recueil.sorties(_releves(
        (100, False), (200, False), (300, False), (400, False),
    )), *fenetre)
    avec = recueil.total(recueil.sorties(_releves(
        (100, False), (200, True), (100, False), (200, False),
    )), *fenetre)
    assert sans.volume_ml == avec.volume_ml == 300


def test_un_niveau_qui_baisse_sans_sac_jete_est_signale_pas_soustrait():
    """Quelqu'un a vidé le sac sans le dire. Compter −860 retrancherait de la
    journée une urine qui a bien été produite."""
    recueil = _dom()
    sorties = recueil.sorties(_releves((900, False), (40, False)))
    assert sorties[1].volume_ml == 40
    assert "sans sac déclaré jeté" in sorties[1].anomalie


# -- la journée d'infirmerie ------------------------------------------------

def test_la_nuit_ne_se_compare_pas_a_l_envers(base):
    """23 h puis 1 h : sans horodatage réel, la soustraction se ferait dans le
    mauvais sens et la diurèse de la nuit serait négative."""
    constantes = _services("constantes")
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 23, {"diurese": 400.0})
    constantes.enregistrer(base, sid, "2026-09-09", 1, {"diurese": 550.0})
    sorties = constantes.sorties_du_jour(base, sid, "2026-09-09", "diurese")
    assert sorties[1].volume_ml == 150


def test_la_premiere_heure_du_jour_se_compare_a_la_veille_au_soir(base):
    """Coupé à 7 h, le calcul perdrait une heure sur vingt-quatre, tous les
    jours."""
    constantes = _services("constantes")
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 6, {"diurese": 600.0})
    constantes.enregistrer(base, sid, "2026-09-10", 7, {"diurese": 700.0})
    sorties = constantes.sorties_du_jour(base, sid, "2026-09-10", "diurese")
    assert sorties[7].volume_ml == 100


def test_le_sac_jete_a_8h_ne_donne_pas_la_nuit_a_la_journee_du_matin(base):
    """« À 8 h on jette celui de la nuit. » Attribuer le sac entier au jour du
    changement donnerait au 10 l'urine du 9 — un bilan faux les deux jours.
    En comptant heure par heure, chaque heure reste dans sa journée."""
    constantes = _services("constantes")
    sid = _sejour(base)
    # La nuit du 9 : le sac se remplit de 200 à 1 000.
    for heure, niveau in ((20, 200.0), (23, 500.0), (3, 800.0), (6, 1000.0)):
        constantes.enregistrer(base, sid, "2026-09-09", heure, {"diurese": niveau})
    # Le 10 à 8 h : dernier niveau 1 100, puis on jette et on repart.
    constantes.enregistrer(base, sid, "2026-09-10", 8, {"diurese": 1100.0},
                           sacs_jetes={"diurese"})
    constantes.enregistrer(base, sid, "2026-09-10", 9, {"diurese": 90.0})

    veille = constantes.total_du_jour(base, sid, "2026-09-09", "diurese")
    matin = constantes.total_du_jour(base, sid, "2026-09-10", "diurese")
    assert veille.volume_ml == 800        # 200 → 1 000 pendant la nuit du 9
    assert matin.volume_ml == 190         # 1 000 → 1 100, puis 0 → 90
    # Et surtout : le sac de 1 100 mL n'est pas versé en bloc au 10.
    assert matin.volume_ml < 1100


# -- les garde-fous --------------------------------------------------------

def test_on_refuse_de_cumuler_ce_qui_n_est_pas_un_recueil(base):
    """La somme des températures d'une journée n'est pas une température."""
    constantes = _services("constantes")
    sid = _sejour(base)
    with pytest.raises(ValueError):
        constantes.total_du_jour(base, sid, "2026-09-09", "temperature")


def test_rien_de_releve_ne_donne_pas_zero(base):
    """None et 0 ne disent pas la même chose : « rien de relevé » n'est pas
    « rien de perdu »."""
    constantes = _services("constantes")
    sid = _sejour(base)
    assert constantes.total_du_jour(base, sid, "2026-09-09", "diurese").volume_ml is None


def test_le_total_dit_ce_qui_lui_manque():
    """Un total amputé qui se présente comme complet est pire qu'un total
    absent : le médecin le recopie."""
    recueil = _dom()
    calcule = recueil.total(
        recueil.sorties(_releves((900, False), (40, False), (120, False))),
        datetime(2026, 9, 9, 7), datetime(2026, 9, 10, 7),
    )
    assert not calcule.complet
    assert calcule.anomalies


def test_le_niveau_saisi_est_conserve_tel_quel(base):
    """L'infirmier doit pouvoir se relire : la case garde ce qu'il a écrit,
    le volume est calculé à côté."""
    constantes = _services("constantes")
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"diurese": 120.0})
    constantes.enregistrer(base, sid, "2026-09-09", 9, {"diurese": 210.0})
    grille = constantes.du_jour(base, sid, "2026-09-09")
    assert grille[9]["diurese"] == 210.0            # le niveau, pas 90
    sorties = constantes.sorties_du_jour(base, sid, "2026-09-09", "diurese")
    assert sorties[9].volume_ml == 90.0             # le volume, calculé


def test_le_drapeau_du_sac_jete_se_decoche(base):
    """Une case cochée par erreur doit pouvoir se décocher, sinon le compte
    reste faux pour toujours."""
    constantes = _services("constantes")
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"diurese": 500.0},
                           sacs_jetes={"diurese"})
    assert (8, "diurese") in constantes.sacs_jetes_du_jour(base, sid, "2026-09-09")
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"diurese": 500.0})
    assert (8, "diurese") not in constantes.sacs_jetes_du_jour(base, sid, "2026-09-09")


# -- le double comptage retiré ---------------------------------------------

def test_le_bilan_ne_compte_plus_les_jetes_a_part():
    """Ce que le sac a recueilli **est** la diurèse. Le recompter sous le nom
    de « jetés » doublait l'urine du patient dans le total des pertes."""
    dom = importlib.import_module("rea.domaine.prescription")
    bilan = dom.bilan_hydrique([], diurese_ml=1000, poids_kg=70,
                               temperature_c=37.0, date_jour="2026-09-01")
    assert not hasattr(bilan, "jetes_ml")
    assert bilan.sorties_ml == 1000 + bilan.pertes_insensibles_ml


def test_plus_aucune_case_jetes_dans_les_referentiels():
    referentiels = importlib.import_module("rea.referentiels")
    hemo = referentiels.charger("elements_plan")["hemodynamique"]
    assert "jetes_24h" not in [c[0] for c in hemo]
    lignes = referentiels.charger("feuille_lignes")["sorties_drains"]
    assert "jetes" not in [c for c, _l in lignes]
