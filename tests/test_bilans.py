from rea.services import bilans, sejours


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)


def test_rapport_pao2_fio2():
    assert bilans.rapport_pao2_fio2(80, 50) == 160
    assert bilans.rapport_pao2_fio2(100, None) is None
    assert bilans.rapport_pao2_fio2(100, 0) is None


def test_bilirubine_indirecte():
    assert bilans.bilirubine_indirecte(25, 8) == 17
    assert bilans.bilirubine_indirecte(None, 8) is None
    # Une bilirubine directe supérieure à la totale n'a pas de sens — pas de
    # valeur négative silencieuse.
    assert bilans.bilirubine_indirecte(5, 8) is None


def test_conversion_lipides_aller_retour():
    gl = bilans.mmol_vers_gl("ct", 5.22)
    assert gl == 2.02
    mmol = bilans.gl_vers_mmol("ct", gl)
    assert abs(mmol - 5.22) < 0.02


def test_enregistrer_resultats_ignore_les_valeurs_vides(base):
    sid = _sejour(base)
    ids = bilans.enregistrer_resultats(
        base, sid, "2026-09-01T08:00", {"hb": 9.2, "gb": None, "plq": 145}
    )
    assert len(ids) == 2
    resultats = bilans.resultats_du_sejour(base, sid)
    assert {r["analyte"] for r in resultats} == {"hb", "plq"}


def test_enregistrer_resultats_calcule_la_bili_indirecte(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T08:00", {"bili": 25, "bili_d": 8})
    resultats = {r["analyte"]: r["valeur_num"] for r in bilans.resultats_du_sejour(base, sid)}
    assert resultats["bili_i"] == 17


def test_format_long_une_ligne_par_mesure(base):
    # Règle de conception 4 : jamais une colonne par jour.
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T08:00", {"hb": 9.2})
    bilans.enregistrer_resultats(base, sid, "2026-09-02T08:00", {"hb": 8.8})
    historique = bilans.historique_analyte(base, sid, "hb")
    assert [h["valeur_num"] for h in historique] == [9.2, 8.8]


def test_texte_genere_seuls_les_champs_remplis_sortent(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-01T08:00", {"hb": 9.2, "plq": 145})
    texte = bilans.texte_genere(base, sid, "2026-09-01")
    assert texte == "- NFS : Hb = 9.2 g/dL ; PLQ = 145 10³/µL"


def test_texte_genere_gaz_du_sang_et_ventilation_separes(base):
    sid = _sejour(base)
    bilans.enregistrer_gaz_du_sang(
        base, sid, "2026-09-01T08:00", ph=7.32, pao2=80, fio2=50,
        mode_ventilatoire="VAC", pep=6, fr=18,
    )
    texte = bilans.texte_genere(base, sid, "2026-09-01")
    lignes = texte.split("\n")
    assert any(l.startswith("- Ventilation :") for l in lignes)
    assert any(l.startswith("- Gaz du sang :") for l in lignes)
    gaz = next(l for l in lignes if l.startswith("- Gaz du sang"))
    assert "PaO₂/FiO₂ = 160" in gaz


def test_texte_genere_masque_avec_debit(base):
    sid = _sejour(base)
    bilans.enregistrer_gaz_du_sang(
        base, sid, "2026-09-01T08:00", mode_ventilatoire="Masque", debit_o2=6, fio2=40,
    )
    texte = bilans.texte_genere(base, sid, "2026-09-01")
    assert "Mode = Masque 6L" in texte


def test_texte_genere_vide_sans_donnees(base):
    sid = _sejour(base)
    assert bilans.texte_genere(base, sid, "2026-09-01") == ""


def test_resultats_du_jour_ne_reprend_pas_un_autre_jour(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-08-31T08:00", {"hb": 9.2})
    assert bilans.resultats_du_jour(base, sid, "2026-09-01") == {}
