"""Croiser deux variables d'une cohorte — et refuser les chiffres trompeurs.

Ce fichier protège trois refus, qui sont l'essentiel de ce module :

* un séjour dont le facteur n'est pas renseigné n'entre dans aucune tranche
  (il est compté à part) — sinon une donnée manquante devient un « non » ;
* une tranche de moins de `EFFECTIF_MINIMAL` séjours n'affiche pas de
  pourcentage — « 100 % de mortalité » sur deux patients n'est pas un
  résultat, et dans un service de douze lits c'est le cas le plus fréquent ;
* un séjour en cours n'a pas d'issue connue : il ne compte ni comme vivant ni
  comme décédé.
"""

from rea.services import (bilans, croisements,
                          prescriptions as prescriptions_mod, sejours)


def _patient(base, nom, *, admission="2026-01-05", sortie=None, mode=None,
             naissance="1970-01-01"):
    pid = sejours.creer_patient(base, matricule=nom, nom_affichage=nom,
                                date_naissance=naissance)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission=admission,
                               lit_admission=1)
    if sortie:
        sejours.cloturer_sejour(base, sid, date_heure_sortie=sortie,
                                mode_sortie=mode)
    return sid


def _cohorte(base):
    return croisements.stats.cohorte(base)


# --- ce qui manque ne devient pas un zéro ---------------------------------

def test_un_sejour_sans_le_facteur_sort_du_tableau(base):
    """Il est compté à part, et le nombre est affiché : une variable
    renseignée chez un tiers des patients produit un croisement sur un tiers
    des patients, et il faut le voir."""
    avec = _patient(base, "Avec", sortie="2026-01-12", mode="domicile")
    _patient(base, "Sans", sortie="2026-01-12", mode="domicile")
    bilans.enregistrer_resultats(base, avec, "2026-01-06T08:00", {"crp": 120})

    c = croisements.croiser(
        base, _cohorte(base),
        code_facteur="bio:crp:max", code_resultat="deces",
    )
    assert c.total == 2
    assert c.non_renseignes == 1
    assert sum(s.effectif for s in c.strates) == 1
    assert any("n'ont pas cette donnée" in a for a in c.avertissements)


# --- pas de pourcentage sur trois patients --------------------------------

def test_une_tranche_trop_petite_n_affiche_pas_de_pourcentage(base):
    for i in range(3):
        sid = _patient(base, f"P{i}", sortie="2026-01-12", mode="deces")
        bilans.enregistrer_resultats(base, sid, "2026-01-06T08:00", {"crp": 100 + i})

    c = croisements.croiser(
        base, _cohorte(base), code_facteur="bio:crp:max",
        code_resultat="deces", seuils=(150,),
    )
    peuplee = [s for s in c.strates if s.effectif]
    assert peuplee, "la tranche des CRP < 150 doit exister"
    for strate in peuplee:
        assert not strate.interpretable
        assert "%" not in strate.texte
        assert "trop peu" in strate.texte
    assert any("moins de" in a for a in c.avertissements)


def test_une_tranche_assez_grande_affiche_sa_proportion(base):
    for i in range(6):
        mode = "deces" if i < 2 else "domicile"
        sid = _patient(base, f"P{i}", sortie="2026-01-12", mode=mode)
        bilans.enregistrer_resultats(base, sid, "2026-01-06T08:00", {"crp": 100})

    c = croisements.croiser(
        base, _cohorte(base), code_facteur="bio:crp:max",
        code_resultat="deces", seuils=(150,),
    )
    strate = next(s for s in c.strates if s.effectif == 6)
    assert strate.interpretable
    assert strate.texte.startswith("2/6")
    assert "33 %" in strate.texte


# --- un séjour en cours n'a pas d'issue -----------------------------------

def test_un_sejour_en_cours_ne_compte_ni_vivant_ni_mort(base):
    sid = _patient(base, "EnCours")           # pas de date de sortie
    bilans.enregistrer_resultats(base, sid, "2026-01-06T08:00", {"crp": 100})

    c = croisements.croiser(
        base, _cohorte(base), code_facteur="bio:crp:max",
        code_resultat="deces", seuils=(150,),
    )
    strate = next(s for s in c.strates if s.effectif == 1)
    assert strate.effectif == 1        # il est bien dans sa tranche
    assert strate.renseignes == 0      # mais son issue est inconnue
    assert strate.texte == "—"


# --- le tableau dit toujours ce qu'il ne prouve pas ------------------------

def test_chaque_croisement_porte_sa_mise_en_garde(base):
    _patient(base, "Un", sortie="2026-01-12", mode="domicile")
    c = croisements.croiser(
        base, _cohorte(base), code_facteur="age", code_resultat="deces",
    )
    assert any("ne démontre rien" in a for a in c.avertissements)


# --- le catalogue ouvert : un analyte du service est croisable -------------

def test_un_analyte_ajoute_par_le_service_devient_un_facteur(base):
    """« Mortalité selon le E/e' » ne demande pas de reprogrammer : il suffit
    que le service ait ajouté E/e' à son catalogue de biologie."""
    # `conftest` vide `sys.modules` de tout `rea.*` à chaque base : le module
    # importé en tête de fichier n'est plus celui que le service utilise, et
    # son catalogue d'analytes est un autre objet. On réimporte donc les deux
    # ici pour qu'ils partagent le même — piège déjà rencontré ailleurs.
    import importlib

    analytes_locaux = importlib.import_module("rea.services.analytes_locaux")
    module = importlib.import_module("rea.services.croisements")

    code = analytes_locaux.code_depuis_libelle("E/e'")
    analytes_locaux.ajouter(base, libelle="E/e'")
    codes = {v.code for v in module.facteurs_disponibles(base)}
    assert f"bio:{code}:max" in codes
    assert f"bio:{code}:dernier" in codes


# --- le PaO2/FiO2 se recalcule, il ne s'invente pas ------------------------

def test_le_pafi_ignore_un_gaz_sans_fio2(base):
    """Un gaz à l'air ambiant n'a pas de rapport PaO₂/FiO₂ — il n'en vaut pas
    zéro, ce qui ferait de tout patient non ventilé le plus grave du service."""
    sid = _patient(base, "Gaz", sortie="2026-01-12", mode="domicile")
    bilans.enregistrer_gaz_du_sang(base, sid, "2026-01-06T08:00",
                                   pao2=80, fio2=None)
    bilans.enregistrer_gaz_du_sang(base, sid, "2026-01-06T12:00",
                                   pao2=90, fio2=60)

    sejour = next(s for s in _cohorte(base) if s["id"] == sid)
    assert croisements.valeur_facteur(base, sejour, "pafi_min") == 150


# --- les facteurs sortent des données, pas d'une liste écrite d'avance -----
#
# « Ce que je veux, c'est pouvoir utiliser les données que j'ai » — les
# exemples cités (mortalité et E/e', mortalité et PaO₂/FiO₂) étaient des
# exemples, pas le catalogue (précision du service, 9 septembre).

def test_les_familles_de_facteurs_couvrent_tout_le_dossier(base):
    import importlib

    module = importlib.import_module("rea.services.croisements")
    familles = {v.famille for v in module.facteurs_disponibles(base)}
    for attendue in ("Dossier", "Scores", "Gaz du sang"):
        assert attendue in familles, familles


def test_un_champ_du_dossier_est_croisable(base):
    """La provenance, le mode de sortie, le Glasgow d'admission : ce sont des
    colonnes du séjour, elles n'avaient aucune raison d'être hors de portée."""
    codes = {v.code for v in croisements.facteurs_disponibles(base)}
    for attendu in ("sejour:provenance_type", "sejour:mode_sortie",
                    "sejour:glasgow_initial", "imc"):
        assert attendu in codes


def test_un_produit_prescrit_ouvre_l_exposition_et_la_duree(base):
    for i in range(2):
        sid = _patient(base, f"P{i}")
        prescriptions_mod.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam",
                                        date_debut="2026-01-06")
    codes = {v.code for v in croisements.facteurs_disponibles(base)}
    assert "produit:Tienam" in codes
    assert "duree_produit:Tienam" in codes


def test_la_duree_d_un_traitement_se_calcule(base):
    sid = _patient(base, "Duree", sortie="2026-01-12", mode="domicile")
    ligne = prescriptions_mod.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam",
        date_debut="2026-01-06",
    )
    prescriptions_mod.arreter_ligne(base, ligne, date_arret="2026-01-10")
    sejour = next(s for s in _cohorte(base) if s["id"] == sid)
    assert croisements.valeur_facteur(base, sejour, "duree_produit:Tienam") == 5


def test_un_facteur_d_exposition_repond_non_et_non_inconnu(base):
    """Pour « a reçu / a eu / a isolé », l'absence de ligne est un non. Le
    dire « inconnu » viderait le croisement de sa moitié utile."""
    sid = _patient(base, "Sans", sortie="2026-01-12", mode="domicile")
    sejour = next(s for s in _cohorte(base) if s["id"] == sid)
    assert croisements.valeur_facteur(base, sejour, "produit:Tienam") == "Non"


def test_une_colonne_booleenne_se_lit_oui_non(base):
    """« traumatique = 1 » n'apprend rien à personne dans un tableau."""
    sid = _patient(base, "Trauma", sortie="2026-01-12", mode="domicile")
    base.mettre_a_jour("sejour", sid, {"traumatique": 1})
    sejour = next(s for s in _cohorte(base) if s["id"] == sid)
    assert croisements.valeur_facteur(base, sejour, "sejour:traumatique") == "Oui"


def test_un_resultat_manquant_reste_manquant(base):
    """Un patient perdu de vue à J28 n'est pas un survivant."""
    sid = _patient(base, "Perdu", sortie="2026-01-12", mode="domicile")
    base.mettre_a_jour("sejour", sid, {"statut_j28": "perdu_de_vue"})
    sejour = next(s for s in _cohorte(base) if s["id"] == sid)
    assert croisements.valeur_resultat(base, sejour, "deces_j28") is None
