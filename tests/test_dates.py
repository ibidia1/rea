from rea.domaine import dates


def test_age_avant_anniversaire():
    assert dates.age_ans("1978-03-14", "2026-03-13") == 47


def test_age_jour_anniversaire():
    assert dates.age_ans("1978-03-14", "2026-03-14") == 48


def test_age_sans_date_naissance_est_none():
    assert dates.age_ans(None) is None


def test_jour_hospitalisation_jour_admission_est_j1():
    assert dates.jour_hospitalisation("2026-08-28", "2026-08-28") == 1


def test_jour_hospitalisation():
    assert dates.jour_hospitalisation("2026-08-28", "2026-09-01") == 5


def test_jour_traitement_introduction():
    assert dates.jour_traitement("2026-09-01", "2026-09-01") == 1


def test_jour_traitement_lendemain():
    assert dates.jour_traitement("2026-09-01", "2026-09-02") == 2


def test_duree_sejour_en_cours_jusqua_aujourdhui():
    assert dates.duree_sejour_jours("2026-08-28", None) >= 1


def test_duree_sejour_close():
    assert dates.duree_sejour_jours("2026-08-28", "2026-09-05") == 9


def test_format_date_fr():
    assert dates.format_date_fr("2026-09-01") == "01/09/2026"


def test_format_date_fr_valeur_absente():
    assert dates.format_date_fr(None) == ""
