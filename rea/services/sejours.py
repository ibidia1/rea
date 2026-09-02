"""Écrans 2 (Admission) et 7 (Sortie) — SPEC §4.1 à §4.7."""

from __future__ import annotations

from datetime import date

from .. import listes
from ..db import Base, maintenant, nouvel_id


# --------------------------------------------------------------------------
# Identité et admission
# --------------------------------------------------------------------------

def creer_patient(
    base: Base,
    *,
    matricule: str,
    nom_affichage: str,
    date_naissance: str | None,
    sexe: str = "non_renseigne",
    utilisateur_id: str | None = None,
    non_identifie: bool = False,
) -> str:
    return base.inserer(
        "patient",
        {
            "matricule": matricule,
            "nom_affichage": nom_affichage,
            "date_naissance": date_naissance,
            "sexe": sexe,
            "non_identifie": int(non_identifie),
            "identifiant_etude": _nouvel_identifiant_etude(base),
        },
        utilisateur_id=utilisateur_id,
    )


def _nouvel_identifiant_etude(base: Base) -> str:
    """Identifiant stable, sans lien direct avec le matricule (règle de
    conception 8 — export recherche pseudonymisé automatiquement)."""
    n = base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"] + 1
    return f"ETU-{n:05d}"


def prochain_matricule_non_identifie(base: Base) -> str:
    """SPEC §4.1 : `XXX-{date}-{n}`."""
    aujourdhui = date.today().strftime("%Y%m%d")
    n = base.une_ligne(
        "SELECT COUNT(*) AS n FROM patient WHERE matricule LIKE ?",
        (f"XXX-{aujourdhui}-%",),
    )["n"] + 1
    return f"XXX-{aujourdhui}-{n}"


def creer_sejour(
    base: Base,
    *,
    patient_id: str,
    date_admission: str,
    lit_admission: int,
    provenance_type: str | None = None,
    provenance_detail: str | None = None,
    est_readmission: bool = False,
    motif_readmission: str | None = None,
    traumatique: bool | None = None,
    mecanisme: str | None = None,
    mecanisme_detail: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    numero = base.une_ligne(
        "SELECT COUNT(*) AS n FROM sejour WHERE patient_id = ?", (patient_id,)
    )["n"] + 1
    return base.inserer(
        "sejour",
        {
            "patient_id": patient_id,
            "numero_sejour": numero,
            "date_admission": date_admission,
            "lit_admission": lit_admission,
            "provenance_type": provenance_type,
            "provenance_detail": provenance_detail,
            "est_readmission": int(est_readmission),
            "motif_readmission": motif_readmission,
            "traumatique": None if traumatique is None else int(traumatique),
            "mecanisme": mecanisme,
            "mecanisme_detail": mecanisme_detail,
            "complication_statut": "non_renseigne",
        },
        utilisateur_id=utilisateur_id,
    )


def sejour_avec_patient(base: Base, sejour_id: str) -> dict | None:
    return base.une_ligne(
        """
        SELECT s.*, p.nom_affichage, p.date_naissance, p.matricule, p.sexe,
               p.traitement_habituel, p.sans_antecedent_connu
        FROM sejour s JOIN patient p ON p.id = s.patient_id
        WHERE s.id = ?
        """,
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Motif traumatique — régions et statut polytraumatisé (SPEC §4.3)
# --------------------------------------------------------------------------

def definir_regions_traumatiques(
    base: Base, sejour_id: str, regions: list[str], *, utilisateur_id: str | None = None
) -> None:
    base.executer(
        "UPDATE sejour_region_trauma SET supprime = 1 WHERE sejour_id = ?", (sejour_id,)
    )
    for region in regions:
        base.executer(
            "UPDATE sejour_region_trauma SET supprime = 0 WHERE sejour_id = ? AND region = ?",
            (sejour_id, region),
        )
        existe = base.une_ligne(
            "SELECT id FROM sejour_region_trauma WHERE sejour_id = ? AND region = ?",
            (sejour_id, region),
        )
        if not existe:
            base.inserer(
                "sejour_region_trauma",
                {"sejour_id": sejour_id, "region": region},
                utilisateur_id=utilisateur_id,
            )


def regions_traumatiques(base: Base, sejour_id: str) -> list[str]:
    lignes = base.requete(
        "SELECT region FROM sejour_region_trauma WHERE sejour_id = ? AND supprime = 0",
        (sejour_id,),
    )
    return [l["region"] for l in lignes]


def est_polytraumatise(base: Base, sejour_id: str) -> bool:
    """Calculé automatiquement, jamais saisi (SPEC §4.3) : >= 2 régions."""
    return len(regions_traumatiques(base, sejour_id)) >= 2


# --------------------------------------------------------------------------
# Motif non traumatique (SPEC §4.4)
# --------------------------------------------------------------------------

def definir_motifs(
    base: Base,
    sejour_id: str,
    *,
    motif_principal: str,
    motifs_associes: list[str] | None = None,
    precisions: dict[str, dict] | None = None,
    utilisateur_id: str | None = None,
) -> None:
    import json

    base.executer("UPDATE sejour_motif SET supprime = 1 WHERE sejour_id = ?", (sejour_id,))
    precisions = precisions or {}
    tous = [(motif_principal, True)] + [(m, False) for m in (motifs_associes or [])]
    for code, principal in tous:
        base.inserer(
            "sejour_motif",
            {
                "sejour_id": sejour_id,
                "code": code,
                "principal": int(principal),
                "donnees": json.dumps(precisions.get(code, {}), ensure_ascii=False),
            },
            utilisateur_id=utilisateur_id,
        )


def motifs_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM sejour_motif WHERE sejour_id = ? AND supprime = 0 ORDER BY principal DESC",
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Antécédents (SPEC §4.2) — attachés au patient
# --------------------------------------------------------------------------

def ajouter_antecedent(
    base: Base,
    *,
    patient_id: str,
    categorie: str,
    libelle: str,
    code: str | None = None,
    code_icd10: str | None = None,
    precision: str | None = None,
    statut: str = "present",
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "antecedent",
        {
            "patient_id": patient_id,
            "categorie": categorie,
            "code": code,
            "libelle": libelle,
            "code_icd10": code_icd10,
            "precision": precision,
            "statut": statut,
        },
        utilisateur_id=utilisateur_id,
    )


def antecedents_du_patient(base: Base, patient_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM antecedent WHERE patient_id = ? AND supprime = 0 ORDER BY cree_le",
        (patient_id,),
    )


def allergies_du_patient(base: Base, patient_id: str) -> list[dict]:
    """Affichées en alerte rouge en haut de la pancarte (SPEC §4.2)."""
    return [
        a
        for a in antecedents_du_patient(base, patient_id)
        if a["categorie"] == "allergie" and a["statut"] == "present"
    ]


# --------------------------------------------------------------------------
# Interventions chirurgicales (SPEC §4.6)
# --------------------------------------------------------------------------

def ajouter_intervention(
    base: Base,
    *,
    sejour_id: str,
    date_acte: str,
    geste: str,
    geste_detail: str | None = None,
    est_reprise: bool = False,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "intervention",
        {
            "sejour_id": sejour_id,
            "date_acte": date_acte,
            "geste": geste,
            "geste_detail": geste_detail,
            "est_reprise": int(est_reprise),
            "complication_statut": "non_renseigne",  # jamais "aucune" par défaut — SPEC §4.6
        },
        utilisateur_id=utilisateur_id,
    )


def interventions_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM intervention WHERE sejour_id = ? AND supprime = 0 ORDER BY date_acte",
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Changement de lit
# --------------------------------------------------------------------------

def changer_de_lit(
    base: Base, sejour_id: str, nouveau_lit: int, *, utilisateur_id: str | None = None
) -> None:
    en_cours = base.une_ligne(
        "SELECT id FROM sejour_lit WHERE sejour_id = ? AND date_fin IS NULL", (sejour_id,)
    )
    if en_cours:
        base.mettre_a_jour(
            "sejour_lit", en_cours["id"], {"date_fin": maintenant()}, utilisateur_id=utilisateur_id
        )
    base.inserer(
        "sejour_lit",
        {"sejour_id": sejour_id, "lit": nouveau_lit, "date_debut": maintenant()},
        utilisateur_id=utilisateur_id,
    )


# --------------------------------------------------------------------------
# Sortie (SPEC §4.7) — clôture le séjour et libère le lit
# --------------------------------------------------------------------------

def cloturer_sejour(
    base: Base,
    sejour_id: str,
    *,
    date_heure_sortie: str,
    mode_sortie: str,
    destination: str | None = None,
    meme_etablissement: bool | None = None,
    complication_statut: str = "non_renseigne",
    complication_texte: str | None = None,
    ordonnance_sortie: str | None = None,
    consultation_externe: str | None = None,
    deces_reanimation: bool | None = None,
    utilisateur_id: str | None = None,
) -> None:
    if mode_sortie == "deces" and deces_reanimation is None:
        deces_reanimation = True
    base.mettre_a_jour(
        "sejour",
        sejour_id,
        {
            "date_sortie": date_heure_sortie,
            "mode_sortie": mode_sortie,
            "destination": destination,
            "meme_etablissement": None if meme_etablissement is None else int(meme_etablissement),
            "complication_statut": complication_statut,
            "complication_texte": complication_texte,
            "ordonnance_sortie": ordonnance_sortie,
            "consultation_externe": consultation_externe,
            "deces_reanimation": None if deces_reanimation is None else int(deces_reanimation),
        },
        utilisateur_id=utilisateur_id,
        action="sortie",
    )
