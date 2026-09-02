from rea import protocoles


def test_protocole_brouillon_non_signe_absent_des_valides():
    tc = next(p for p in protocoles.tous_les_protocoles() if p.code == "traumatisme_cranien")
    assert tc.valide is False
    assert tc.signe_par is None
    assert tc not in protocoles.protocoles_valides()


def test_protocoles_pour_region_traumatique_est_vide_tant_que_non_signe():
    # Règle de sécurité 1 (SPEC §4.5) : jamais proposé avant signature.
    assert protocoles.protocoles_pour_region_traumatique("cranien") == ()
