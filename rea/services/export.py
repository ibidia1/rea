"""Export pseudonymisé et gel de base (bloc 13).

Ce que l'export doit garantir, et qui n'est pas négociable :

1. **Aucun identifiant direct ne sort.** Matricule, nom affiché et date de
   naissance ne sont jamais écrits ; le patient est désigné par son
   identifiant d'étude, stable d'un export à l'autre, et l'âge remplace la
   date de naissance.
2. **Aucun texte libre ne sort par défaut.** Un commentaire d'évolution peut
   contenir un nom, un lieu, un numéro de chambre. Les colonnes de texte libre
   sont retirées, sauf demande explicite — et l'export dit alors qu'elles y
   sont.
3. **La politique de pseudonymisation est dans le code, pas dans un fichier de
   configuration.** Tout le reste du logiciel est paramétrable par fichiers ;
   pas ceci. Un fichier se modifie sans trace et sans relecture — c'est
   exactement ce qu'on ne veut pas d'une règle de protection des données.
4. **Un export est daté, versionné et reproductible.** Il emporte son
   dictionnaire des données et la version de chaque référentiel : sans quoi,
   six mois plus tard, personne ne sait ce que valait la colonne.

Trois valeurs manquantes distinctes voyagent dans les fichiers, parce que les
confondre fausse toute analyse :

    .NR   non renseigné — la donnée existe, personne ne l'a saisie
    .NA   non applicable — la question n'a pas de sens ici
    .NF   non fait — l'examen n'a pas été réalisé
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .. import aides, analytes as cat, config, referentiels
from ..db import Base
from ..domaine.dates import age_ans

NON_RENSEIGNE = ".NR"
NON_APPLICABLE = ".NA"
NON_FAIT = ".NF"

# Colonnes qui identifient directement une personne : jamais exportées.
IDENTIFIANTS_DIRECTS = {
    "patient": ("matricule", "nom_affichage", "date_naissance", "fusionne_vers"),
    "utilisateur": ("nom",),
}

# Colonnes de texte libre : retirées par défaut (elles peuvent contenir un nom).
TEXTE_LIBRE = {
    "patient": ("traitement_habituel",),
    "sejour": ("provenance_detail", "motif_readmission", "mecanisme_detail",
               "destination", "complication_texte", "ordonnance_sortie",
               "consultation_externe"),
    "antecedent": ("libelle", "precision"),
    "evolution_jour": ("plan_neurologique", "plan_respiratoire",
                       "plan_hemodynamique", "plan_infectieux", "conduite"),
    "evolution_element": ("valeur_texte",),
    "dispositif": ("commentaire",),
    "exploration": ("conclusion", "operateur"),
    "microbiologie": ("antibiogramme",),
    "prescription_ligne": ("condition_texte", "additifs", "dilution"),
    "escarre": ("commentaire",),
    "infection_nosocomiale": ("commentaire",),
    "intervention": ("geste_detail", "complication_texte"),
    "sejour_motif": ("texte", "donnees"),
}

# Tables exportées, dans l'ordre où on les lit. Le journal d'audit et les
# sauvegardes n'en font pas partie : ils décrivent qui a travaillé, pas les
# patients.
TABLES = (
    "patient", "sejour", "sejour_motif", "sejour_region_trauma", "antecedent",
    "condition_chronique", "intervention", "prescription_ligne", "journee",
    "bilan_demande", "bilan_resultat", "gaz_du_sang", "microbiologie",
    "exploration", "exploration_valeur", "evolution_jour", "evolution_element",
    "escarre", "dispositif", "infection_nosocomiale", "score_quotidien",
    "evaluation_admission",
)


def _colonnes_exportables(base: Base, table: str, avec_texte_libre: bool) -> list[str]:
    colonnes = [
        ligne["name"] for ligne in base.requete(f"PRAGMA table_info({table})")
    ]
    exclues = set(IDENTIFIANTS_DIRECTS.get(table, ()))
    if not avec_texte_libre:
        exclues |= set(TEXTE_LIBRE.get(table, ()))
    # Ces colonnes disent qui a saisi : inutiles à l'analyse, sensibles pour
    # le personnel.
    exclues |= {"cree_par", "modifie_par"}
    return [c for c in colonnes if c not in exclues]


def _valeur_export(valeur) -> str:
    return NON_RENSEIGNE if valeur is None else str(valeur)


def exporter(
    base: Base,
    *,
    dossier: Path | str | None = None,
    sejour_ids: list[str] | None = None,
    avec_texte_libre: bool = False,
    motif: str = "",
    utilisateur_id: str | None = None,
) -> Path:
    """Écrit l'export et rend le dossier créé.

    `sejour_ids` restreint l'export à une cohorte ; sans lui, tous les séjours
    non supprimés sont exportés.
    """
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    racine = Path(dossier) if dossier else config.DOSSIER_EXPORTS / f"export-{horodatage}"
    racine.mkdir(parents=True, exist_ok=True)

    if sejour_ids is None:
        sejour_ids = [
            s["id"] for s in base.requete("SELECT id FROM sejour WHERE supprime = 0")
        ]
    patients = {
        s["patient_id"]
        for s in base.requete(
            "SELECT patient_id FROM sejour WHERE id IN (%s)"
            % ",".join("?" * len(sejour_ids)),
            tuple(sejour_ids),
        )
    } if sejour_ids else set()

    compte: dict[str, int] = {}
    for table in TABLES:
        lignes = _lignes_table(base, table, sejour_ids, patients)
        colonnes = _colonnes_exportables(base, table, avec_texte_libre)
        if table == "patient":
            colonnes = [c for c in colonnes if c != "id"]
        chemin = racine / f"{table}.csv"
        with chemin.open("w", encoding="utf-8", newline="") as fichier:
            ecrivain = csv.writer(fichier, delimiter=";")
            entetes = list(colonnes)
            if table == "sejour":
                entetes.append("age_admission")
            ecrivain.writerow(entetes)
            for ligne in lignes:
                valeurs = [_valeur_export(ligne.get(c)) for c in colonnes]
                if table == "sejour":
                    valeurs.append(_age_du_sejour(base, ligne))
                ecrivain.writerow(valeurs)
        compte[table] = len(lignes)

    _ecrire_dictionnaire(base, racine, avec_texte_libre)
    manifeste = _ecrire_manifeste(base, racine, compte, avec_texte_libre, motif, sejour_ids)
    base.inserer(
        "journal",
        {
            "date_heure": datetime.now().isoformat(timespec="seconds"),
            "utilisateur_id": utilisateur_id,
            "table_cible": "export",
            "ligne_id": racine.name,
            "action": "export",
            "details": json.dumps(
                {"dossier": str(racine), "sejours": len(sejour_ids),
                 "texte_libre": avec_texte_libre, "motif": motif},
                ensure_ascii=False,
            ),
        },
    )
    return manifeste.parent


def _lignes_table(base: Base, table: str, sejour_ids: list[str], patients: set[str]) -> list[dict]:
    if not sejour_ids:
        return []
    espaces = ",".join("?" * len(sejour_ids))
    colonnes = {l["name"] for l in base.requete(f"PRAGMA table_info({table})")}
    if table == "patient":
        if not patients:
            return []
        return base.requete(
            "SELECT * FROM patient WHERE id IN (%s) AND supprime = 0"
            % ",".join("?" * len(patients)),
            tuple(patients),
        )
    if "sejour_id" in colonnes:
        return base.requete(
            f"SELECT * FROM {table} WHERE sejour_id IN ({espaces})"
            + (" AND supprime = 0" if "supprime" in colonnes else ""),
            tuple(sejour_ids),
        )
    if table == "sejour":
        return base.requete(
            f"SELECT * FROM sejour WHERE id IN ({espaces}) AND supprime = 0",
            tuple(sejour_ids),
        )
    return []


def _age_du_sejour(base: Base, sejour: dict) -> str:
    patient = base.une_ligne(
        "SELECT date_naissance FROM patient WHERE id = ?", (sejour["patient_id"],)
    )
    age = age_ans((patient or {}).get("date_naissance"), sejour["date_admission"])
    return NON_RENSEIGNE if age is None else str(age)


# --------------------------------------------------------------------------
# Dictionnaire des données
# --------------------------------------------------------------------------

def _ecrire_dictionnaire(base: Base, racine: Path, avec_texte_libre: bool) -> Path:
    """« Un export sans dictionnaire est illisible dans six mois. »"""
    chemin = racine / "dictionnaire.csv"
    with chemin.open("w", encoding="utf-8", newline="") as fichier:
        ecrivain = csv.writer(fichier, delimiter=";")
        ecrivain.writerow(
            ["table", "colonne", "type", "obligatoire", "referentiel", "note"]
        )
        for table in TABLES:
            infos = {l["name"]: l for l in base.requete(f"PRAGMA table_info({table})")}
            for colonne in _colonnes_exportables(base, table, avec_texte_libre):
                info = infos.get(colonne, {})
                ecrivain.writerow([
                    table,
                    colonne,
                    info.get("type", ""),
                    "oui" if info.get("notnull") else "non",
                    _referentiel_de(colonne),
                    _note_de(table, colonne),
                ])
        for id_analyte in cat.tous_les_ids():
            a = cat.analyte(id_analyte)
            ecrivain.writerow([
                "bilan_resultat", f"analyte = {id_analyte}", "REAL", "non", "analytes",
                f"{a.libelle} ({a.unite}) · LOINC {a.code_loinc or '—'}"
                + ("" if cat.LOINC_VALIDE else " · correspondance LOINC provisoire"),
            ])
    return chemin


_REFERENTIEL_PAR_COLONNE = {
    "provenance_type": "provenances", "mode_sortie": "modes_sortie",
    "sexe": "sexes", "role": "roles", "mecanisme": "mecanismes",
    "voie": "voies", "rythme": "rythmes", "unite": "unites",
    "type_prelevement": "prelevements", "resultat": "resultats_microbio",
    "type_admission": "types_admission",
    "maladie_chronique_igs2": "maladies_chroniques_igs2",
    "categorie": "categories_antecedent", "code": "conditions_chroniques",
    "cle": "elements_plan", "localisation": "escarres",
}


def _referentiel_de(colonne: str) -> str:
    nom = _REFERENTIEL_PAR_COLONNE.get(colonne)
    if not nom:
        return ""
    try:
        return f"{nom} v{referentiels.version(nom)}"
    except Exception:
        return nom


def _note_de(table: str, colonne: str) -> str:
    if colonne == "identifiant_etude":
        return "Identifiant pseudonyme stable ; la table de correspondance reste dans le service."
    if colonne == "supprime":
        return "1 = ligne annulée, jamais effacée physiquement."
    if colonne.startswith("date"):
        return "Date ISO (AAAA-MM-JJ) ou date-heure ISO."
    if table == "evolution_element" and colonne == "valeur_num":
        return "Format long : une ligne par élément et par jour."
    return ""


# --------------------------------------------------------------------------
# Manifeste : de quoi refaire exactement le même export
# --------------------------------------------------------------------------

def _ecrire_manifeste(
    base: Base, racine: Path, compte: dict, avec_texte_libre: bool,
    motif: str, sejour_ids: list[str],
) -> Path:
    manifeste = {
        "date_export": datetime.now().isoformat(timespec="seconds"),
        "motif": motif,
        "nb_sejours": len(sejour_ids),
        "lignes_par_table": compte,
        "texte_libre_inclus": avec_texte_libre,
        "valeurs_manquantes": {
            NON_RENSEIGNE: "non renseigné — la donnée existe, personne ne l'a saisie",
            NON_APPLICABLE: "non applicable — la question n'a pas de sens pour ce patient",
            NON_FAIT: "non fait — l'examen n'a pas été réalisé",
        },
        "versions_referentiels": {
            ligne["nom"]: ligne["version"] for ligne in referentiels.inventaire()
        },
        "versions_regles": {
            jeu["code"]: jeu["version"] for jeu in aides.inventaire()
        },
        "catalogue_analytes": cat.VERSION_CATALOGUE,
        "loinc_valide": cat.LOINC_VALIDE,
        "avertissements": [
            "Les identifiants directs (matricule, nom, date de naissance) ne "
            "sont pas exportés ; la table de correspondance reste dans le service.",
            "Un export reste une donnée de santé : il se conserve et se "
            "transmet comme telle.",
        ],
    }
    if not avec_texte_libre:
        manifeste["avertissements"].append(
            "Les colonnes de texte libre ont été retirées : elles peuvent "
            "contenir des éléments identifiants."
        )
    else:
        manifeste["avertissements"].insert(
            0,
            "⚠️ TEXTE LIBRE INCLUS : cet export peut contenir des éléments "
            "identifiants et n'est pas pseudonymisé de façon fiable.",
        )
    chemin = racine / "manifeste.json"
    chemin.write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return chemin


# --------------------------------------------------------------------------
# Gel de base
# --------------------------------------------------------------------------

def geler(base: Base, *, motif: str, utilisateur_id: str | None = None) -> dict:
    """Fige un état de la base pour une analyse.

    Une étude qui tourne pendant que les données bougent n'est pas
    reproductible : deux mois plus tard, le même filtre rend un autre chiffre,
    et personne ne sait lequel a servi à écrire l'article. Le gel garde une
    copie complète de la base à l'instant de l'analyse et l'enregistre.
    """
    fichier = base.sauvegarder(motif=f"gel-{motif}" if motif else "gel")
    gel = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "motif": motif,
        "fichier": str(fichier),
        "nb_sejours": base.une_ligne(
            "SELECT COUNT(*) AS n FROM sejour WHERE supprime = 0"
        )["n"],
    }
    base.inserer(
        "journal",
        {
            "date_heure": gel["date"],
            "utilisateur_id": utilisateur_id,
            "table_cible": "base",
            "ligne_id": fichier.name,
            "action": "gel",
            "details": json.dumps(gel, ensure_ascii=False),
        },
    )
    return gel
