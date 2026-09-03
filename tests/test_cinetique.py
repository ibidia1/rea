from rea import analytes as cat
from rea.services import bilans, sejours


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-08-29", lit_admission=1)


def test_bornes_signalent_le_haut_et_le_bas():
    assert cat.analyte("k").hors_bornes(6.2) == "haut"
    assert cat.analyte("hb").hors_bornes(9.2) == "bas"
    assert cat.analyte("hb").hors_bornes(14) is None


def test_analyte_sans_borne_ne_signale_rien():
    # On ne signale jamais ce qu'on ne sait pas juger (question ouverte 8).
    assert cat.analyte("tg").hors_bornes(99) is None
    assert cat.analyte("hb").hors_bornes(None) is None


def test_tableau_par_date(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T06:00", {"hb": 10.5, "crp": 120})
    bilans.enregistrer_resultats(base, sid, "2026-09-02T06:00", {"hb": 9.2})
    dates, matrice = bilans.tableau_par_date(base, sid)
    assert dates == ["2026-09-01T06:00", "2026-09-02T06:00"]
    assert matrice["hb"]["2026-09-02T06:00"] == 9.2
    # Un analyte non mesuré ce jour-là n'invente pas de valeur.
    assert "2026-09-02T06:00" not in matrice["crp"]


def test_tableau_filtre_sur_les_analytes_demandes(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T06:00", {"hb": 10.5, "crp": 120})
    _dates, matrice = bilans.tableau_par_date(base, sid, ["crp"])
    assert set(matrice) == {"crp"}


def test_variation_depuis_le_prelevement_precedent(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T06:00", {"hb": 10.5})
    bilans.enregistrer_resultats(base, sid, "2026-09-02T06:00", {"hb": 9.2})
    variation = bilans.dernieres_variations(base, sid, ["hb"])[0]
    assert variation.valeur == 9.2
    assert variation.precedente == 10.5
    assert variation.delta == -1.3
    assert variation.alerte == "bas"


def test_variation_sans_precedent_na_pas_de_delta(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-02T06:00", {"hb": 9.2})
    assert bilans.dernieres_variations(base, sid, ["hb"])[0].delta is None


def test_variation_dun_analyte_jamais_mesure(base):
    sid = _sejour(base)
    variation = bilans.dernieres_variations(base, sid, ["hb"])[0]
    assert variation.valeur is None
    assert variation.alerte is None


def test_analytes_renseignes_suit_lordre_du_catalogue(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T06:00", {"crp": 120, "hb": 10.5})
    # hb (NFS) vient avant crp (Inflammation) dans le catalogue.
    assert bilans.analytes_renseignes(base, sid) == ["hb", "crp"]


def test_panels_ne_contiennent_que_des_analytes_connus():
    for _code, _titre, ids in bilans.PANELS:
        for id_analyte in ids:
            assert cat.analyte(id_analyte) is not None
