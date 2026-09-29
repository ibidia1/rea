"""Précision des chiffres, suivi dans le temps, qualité des données.

Demande du service, 27 septembre : « bien utiliser les statistiques et
profiter des données ». Les calculs sont vérifiés contre des valeurs publiées.
"""

import pytest

from rea.models import inference
from rea.services import croisements, dispositifs, scores, sejours
from rea.services import statistiques as stats


# -- les outils, contre des valeurs de référence ----------------------------

def test_wilson_valeurs_de_reference():
    """3/10 : 10,8 %–60,3 % (Newcombe, Stat Med 1998, tableau I)."""
    ic = inference.wilson(3, 10)
    assert ic.bas == pytest.approx(0.1078, abs=1e-3)
    assert ic.haut == pytest.approx(0.6032, abs=1e-3)
    # Zéro événement ne donne pas un intervalle nul.
    assert inference.wilson(0, 8).haut > 0.3


@pytest.mark.parametrize("k, bas, haut", [
    (0, 0.0, 3.689), (1, 0.0253, 5.572), (5, 1.623, 11.668), (10, 4.795, 18.390),
])
def test_poisson_exact_valeurs_tabulees(k, bas, haut):
    b, h = inference.poisson_exact(k)
    assert b == pytest.approx(bas, abs=2e-3)
    assert h == pytest.approx(haut, abs=2e-3)


def test_smr_et_son_intervalle():
    ic = inference.rapport_standardise(12, 10.0)
    assert ic.valeur == pytest.approx(1.2)
    assert ic.bas < 1 < ic.haut          # compatible avec « comme prévu »


def test_kaplan_meier_et_censure():
    km = inference.kaplan_meier([(1, True), (2, True), (3, False), (4, True), (5, False)])
    assert km.survie == pytest.approx([0.8, 0.6, 0.3])
    assert km.mediane == 4
    # Si la moitié ne décroche jamais, la médiane n'est pas estimable.
    assert inference.kaplan_meier([(2, True), (9, False), (9, False)]).mediane is None


def test_auroc():
    assert inference.auroc([0.9, 0.8], [0.1, 0.2]).valeur == 1.0
    assert inference.auroc([0.5], [0.5]).valeur == 0.5


def test_carte_p_signale_un_mois_hors_limites():
    periodes = [(f"2026-{m:02d}", 20, 4) for m in range(1, 9)] + [("2026-09", 20, 16)]
    centre, points = inference.carte_p(periodes)
    assert points[-1].signal == "hors des limites"
    assert 0.2 < centre < 0.3


def test_carte_p_ne_signale_pas_le_bruit():
    periodes = [(f"m{i}", 10, e) for i, e in enumerate((2, 3, 1, 2, 4, 2, 3, 1, 2, 3))]
    _centre, points = inference.carte_p(periodes)
    assert not any(p.signal for p in points)


# -- les indicateurs du service -----------------------------------------------

def _sejour(base, n, *, admission="2026-03-10", sortie=None, mode="domicile"):
    pid = sejours.creer_patient(base, matricule=f"R-{n}", nom_affichage="Patient",
                                date_naissance="1960-01-01", sexe="M")
    sid = sejours.creer_sejour(base, patient_id=pid, lit_admission=1 + n % 12,
                               date_admission=admission)
    if sortie:
        sejours.cloturer_sejour(base, sid, date_heure_sortie=f"{sortie}T12:00",
                                mode_sortie=mode)
    return sid


def test_extubation_accidentelle_et_echec_d_extubation(base):
    sid = _sejour(base, 1, sortie="2026-03-30")
    i1 = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-03-10")
    dispositifs.retirer(base, i1, date_retrait="2026-03-15", motif_retrait="programmee")
    i2 = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-03-16")
    dispositifs.retirer(base, i2, date_retrait="2026-03-20", motif_retrait="accidentelle")
    v = stats.indicateurs_ventilation(base, stats.cohorte(base))
    assert v["extubations_programmees"] == 1
    assert v["echecs_extubation"] == 1          # réintubé le lendemain
    assert v["extubations_non_programmees"] == 1
    assert v["jours_vm"] == 9
    assert v["taux_non_programmees"].valeur == pytest.approx(100 / 9)


def test_le_relais_par_trachéotomie_n_est_pas_une_extubation(base):
    """Intubé du 10 au 16, canule du 16 au 25 : 15 jours de ventilation, et
    aucune extubation — ni programmée, ni accidentelle, ni échouée."""
    sid = _sejour(base, 2, sortie="2026-03-30")
    i1 = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-03-10")
    dispositifs.retirer(base, i1, date_retrait="2026-03-16", motif_retrait="tracheotomie")
    t = dispositifs.poser(base, sejour_id=sid, type_="tracheotomie", date_pose="2026-03-16")
    dispositifs.retirer(base, t, date_retrait="2026-03-25")
    v = stats.indicateurs_ventilation(base, stats.cohorte(base))
    assert v["extubations_programmees"] == 0
    assert v["extubations_non_programmees"] == 0
    assert v["echecs_extubation"] == 0
    assert v["jours_vm"] == 15


def test_mortalite_porte_son_intervalle(base):
    for n in range(10):
        _sejour(base, n, sortie="2026-03-20", mode="deces" if n < 3 else "domicile")
    m = stats.mortalite(base, stats.cohorte(base))
    assert m["ic_mortalite"].bas == pytest.approx(0.1078, abs=1e-3)


def test_tendances_mensuelles(base):
    _sejour(base, 1, admission="2026-01-05", sortie="2026-01-20", mode="deces")
    _sejour(base, 2, admission="2026-01-25", sortie="2026-02-03")
    _sejour(base, 3, admission="2026-02-10")
    t = {m["mois"]: m for m in stats.tendances_mensuelles(base, stats.cohorte(base))}
    assert t["2026-01"]["admissions"] == 2 and t["2026-01"]["deces"] == 1
    assert t["2026-02"]["admissions"] == 1 and t["2026-02"]["sorties"] == 1


def test_calibration_par_classe_de_risque(base, monkeypatch):
    risques = {}
    for n in range(12):
        sid = _sejour(base, n, sortie="2026-03-20", mode="deces" if n >= 8 else "domicile")
        risques[sid] = 0.05 if n < 6 else 0.6
    monkeypatch.setattr(scores, "mortalite_predite", lambda base, sid: risques.get(sid))
    cal = stats.calibration_igs2(base, stats.cohorte(base))
    assert cal["n"] == 12
    classes = {c["classe"]: c for c in cal["classes"]}
    assert classes["0–10 %"]["observes"] == 0
    assert classes["50–75 %"]["observes"] == 4
    assert cal["auroc"].valeur > 0.8


def test_qualite_des_donnees_liste_les_dossiers_a_completer(base):
    complet = _sejour(base, 1)
    base.mettre_a_jour("sejour", complet, {"poids_kg": 70})
    _sejour(base, 2)
    lignes = {l["donnee"]: l for l in stats.qualite_des_donnees(base, stats.cohorte(base))}
    poids = lignes["Poids"]
    assert poids["concernes"] == 2 and poids["renseignes"] == 1
    assert [s["matricule"] for s in poids["manquants"]] == ["R-2"]
    # Le mode de sortie ne concerne que les séjours clos.
    assert lignes["Mode de sortie"]["concernes"] == 0


def test_les_croisements_affichent_l_intervalle():
    strate = croisements._resumer(
        "x", [(1, True)] * 3 + [(1, False)] * 7,
        croisements.Variable("deces", "Mortalité", "proportion"),
    )
    assert "IC95 11–60 %" in strate.texte
