"""Deux internes sur le même patient, le même jour.

C'est le cas ordinaire d'un service, pas un cas limite : la visite passe, un
interne remplit l'évolution du lit 3, un autre ouvre le même lit pour ajouter
une ligne. Sans garde, le second enregistrement écrase le premier — et
personne ne voit jamais que quelque chose a été perdu. C'est la seule
catégorie de bug qui détruit des données sans laisser de trace.

Ce qui est vérifié ici : le refus. Pas de fusion, pas de résolution de
conflit — juste ne pas écraser en silence.
"""

import sys

import pytest

from rea.services import evolution, sejours


def _conflit_de_version() -> type[Exception]:
    """La classe d'exception telle que la voit le code sous test.

    Le conftest recharge les modules `rea.*` à chaque fixture `base` : une
    classe importée en tête de ce fichier ne serait pas celle réellement levée,
    et `pytest.raises` ne l'attraperait pas. Le piège coûte une demi-heure à
    qui le rencontre sans le savoir.
    """
    return sys.modules["rea.db"].ConflitDeVersion

JOUR = "2026-09-08"


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-06",
                                lit_admission=3)


def _ouvrir(base, sid):
    """Ce que fait l'écran à son ouverture : lire la journée et sa version."""
    return evolution.obtenir_ou_creer(base, sid, JOUR)["version"]


def test_un_enregistrement_seul_passe(base):
    sid = _sejour(base)
    version = _ouvrir(base, sid)
    evolution.enregistrer_journee(
        base, sid, JOUR, elements={"fc": 92}, textes={"conduite": "Poursuite"},
        version_attendue=version,
    )
    assert evolution.elements_du_jour(base, sid, JOUR)["fc"] == 92


def test_le_second_interne_est_refuse_et_le_premier_est_conserve(base):
    """Le scénario complet : les deux ouvrent l'écran, le premier enregistre,
    le second aussi — et c'est le second qui doit être refusé."""
    sid = _sejour(base)
    version_interne_a = _ouvrir(base, sid)
    version_interne_b = _ouvrir(base, sid)      # même version, deux écrans

    evolution.enregistrer_journee(
        base, sid, JOUR, elements={"fc": 92},
        textes={"plan_hemodynamique": "Stable sous noradrénaline"},
        version_attendue=version_interne_a,
    )

    with pytest.raises(_conflit_de_version()):
        evolution.enregistrer_journee(
            base, sid, JOUR, elements={"fc": 120},
            textes={"plan_hemodynamique": "Choc"},
            version_attendue=version_interne_b,
        )

    # Rien de ce qu'a écrit le premier n'a bougé.
    entree = base.une_ligne(
        "SELECT plan_hemodynamique FROM evolution_jour WHERE sejour_id = ? AND date_jour = ?",
        (sid, JOUR),
    )
    assert entree["plan_hemodynamique"] == "Stable sous noradrénaline"
    assert evolution.elements_du_jour(base, sid, JOUR)["fc"] == 92


def test_le_refus_nenregistre_aucune_mesure(base):
    """Refuser à moitié serait pire que tout : les mesures ne doivent pas
    passer quand les textes sont refusés."""
    sid = _sejour(base)
    version = _ouvrir(base, sid)
    evolution.enregistrer_journee(base, sid, JOUR, elements={"fc": 92}, textes={},
                                  version_attendue=version)

    with pytest.raises(_conflit_de_version()):
        evolution.enregistrer_journee(
            base, sid, JOUR, elements={"fc": 150, "pas": 70}, textes={},
            version_attendue=version,
        )

    elements = evolution.elements_du_jour(base, sid, JOUR)
    assert elements["fc"] == 92
    assert "pas" not in elements


def test_relire_avant_de_reenregistrer_passe(base):
    """La parade que le message propose à l'utilisateur : rouvrir le jour,
    relire, puis reporter ses ajouts."""
    sid = _sejour(base)
    evolution.enregistrer_journee(base, sid, JOUR, elements={"fc": 92}, textes={},
                                  version_attendue=_ouvrir(base, sid))

    version_relue = _ouvrir(base, sid)          # l'écran est rouvert
    evolution.enregistrer_journee(base, sid, JOUR, elements={"fc": 96}, textes={},
                                  version_attendue=version_relue)
    assert evolution.elements_du_jour(base, sid, JOUR)["fc"] == 96


def test_deux_jours_differents_ne_se_genent_pas(base):
    """Chaque journée a sa ligne et sa version : remplir hier ne bloque pas
    aujourd'hui."""
    sid = _sejour(base)
    veille = "2026-09-07"
    evolution.enregistrer_journee(
        base, sid, veille, elements={"fc": 80}, textes={},
        version_attendue=evolution.obtenir_ou_creer(base, sid, veille)["version"],
    )
    evolution.enregistrer_journee(
        base, sid, JOUR, elements={"fc": 92}, textes={},
        version_attendue=_ouvrir(base, sid),
    )
    assert evolution.elements_du_jour(base, sid, veille)["fc"] == 80
    assert evolution.elements_du_jour(base, sid, JOUR)["fc"] == 92


def test_sans_version_attendue_la_garde_ne_bloque_rien(base):
    """Les écrans qui n'ont pas encore la garde continuent d'écrire : on
    n'ajoute pas un verrou là où personne ne l'a demandé."""
    sid = _sejour(base)
    _ouvrir(base, sid)
    evolution.enregistrer_journee(base, sid, JOUR, elements={"fc": 92}, textes={})
    evolution.enregistrer_journee(base, sid, JOUR, elements={"fc": 110}, textes={})
    assert evolution.elements_du_jour(base, sid, JOUR)["fc"] == 110


def test_le_message_de_conflit_dit_les_deux_versions(base):
    """Un message d'erreur qui ne dit pas ce qui s'est passé oblige à ouvrir
    le journal pour le comprendre."""
    sid = _sejour(base)
    version = _ouvrir(base, sid)
    evolution.enregistrer_journee(base, sid, JOUR, elements={}, textes={"conduite": "A"},
                                  version_attendue=version)
    with pytest.raises(_conflit_de_version()) as capture:
        evolution.enregistrer_journee(base, sid, JOUR, elements={}, textes={"conduite": "B"},
                                      version_attendue=version)
    assert capture.value.attendue == version
    assert capture.value.actuelle == version + 1
    assert "evolution_jour" in str(capture.value)
