"""Délai jusqu'à l'apyrexie sous une molécule (SPEC §5.7).

« À partir de combien de jours un patient décroche sous telle molécule ? » —
décrocher, c'est **ne plus être fébrile** (définition du service, 9 septembre).
En réanimation on distingue apyrétique, subfébrile et fébrile, et la
différence décide d'une conduite : le calcul doit la respecter.

Trois pièges, un test chacun, parce que chacun ferait paraître une molécule
plus efficace qu'elle n'est :

* compter un patient **subfébrile** comme ayant décroché ;
* lire une température **non mesurée** comme une apyrexie ;
* ne rapporter que ceux qui ont décroché, en oubliant ceux qui ne décrochent
  jamais.
"""

from rea.domaine import temperature as temp
from rea.services import croisements, evolution, prescriptions, sejours


def _sejour(base, nom="P1"):
    pid = sejours.creer_patient(base, matricule=nom, nom_affichage=nom,
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid,
                                date_admission="2026-09-01", lit_admission=1)


def _temperatures(base, sid, valeurs: dict[str, float]):
    for jour, t in valeurs.items():
        evolution.enregistrer_elements(base, sid, jour, {"temperature": t})


def _cohorte(base):
    return croisements.stats.cohorte(base)


# --- les trois catégories --------------------------------------------------

def test_les_trois_categories_de_temperature():
    assert temp.categorie(36.8) == temp.APYRETIQUE
    assert temp.categorie(37.9) == temp.SUBFEBRILE
    assert temp.categorie(38.5) == temp.FEBRILE
    assert temp.categorie(None) is None


def test_une_temperature_absente_n_est_pas_une_apyrexie():
    """Sinon tout patient qu'on cesse de mesurer « décroche »."""
    assert not temp.est_apyretique(None)
    assert not temp.est_febrile(None)


# --- le délai lui-même -----------------------------------------------------

def test_le_delai_compte_le_jour_de_debut_comme_J1(base):
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {
        "2026-09-02": 39.0,   # J1 — fébrile au début
        "2026-09-03": 38.5,   # J2 — toujours fébrile
        "2026-09-04": 37.0,   # J3 — apyrétique
    })
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.episodes == 1
    assert r.decroches == 1
    assert r.delais == [3]


def test_un_patient_subfebrile_n_a_pas_decroche(base):
    """37,9 °C n'est pas une apyrexie : le patient reste compté comme non
    décroché tant qu'il n'est pas franchement apyrétique."""
    sid = _sejour(base)
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam",
        date_debut="2026-09-02",
    )
    prescriptions.arreter_ligne(base, ligne_id, date_arret="2026-09-04")
    _temperatures(base, sid, {
        "2026-09-02": 39.0,
        "2026-09-03": 37.9,   # subfébrile — pas décroché
        "2026-09-04": 37.8,
    })
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.episodes == 1
    assert r.decroches == 0
    assert r.jamais_decroches == 1


def test_un_traitement_commence_chez_un_apyretique_n_est_pas_compte(base):
    """Sans fièvre au départ, il n'y a rien à mesurer."""
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {"2026-09-02": 36.8, "2026-09-03": 36.9})
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.episodes == 0


def test_une_temperature_non_mesuree_au_debut_ecarte_l_episode(base):
    """Et l'écart est dit, pas caché : un traitement écarté silencieusement
    améliore le résultat sans que personne le sache."""
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {"2026-09-03": 36.5})   # rien le jour du début
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.episodes == 0
    assert r.sans_temperature == 1
    assert any("non mesurée" in a for a in r.avertissements)


def test_ceux_qui_ne_decrochent_jamais_sont_comptes_et_dits(base):
    """Le piège classique : ne rapporter que ceux qui ont décroché fait
    paraître efficace une molécule sous laquelle personne ne décroche."""
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {
        "2026-09-02": 39.0, "2026-09-03": 39.2, "2026-09-04": 38.8,
    })
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.episodes == 1
    assert r.jamais_decroches == 1
    assert r.delai_median is None
    assert any("n'ont pas décroché" in a for a in r.avertissements)


def test_la_part_de_decroches_n_est_pas_affichee_sur_trop_peu(base):
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {"2026-09-02": 39.0, "2026-09-03": 36.9})
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert r.decroches == 1
    assert r.part_decroches is None        # un seul épisode
    assert any("rien à conclure" in a for a in r.avertissements)


def test_le_resultat_dit_qu_il_ne_compare_pas(base):
    sid = _sejour(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Tienam", date_debut="2026-09-02")
    _temperatures(base, sid, {"2026-09-02": 39.0})
    r = croisements.delai_apyrexie(base, _cohorte(base), "Tienam")
    assert any("il ne compare pas" in a for a in r.avertissements)
