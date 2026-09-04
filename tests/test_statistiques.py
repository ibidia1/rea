"""Cohortes, taux et tableau descriptif (blocs 14, 16, 17, 18)."""

from rea.services import (
    dispositifs as dispositifs_service,
    microbiologie as micro,
    prescriptions,
    sejours,
    statistiques as stats,
)


def _patient(base, matricule, naissance="1970-01-01", sexe="M"):
    return sejours.creer_patient(
        base, matricule=matricule, nom_affichage=matricule,
        date_naissance=naissance, sexe=sexe,
    )


def _sejour(base, matricule, **kw):
    pid = _patient(base, matricule, kw.pop("naissance", "1970-01-01"),
                   kw.pop("sexe", "M"))
    params = dict(patient_id=pid, date_admission="2026-09-01", lit_admission=1)
    params.update(kw)
    return sejours.creer_sejour(base, **params)


# -- cohorte -----------------------------------------------------------------

def test_cohorte_sans_filtre_prend_tout(base):
    _sejour(base, "A")
    _sejour(base, "B")
    assert len(stats.cohorte(base)) == 2


def test_cohorte_filtre_sur_la_periode(base):
    _sejour(base, "A", date_admission="2026-08-15")
    _sejour(base, "B", date_admission="2026-09-20")
    retenus = stats.cohorte(base, stats.Filtres(date_debut="2026-09-01"))
    assert len(retenus) == 1


def test_cohorte_filtre_sur_l_age(base):
    _sejour(base, "jeune", naissance="2000-01-01")
    _sejour(base, "age", naissance="1940-01-01")
    retenus = stats.cohorte(base, stats.Filtres(age_min=70))
    assert len(retenus) == 1


def test_cohorte_filtre_sur_un_dispositif(base):
    sid = _sejour(base, "A")
    _sejour(base, "B")
    dispositifs_service.poser(base, sejour_id=sid, type_="intubation",
                              date_pose="2026-09-01")
    retenus = stats.cohorte(base, stats.Filtres(dispositifs=("intubation",)))
    assert [s["id"] for s in retenus] == [sid]


def test_le_resume_des_filtres_est_lisible(base):
    filtres = stats.Filtres(date_debut="2026-01-01", traumatique=True, age_min=18)
    assert "traumatiques" in filtres.resume()


# -- Table 1 -----------------------------------------------------------------

def test_table_1_declare_les_donnees_manquantes(base):
    """STROBE demande de déclarer les manquants, pas de les diluer."""
    _sejour(base, "A", poids_kg=70)
    _sejour(base, "B")           # pas de poids
    lignes = stats.table_1(base, stats.cohorte(base))
    poids = next(l for l in lignes if l.libelle.startswith("Poids"))
    assert poids.renseignes == 1
    assert poids.total == 2
    assert poids.manquants == 1


def test_table_1_proportion_calculee_sur_les_renseignes(base):
    _sejour(base, "A", sexe="M")
    _sejour(base, "B", sexe="F")
    _sejour(base, "C", sexe="non_renseigne")
    ligne = next(l for l in stats.table_1(base, stats.cohorte(base))
                 if l.libelle == "Sexe masculin")
    assert ligne.valeur == "1 (50 %)"   # 1 homme sur 2 sexes connus, pas sur 3
    assert ligne.renseignes == 2


def test_table_1_sur_une_cohorte_vide(base):
    assert stats.table_1(base, []) == []


# -- taux ECDC ---------------------------------------------------------------

def test_taux_incalculable_sans_jours_dispositif(base):
    """« Aucune donnée » ne doit jamais s'afficher comme « zéro infection »."""
    _sejour(base, "A")
    taux = {t.libelle: t for t in stats.taux_infections_dispositifs(base, stats.cohorte(base))}
    pavm = taux["Pneumonies acquises sous ventilation"]
    assert pavm.denominateur == 0
    assert pavm.valeur is None
    assert "incalculable" in pavm.texte


def test_taux_pavm_pour_1000_jours_de_ventilation(base):
    sid = _sejour(base, "A")
    dispositifs_service.poser(base, sejour_id=sid, type_="intubation",
                              date_pose="2026-09-01")
    dispositifs_service.retirer(base,
        dispositifs_service.dernier_du_type(base, sid, "intubation")["id"],
        date_retrait="2026-09-11")
    micro.declarer_infection_nosocomiale(
        base, sejour_id=sid, type_="pavm", date_diagnostic="2026-09-06"
    )
    pavm = next(t for t in stats.taux_infections_dispositifs(base, stats.cohorte(base))
                if t.libelle.startswith("Pneumonies"))
    assert pavm.numerateur == 1
    assert pavm.denominateur > 0
    assert pavm.valeur == round(1 / pavm.denominateur * 1000, 2)


def test_une_infection_presente_a_l_admission_n_est_pas_comptee(base):
    """Sans le délai de 48 h, le service se compte des infections importées."""
    sid = _sejour(base, "A")
    dispositifs_service.poser(base, sejour_id=sid, type_="intubation",
                              date_pose="2026-09-01")
    micro.declarer_infection_nosocomiale(
        base, sejour_id=sid, type_="pavm", date_diagnostic="2026-09-01"
    )
    pavm = next(t for t in stats.taux_infections_dispositifs(base, stats.cohorte(base))
                if t.libelle.startswith("Pneumonies"))
    assert pavm.numerateur == 0


# -- antibiotiques -----------------------------------------------------------

def test_consommation_en_jours_de_traitement(base):
    sid = _sejour(base, "A")
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Ceftriaxone 2 g",
        date_debut="2026-09-01",
    )
    resultat = stats.consommation_antibiotiques(base, stats.cohorte(base))
    assert resultat["jours_de_traitement"] >= 1
    assert "ceftriaxone" in resultat["par_molecule"]
    assert resultat["ddd_disponible"] is False
    assert "DOT" in resultat["note"]


def test_un_produit_non_antibiotique_n_est_pas_compte(base):
    sid = _sejour(base, "A")
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Paracétamol 1 g",
        date_debut="2026-09-01",
    )
    assert stats.consommation_antibiotiques(base, stats.cohorte(base))["jours_de_traitement"] == 0


# -- mortalité ---------------------------------------------------------------

def test_mortalite_ne_compte_que_les_sejours_clos(base):
    sid = _sejour(base, "A")
    _sejour(base, "B")   # toujours hospitalisé
    sejours.cloturer_sejour(
        base, sid, date_heure_sortie="2026-09-10T10:00", mode_sortie="deces"
    )
    resultat = stats.mortalite(base, stats.cohorte(base))
    assert resultat["sejours_clos"] == 1
    assert resultat["deces"] == 1
    assert resultat["mortalite_observee"] == 1.0
