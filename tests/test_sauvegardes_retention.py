"""Sauvegardes : compressées, pas de copie inutile, rétention étagée.

200 copies complètes pour deux jours d'historique remplissaient le disque du
poste (remarque du service, 27 septembre). Désormais : les sauvegardes
automatiques sont compressées, rien n'est copié si la base n'a pas bougé, et
on garde de moins en moins serré à mesure qu'on s'éloigne — une année entière
avec une centaine de fichiers.
"""

from datetime import datetime, timedelta
from pathlib import Path

from rea import config
from rea.database import sauvegardes_a_supprimer


def _nom(quand: datetime, motif="periodique") -> Path:
    return Path(f"rea-{quand:%Y%m%d-%H%M%S}-{motif}.db.gz")


def test_la_sauvegarde_automatique_est_compressee_et_se_restaure(base):
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="S1", nom_affichage="Avant",
                                date_naissance="1970-01-01", sexe="M")
    chemin = base.sauvegarder(motif="periodique")
    assert chemin.name.endswith(".db.gz")
    sejours.creer_patient(base, matricule="S2", nom_affichage="Après",
                          date_naissance="1970-01-01", sexe="M")
    base.restaurer(chemin)
    matricules = {p["matricule"] for p in base.requete("SELECT matricule FROM patient")}
    assert "S1" in matricules and "S2" not in matricules
    assert pid


def test_la_sauvegarde_manuelle_reste_un_db_ordinaire(base):
    assert base.sauvegarder(motif="manuelle").suffix == ".db"


def test_rien_n_est_copie_si_la_base_n_a_pas_bouge(base):
    from rea.services import sejours

    assert base.sauvegarder(motif="periodique", seulement_si_modifiee=True) is not None
    assert base.sauvegarder(motif="periodique", seulement_si_modifiee=True) is None
    sejours.creer_patient(base, matricule="S3", nom_affichage="Nouveau",
                          date_naissance="1970-01-01", sexe="F")
    assert base.sauvegarder(motif="periodique", seulement_si_modifiee=True) is not None


def test_retention_etagee_sur_une_annee():
    """Une sauvegarde toutes les 15 min pendant 400 jours : il en reste une
    centaine, la plus ancienne a environ un an."""
    maintenant = datetime(2027, 10, 1, 12, 0)
    fichiers = []
    quand = maintenant
    while quand > maintenant - timedelta(days=400):
        fichiers.append((_nom(quand), quand))
        quand -= timedelta(minutes=15)
    supprimes = set(sauvegardes_a_supprimer(fichiers, maintenant))
    gardes = [q for f, q in fichiers if f not in supprimes]
    toutes = config.RETENTION_TOUTES_HEURES * 4
    horaires = config.RETENTION_HORAIRE_HEURES - config.RETENTION_TOUTES_HEURES
    assert len(gardes) <= toutes + horaires + config.RETENTION_QUOTIDIENNE_JOURS \
        + config.RETENTION_MENSUELLE_MOIS + 3
    assert maintenant - min(gardes) > timedelta(days=330)
    assert maintenant - min(gardes) < timedelta(days=31 * config.RETENTION_MENSUELLE_MOIS)
    # Les six dernières heures sont toutes là.
    assert sum(1 for q in gardes if maintenant - q < timedelta(hours=6)) == toutes


def test_un_gel_de_base_n_est_jamais_efface():
    maintenant = datetime(2027, 10, 1)
    vieux = maintenant - timedelta(days=900)
    gel = Path(f"rea-{vieux:%Y%m%d-%H%M%S}-gel-etude-sdra.db")
    fichiers = [(_nom(maintenant), maintenant), (gel, vieux),
                (_nom(vieux), vieux)]
    supprimes = sauvegardes_a_supprimer(fichiers, maintenant)
    assert gel not in supprimes
    assert _nom(vieux) in supprimes


def test_la_derniere_sauvegarde_est_toujours_gardee():
    maintenant = datetime(2027, 10, 1)
    vieux = maintenant - timedelta(days=900)
    assert sauvegardes_a_supprimer([(_nom(vieux), vieux)], maintenant) == []
