import sqlite3
from pathlib import Path

SCHEMA = (Path(__file__).resolve().parent.parent / "rea" / "schema.sql").read_text(
    encoding="utf-8"
)

TABLES_ATTENDUES = {
    "patient",
    "sejour",
    "sejour_lit",
    "antecedent",
    "condition_chronique",
    "sejour_region_trauma",
    "sejour_motif",
    "intervention",
    "prescription_ligne",
    "journee",
    "bilan_demande",
    "pancarte_snapshot",
    "protocole_applique",
    "exploration",
    "exploration_valeur",
    "bilan_resultat",
    "gaz_du_sang",
    "microbiologie",
    "evolution_jour",
    "dispositif",
    "infection_nosocomiale",
    "score_quotidien",
    "evaluation_admission",
    "journal",
    "sauvegarde",
    "utilisateur",
    "meta",
}


def _connexion_en_memoire():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def test_schema_cree_toutes_les_tables_attendues():
    conn = _connexion_en_memoire()
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert TABLES_ATTENDUES <= tables


def test_schema_est_idempotent():
    # Le schéma doit pouvoir être rejoué sur une base existante (ouverture
    # normale de l'application) sans erreur.
    conn = _connexion_en_memoire()
    conn.executescript(SCHEMA)  # deuxième exécution


def test_aucune_table_metier_ne_permet_de_supprimer_physiquement():
    # Règle de conception 2 : chaque table métier porte une colonne `supprime`.
    conn = _connexion_en_memoire()
    tables_sans_horodatage_attendu = {"meta", "journal", "sauvegarde", "pancarte_snapshot"}
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in tables - tables_sans_horodatage_attendu:
        colonnes = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "supprime" in colonnes, f"{table} n'a pas de colonne `supprime`"
