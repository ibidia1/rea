"""Couche base de données.

Une connexion SQLite unique, un fichier unique (SPEC §2.2). Sauvegardes
automatiques à l'ouverture, toutes les 15 minutes, et à la fermeture.

Tout ce qui écrit passe par `executer()` ou `inserer()` / `mettre_a_jour()`
qui journalisent l'action (SPEC §3, §10 — bloc 7).
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config


# Mots qui commencent une contrainte de table, pas une colonne.
_MOTS_CLES_SQL = {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}

# `pancarte_snapshot.version` existe depuis l'origine et désigne le numéro
# d'impression d'une feuille (v1, v2 du même jour) : l'incrémenter à chaque
# écriture renuméroterait les feuilles déjà sorties de l'imprimante. Cette
# table est de toute façon immuable — on ne modifie jamais un instantané.
TABLES_SANS_COMPTEUR_DE_VERSION = {"pancarte_snapshot"}


def nouvel_id() -> str:
    return str(uuid.uuid4())


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    champs = [c[0] for c in cursor.description]
    return dict(zip(champs, row))


class Base:
    """Enveloppe autour d'une connexion SQLite vers le fichier du service."""

    def __init__(self, chemin: Path | str | None = None):
        self.chemin = Path(chemin) if chemin else config.FICHIER_BASE
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        # Réentrant : une transaction garde le verrou pendant qu'elle appelle
        # `inserer()`, qui le reprend. Un verrou simple se bloquerait lui-même.
        self._verrou = threading.RLock()
        self._profondeur_transaction = 0
        self.connexion = sqlite3.connect(
            str(self.chemin), check_same_thread=False, isolation_level=None
        )
        self.connexion.row_factory = _dict_factory
        self.connexion.execute("PRAGMA foreign_keys = ON")
        self.connexion.execute("PRAGMA journal_mode = WAL")
        self._initialiser_schema()
        self._minuteur_sauvegarde: threading.Timer | None = None

    # -- schéma -----------------------------------------------------------
    def _initialiser_schema(self) -> None:
        """Crée le schéma, puis rattrape ce qui manque à une base plus ancienne.

        L'ordre compte. Le script complet contient des index qui portent sur des
        colonnes ajoutées après coup (`idx_sejour_ouvert` sur `date_sortie`, par
        exemple) : le jouer en entier sur une base ancienne échoue avant même
        d'arriver au rattrapage, et l'application ne démarre plus du tout. Les
        tables sont donc créées d'abord, les colonnes manquantes ajoutées
        ensuite, et le reste du script seulement à la fin.
        """
        sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        tables = "\n".join(
            bloc.group(0)
            for bloc in re.finditer(r"CREATE TABLE IF NOT EXISTS.*?\n\);", sql, re.S)
        )
        with self._verrou:
            self.connexion.executescript(tables)
        self._completer_colonnes_manquantes(sql)
        with self._verrou:
            self.connexion.executescript(sql)
            existe = self.connexion.execute(
                "SELECT valeur FROM meta WHERE cle = 'version_schema'"
            ).fetchone()
            if not existe:
                self.connexion.execute(
                    "INSERT INTO meta(cle, valeur) VALUES ('version_schema', ?)",
                    (config.__dict__.get("VERSION_SCHEMA", "1"),),
                )

    def _completer_colonnes_manquantes(self, sql: str) -> None:
        """Ajoute aux tables existantes les colonnes apparues dans le schéma.

        `CREATE TABLE IF NOT EXISTS` ne touche pas à une table déjà créée : sans
        ce rattrapage, une base ouverte par une version plus ancienne du
        logiciel resterait sans les nouvelles colonnes, et le programme
        planterait à la première écriture. Le jour où le service tourne pour de
        bon, on ne peut plus se permettre de repartir d'une base vide.

        Seules les colonnes ajoutables sans risque le sont : SQLite refuse
        d'ajouter une colonne NOT NULL sans valeur par défaut, et un tel ajout
        n'aurait de toute façon pas de sens sur des lignes déjà écrites.
        """
        for bloc in re.finditer(
            r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", sql, re.S
        ):
            table, corps = bloc.group(1), bloc.group(2)
            existantes = self._colonnes(table)
            if not existantes:
                continue
            for ligne in corps.splitlines():
                ligne = ligne.split("--")[0].strip().rstrip(",")
                if not ligne:
                    continue
                nom = ligne.split()[0]
                if not nom.isidentifier() or nom.upper() in _MOTS_CLES_SQL:
                    continue
                if nom in existantes:
                    continue
                definition = ligne
                if "NOT NULL" in definition.upper() and "DEFAULT" not in definition.upper():
                    continue
                with self._verrou:
                    self.connexion.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    # -- requêtes -----------------------------------------------------------
    def requete(self, sql: str, parametres: tuple = ()) -> list[dict]:
        with self._verrou:
            return self.connexion.execute(sql, parametres).fetchall()

    def une_ligne(self, sql: str, parametres: tuple = ()) -> dict | None:
        lignes = self.requete(sql, parametres)
        return lignes[0] if lignes else None

    def _colonnes(self, table: str) -> set[str]:
        return {ligne["name"] for ligne in self.requete(f"PRAGMA table_info({table})")}

    # -- transactions -------------------------------------------------------
    @contextmanager
    def transaction(self):
        """Rend atomique un groupe d'écritures : tout passe, ou rien.

        Sans elle, la connexion est en validation automatique — chaque écriture
        est définitive dès qu'elle est faite. Une admission, qui crée d'abord le
        patient puis le séjour, laissait donc un patient sans séjour si la
        seconde écriture échouait.

        Le verrou est tenu pendant toute la transaction : c'est lui qui empêche
        deux onglets (Streamlit sert chacun dans son propre fil) de lire le même
        compteur avant que l'autre ne l'ait incrémenté. `BEGIN IMMEDIATE` prend
        le verrou d'écriture de SQLite tout de suite, plutôt qu'à la première
        écriture, ce qui écarte le même écueil entre deux processus.

        S'imbrique : une transaction ouverte dans une autre rejoint la première
        et ne valide rien avant elle.
        """
        with self._verrou:
            if self._profondeur_transaction:
                self._profondeur_transaction += 1
                try:
                    yield self
                finally:
                    self._profondeur_transaction -= 1
                return
            self.connexion.execute("BEGIN IMMEDIATE")
            self._profondeur_transaction = 1
            try:
                yield self
            except BaseException:
                self.connexion.execute("ROLLBACK")
                raise
            else:
                self.connexion.execute("COMMIT")
            finally:
                self._profondeur_transaction = 0

    def executer(self, sql: str, parametres: tuple = ()) -> None:
        with self._verrou:
            self.connexion.execute(sql, parametres)

    def inserer(
        self,
        table: str,
        valeurs: dict,
        *,
        utilisateur_id: str | None = None,
        action: str = "creation",
    ) -> str:
        """Insère une ligne avec horodatage (règle de conception 3) et
        journalise l'action (règle de conception 8, SPEC bloc 7)."""
        valeurs = dict(valeurs)
        colonnes_table = self._colonnes(table)
        valeurs.setdefault("id", nouvel_id())
        if "cree_le" not in valeurs and "cree_le" in colonnes_table:
            valeurs["cree_le"] = maintenant()
        if "cree_par" not in valeurs and "cree_par" in colonnes_table:
            valeurs["cree_par"] = utilisateur_id
        colonnes = ", ".join(valeurs.keys())
        espaces = ", ".join("?" for _ in valeurs)
        # La ligne et sa trace au journal partent ensemble : une écriture sans
        # trace ne serait pas opposable (règle de conception 8).
        with self.transaction():
            self.connexion.execute(
                f"INSERT INTO {table} ({colonnes}) VALUES ({espaces})",
                tuple(valeurs.values()),
            )
            self._journaliser(table, valeurs["id"], action, utilisateur_id, valeurs)
        return valeurs["id"]

    def mettre_a_jour(
        self,
        table: str,
        id_ligne: str,
        valeurs: dict,
        *,
        utilisateur_id: str | None = None,
        action: str = "modification",
    ) -> None:
        valeurs = dict(valeurs)
        colonnes = self._colonnes(table)
        if "modifie_le" in colonnes:
            valeurs["modifie_le"] = maintenant()
        if "modifie_par" in colonnes:
            valeurs["modifie_par"] = utilisateur_id
        affectation = ", ".join(f"{cle} = ?" for cle in valeurs)
        # §2.4, invariant 1 : `version` s'incrémente à chaque écriture. Personne
        # ne la lit encore — elle est là pour que détecter un conflit entre deux
        # postes, le jour venu, ne demande pas de migrer des données cliniques
        # déjà écrites. Incrémentée en SQL et non en Python : c'est la base qui
        # doit compter, pas la lecture qui a précédé.
        if "version" in colonnes and table not in TABLES_SANS_COMPTEUR_DE_VERSION:
            affectation += ", version = version + 1"
        with self.transaction():
            self.connexion.execute(
                f"UPDATE {table} SET {affectation} WHERE id = ?",
                (*valeurs.values(), id_ligne),
            )
            self._journaliser(table, id_ligne, action, utilisateur_id, valeurs)

    def supprimer_logiquement(
        self, table: str, id_ligne: str, *, utilisateur_id: str | None = None
    ) -> None:
        """Jamais de DELETE — règle de conception 2."""
        self.mettre_a_jour(
            table, id_ligne, {"supprime": 1}, utilisateur_id=utilisateur_id, action="suppression"
        )

    def journaliser_forcage(
        self,
        *,
        cible: str,
        avertissements,
        utilisateur_id: str | None = None,
        ligne_id: str | None = None,
    ) -> None:
        """Trace le franchissement d'un garde-fou de cohérence (bloc 4).

        Un avertissement « impossible » — sortie avant l'admission, extubation
        avant l'intubation — se franchit à un second clic. Le médecin garde le
        dernier mot, mais le dossier doit dire qu'un garde-fou a été franchi :
        sans ça, la ligne écrite ressemble à n'importe quelle autre, et personne
        ne peut savoir plus tard que le logiciel avait signalé quelque chose.

        `bilan_resultat` porte en plus une colonne `saisie_forcee` ; ici on
        garde la trace pour tous les écrans, y compris ceux qui n'ont pas de
        colonne où la mettre.
        """
        self._journaliser(
            cible,
            ligne_id,
            "forcage_coherence",
            utilisateur_id,
            {
                "avertissements": [
                    {"gravite": a.gravite, "message": a.message} for a in avertissements
                ]
            },
        )

    def journaliser_evenement(
        self,
        *,
        action: str,
        details: dict,
        cible: str = "systeme",
        ligne_id: str | None = None,
        utilisateur_id: str | None = None,
    ) -> None:
        """Trace un événement qui ne correspond à aucune ligne créée ou
        modifiée — un export, un gel de base.

        À utiliser plutôt que `inserer("journal", ...)` : `inserer()`
        journalise automatiquement toute écriture, donc insérer directement
        dans `journal` par ce chemin laisse une seconde trace fantôme, qui dit
        seulement « une ligne a été créée dans journal » sans rien d'utile.
        """
        self._journaliser(cible, ligne_id, action, utilisateur_id, details)

    def _journaliser(
        self, table: str, ligne_id: str | None, action: str, utilisateur_id: str | None, details: dict
    ) -> None:
        details_serialisables = {
            k: v for k, v in details.items() if k not in ("id",) and not isinstance(v, (bytes,))
        }
        with self._verrou:
            self.connexion.execute(
                "INSERT INTO journal(id, date_heure, utilisateur_id, table_cible, ligne_id, "
                "action, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    nouvel_id(),
                    maintenant(),
                    utilisateur_id,
                    table,
                    ligne_id,
                    action,
                    json.dumps(details_serialisables, ensure_ascii=False, default=str),
                ),
            )

    # -- sauvegardes (SPEC §2.2) --------------------------------------------
    def sauvegarder(self, motif: str = "manuelle") -> Path:
        """Copie le fichier de base vers le dossier de sauvegardes, avec
        horodatage dans le nom. Utilise la sauvegarde en ligne de SQLite
        (fonctionne même pendant l'écriture, contrairement à un `cp` brut)."""
        config.DOSSIER_SAUVEGARDES.mkdir(parents=True, exist_ok=True)
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = config.DOSSIER_SAUVEGARDES / f"rea-{horodatage}-{motif}.db"
        # Deux sauvegardes dans la même seconde portaient le même nom : la
        # seconde écrasait la première. Ça n'arrive jamais avec les sauvegardes
        # périodiques, mais toujours avec le filet de sécurité posé juste avant
        # une restauration — c'est-à-dire au pire moment possible.
        rang = 1
        while destination.exists():
            rang += 1
            destination = (
                config.DOSSIER_SAUVEGARDES / f"rea-{horodatage}-{motif}-{rang}.db"
            )
        with self._verrou:
            sauvegarde_connexion = sqlite3.connect(str(destination))
            with sauvegarde_connexion:
                self.connexion.backup(sauvegarde_connexion)
            sauvegarde_connexion.close()
            self.connexion.execute(
                "INSERT INTO sauvegarde(id, date_heure, fichier, taille, motif) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    nouvel_id(),
                    maintenant(),
                    str(destination),
                    destination.stat().st_size,
                    motif,
                ),
            )
        self._purger_anciennes_sauvegardes()
        return destination

    def _purger_anciennes_sauvegardes(self) -> None:
        fichiers = sorted(
            config.DOSSIER_SAUVEGARDES.glob("rea-*.db"), key=lambda p: p.stat().st_mtime
        )
        excedent = len(fichiers) - config.SAUVEGARDES_CONSERVEES
        for fichier in fichiers[:max(excedent, 0)]:
            fichier.unlink(missing_ok=True)

    def demarrer_sauvegardes_periodiques(self) -> None:
        """À appeler une fois à l'ouverture. Programme une sauvegarde toutes
        les `INTERVALLE_SAUVEGARDE_MINUTES` minutes."""
        if self._minuteur_sauvegarde is not None:
            return

        def _boucle() -> None:
            self.sauvegarder(motif="periodique")
            self._minuteur_sauvegarde = threading.Timer(
                config.INTERVALLE_SAUVEGARDE_MINUTES * 60, _boucle
            )
            self._minuteur_sauvegarde.daemon = True
            self._minuteur_sauvegarde.start()

        self._minuteur_sauvegarde = threading.Timer(
            config.INTERVALLE_SAUVEGARDE_MINUTES * 60, _boucle
        )
        self._minuteur_sauvegarde.daemon = True
        self._minuteur_sauvegarde.start()

    def arreter_sauvegardes_periodiques(self) -> None:
        if self._minuteur_sauvegarde is not None:
            self._minuteur_sauvegarde.cancel()
            self._minuteur_sauvegarde = None

    # -- restauration (feuille de route, critère de fin du bloc 0) ----------
    def sauvegardes_disponibles(self) -> list[dict]:
        """Les fichiers de sauvegarde présents, du plus récent au plus ancien."""
        if not config.DOSSIER_SAUVEGARDES.exists():
            return []
        fichiers = sorted(
            config.DOSSIER_SAUVEGARDES.glob("rea-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [
            {
                "chemin": f,
                "nom": f.name,
                "taille": f.stat().st_size,
                "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            }
            for f in fichiers
        ]

    def restaurer(self, chemin_sauvegarde: Path | str) -> Path:
        """Remplace la base courante par une sauvegarde.

        « Une sauvegarde jamais restaurée n'existe pas » : cette fonction est
        le critère de fin du bloc 0, et elle est testée.

        La base actuelle est sauvegardée avant tout — restaurer par erreur ne
        doit jamais être irréversible.
        """
        source = Path(chemin_sauvegarde)
        if not source.exists():
            raise FileNotFoundError(f"Sauvegarde introuvable : {source}")

        filet = self.sauvegarder(motif="avant-restauration")
        self.arreter_sauvegardes_periodiques()
        with self._verrou:
            self.connexion.close()
            shutil.copy2(source, self.chemin)
            # Les fichiers annexes du mode WAL décrivent l'ancienne base : les
            # laisser rendrait la restauration incohérente.
            for suffixe in ("-wal", "-shm"):
                annexe = Path(str(self.chemin) + suffixe)
                annexe.unlink(missing_ok=True)
            self.connexion = sqlite3.connect(
                str(self.chemin), check_same_thread=False, isolation_level=None
            )
            self.connexion.row_factory = _dict_factory
            self.connexion.execute("PRAGMA foreign_keys = ON")
            self.connexion.execute("PRAGMA journal_mode = WAL")
        self._initialiser_schema()
        self.connexion.execute(
            "INSERT INTO journal(id, date_heure, utilisateur_id, table_cible, ligne_id, "
            "action, details) VALUES (?, ?, NULL, 'base', 'base', 'restauration', ?)",
            (nouvel_id(), maintenant(),
             json.dumps({"depuis": str(source), "filet": str(filet)}, ensure_ascii=False)),
        )
        return filet

    # -- journal d'audit consultable (bloc 0) -------------------------------
    def journal(self, limite: int = 200, table: str | None = None) -> list[dict]:
        """Le journal doit être lisible, pas seulement écrit : sans ça,
        « qui a modifié quoi » n'est pas reconstituable (principes ALCOA+)."""
        sql = (
            "SELECT j.*, u.nom AS utilisateur_nom FROM journal j "
            "LEFT JOIN utilisateur u ON u.id = j.utilisateur_id "
        )
        parametres: tuple = ()
        if table:
            sql += "WHERE j.table_cible = ? "
            parametres = (table,)
        sql += "ORDER BY j.date_heure DESC, j.rowid DESC LIMIT ?"
        return self.requete(sql, (*parametres, limite))

    def tables_journalisees(self) -> list[str]:
        """Les tables sur lesquelles le journal porte au moins une trace —
        de quoi peupler le filtre de l'écran d'administration sans que celui-ci
        ait à écrire du SQL (§2.4, invariant 3)."""
        return [
            ligne["table_cible"]
            for ligne in self.requete(
                "SELECT DISTINCT table_cible FROM journal ORDER BY table_cible"
            )
        ]

    def fermer(self) -> None:
        self.arreter_sauvegardes_periodiques()
        self.sauvegarder(motif="fermeture")
        self.connexion.close()


_BASE: Base | None = None


def obtenir_base() -> Base:
    """Connexion partagée pour tout le processus Streamlit."""
    global _BASE
    if _BASE is None:
        _BASE = Base()
        _BASE.sauvegarder(motif="ouverture")
        _BASE.demarrer_sauvegardes_periodiques()
    return _BASE
