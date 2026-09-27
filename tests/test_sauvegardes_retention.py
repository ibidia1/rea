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


def test_la_compression_ne_bloque_pas_les_autres_ecrans(base, monkeypatch):
    """Sur une base de quelques années, compresser prend plusieurs secondes :
    pendant ce temps, les autres postes doivent pouvoir lire la base."""
    import gzip
    import threading

    import rea.database as db

    libre_pendant_compression = []
    ouvrir = gzip.open

    def espion(*args, **kwargs):
        resultat = []
        t = threading.Thread(target=lambda: resultat.append(
            base._verrou.acquire(timeout=1) and (base._verrou.release() or True)))
        t.start()
        t.join()
        libre_pendant_compression.append(bool(resultat and resultat[0]))
        return ouvrir(*args, **kwargs)

    monkeypatch.setattr(db.gzip, "open", espion)
    base.sauvegarder(motif="periodique")
    assert libre_pendant_compression == [True]


def test_une_sauvegarde_en_cours_n_apparait_pas_dans_la_liste(base):
    """La copie brute porte « .tmp » : elle ne peut pas être restaurée à
    moitié écrite."""
    from rea import config as cfg        # rechargé par le fixture sur le dossier de test

    cfg.DOSSIER_SAUVEGARDES.mkdir(parents=True, exist_ok=True)
    base.sauvegarder(motif="manuelle")
    (cfg.DOSSIER_SAUVEGARDES / "rea-20270101-000000-periodique.db.gz.tmp").write_bytes(b"x")
    noms = [s["nom"] for s in base.sauvegardes_disponibles()]
    assert noms and all(not n.endswith(".tmp") for n in noms)


def test_une_copie_interrompue_est_nettoyee(base):
    import os
    import time

    from rea import config as cfg        # rechargé par le fixture sur le dossier de test

    cfg.DOSSIER_SAUVEGARDES.mkdir(parents=True, exist_ok=True)
    reste = cfg.DOSSIER_SAUVEGARDES / "rea-20260101-000000-periodique.db.gz.tmp"
    reste.write_bytes(b"x")
    vieux = time.time() - 7200
    os.utime(reste, (vieux, vieux))
    base.sauvegarder(motif="manuelle")
    assert not reste.exists()
