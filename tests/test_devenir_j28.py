"""Le devenir à J28 : saisi quand il faut le vérifier, déduit quand on le sait.

Audit du 27 septembre : la mortalité à J28 était calculée sur un champ
qu'aucun écran ne permettait de remplir. Et un décès après la sortie,
une fois saisi, aurait été compté comme un décès **en réanimation**.
"""

from datetime import date

import pytest

from rea.models import devenir
from rea.services import croisements, scores, sejours
from rea.services import statistiques as stats

AUJ = date(2026, 9, 27)


def _s(**champs):
    return {"date_admission": "2026-08-01", **champs}


@pytest.mark.parametrize("sejour, attendu", [
    (_s(date_sortie="2026-08-10T12:00", mode_sortie="deces"), "decede"),
    (_s(date_sortie="2026-09-15T12:00", mode_sortie="deces"), "vivant"),   # mort après J28
    (_s(date_sortie=None), "vivant"),                                       # encore là à J28
    (_s(date_sortie="2026-09-05T12:00", mode_sortie="domicile"), "vivant"), # sorti après J28
    (_s(date_sortie="2026-08-10T12:00", mode_sortie="domicile"), None),     # à vérifier
    (_s(date_sortie="2026-08-10T12:00", mode_sortie="domicile",
        statut_j28="perdu_de_vue"), "perdu_de_vue"),
])
def test_statut_deduit_ou_saisi(sejour, attendu):
    assert devenir.statut_j28(sejour, AUJ) == attendu


def test_seul_le_sorti_vivant_avant_j28_est_a_relancer():
    assert devenir.a_relancer(_s(date_sortie="2026-08-10T12:00", mode_sortie="domicile"), AUJ)
    assert not devenir.a_relancer(_s(date_sortie="2026-08-10T12:00", mode_sortie="deces"), AUJ)
    # J28 pas encore atteint : rien à vérifier aujourd'hui.
    assert not devenir.a_relancer({"date_admission": "2026-09-20",
                                   "date_sortie": "2026-09-22T12:00"}, AUJ)


def _sejour(base, n, **sortie):
    pid = sejours.creer_patient(base, matricule=f"J{n}", nom_affichage="P",
                                date_naissance="1960-01-01", sexe="M")
    sid = sejours.creer_sejour(base, patient_id=pid, lit_admission=1 + n,
                               date_admission="2026-08-01")
    if sortie:
        sejours.cloturer_sejour(base, sid, **sortie)
    return sid


def test_noter_le_statut_et_le_retrouver(base):
    sid = _sejour(base, 1, date_heure_sortie="2026-08-10T12:00", mode_sortie="domicile")
    assert [s["id"] for s in stats.a_relancer_j28(stats.cohorte(base))] == [sid]
    sejours.noter_statut_j28(base, sid, statut="decede", date_statut="2026-09-01")
    assert stats.a_relancer_j28(stats.cohorte(base)) == []
    with pytest.raises(ValueError):
        sejours.noter_statut_j28(base, sid, statut="inconnu")


def test_un_deces_apres_la_sortie_n_est_pas_un_deces_en_reanimation(base):
    sid = _sejour(base, 2, date_heure_sortie="2026-08-10T12:00", mode_sortie="domicile")
    sejours.noter_statut_j28(base, sid, statut="decede")
    cohorte = stats.cohorte(base)
    assert stats.mortalite(base, cohorte)["deces"] == 0          # en réanimation
    assert croisements.valeur_resultat(base, cohorte[0], "deces_j28") is True


def test_la_mortalite_a_j28_compte_le_deces_en_reanimation_sans_saisie(base):
    _sejour(base, 3, date_heure_sortie="2026-08-05T12:00", mode_sortie="deces")
    cohorte = stats.cohorte(base)
    assert croisements.valeur_resultat(base, cohorte[0], "deces_j28") is True


def test_jours_sans_ventilation_d_un_deces_apres_j28(base):
    """Décédé au 45e jour : vivant à J28, ses jours sans ventilation se
    comptent (Schoenfeld 2002) — ils ne valent pas zéro."""
    sid = _sejour(base, 4, date_heure_sortie="2026-09-15T12:00", mode_sortie="deces")
    assert scores.jours_sans_ventilation(base, sid) == 28
