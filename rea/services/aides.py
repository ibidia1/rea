"""Les faits sur lesquels les règles d'aide sont évaluées (bloc 7).

Ce module ne décide rien : il rassemble, à une date donnée, ce que le dossier
sait déjà du patient — combien de jours de tel dispositif, la dernière
kaliémie, ce qui est prescrit. Le jugement, lui, est écrit dans `regles/*.json`
et appliqué par `domaine/regles.py`.

Séparer les deux est ce qui rend la règle R4 tenable : tant que les faits sont
ici et les seuils là-bas, changer un seuil ne demande pas de programmeur.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from .. import aides as fichiers_regles
from .. import referentiels
from ..db import Base
from ..domaine import calculs, regles as moteur
from ..domaine.dates import age_ans, parse_date
from . import bilans as bilans_service
from . import dispositifs as dispositifs_service
from . import evolution as evolution_service
from . import prescriptions as prescriptions_service

# Analytes repris comme faits, sous un nom lisible dans les fichiers de règles.
_ANALYTES_SUIVIS = {
    "k": "kaliemie",
    "na": "natremie",
    "hb": "hemoglobine",
    "plq": "plaquettes",
    "creat": "creatinine",
    "glycemie": "glycemie_du_jour",
    "crp": "crp",
}


def _sans_accent(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if unicodedata.category(c) != "Mn"
    )


def _familles_prescrites(lignes: list[dict]) -> set[str]:
    """Quelles familles de médicaments sont représentées dans le prescrit.

    Reconnaissance par fragment de nom, à partir d'un référentiel modifiable
    (`familles_medicaments.json`). C'est volontairement grossier : ça sert à
    cocher une check-list, jamais à déduire une dose ni une contre-indication.
    """
    familles = referentiels.charger("familles_medicaments")
    libelles = [_sans_accent(l.get("produit") or "") for l in lignes]
    trouvees = set()
    for famille, fragments in familles.items():
        if any(f in libelle for libelle in libelles for f in fragments):
            trouvees.add(famille)
    return trouvees


def faits(base: Base, sejour_id: str, date_jour: str | None = None) -> dict:
    """Tout ce que les règles peuvent interroger, à une date donnée."""
    jour = date_jour or date.today().isoformat()
    sejour = base.une_ligne(
        "SELECT s.*, p.date_naissance, p.sexe FROM sejour s "
        "JOIN patient p ON p.id = s.patient_id WHERE s.id = ?",
        (sejour_id,),
    )
    if sejour is None:
        return {}

    f: dict = {}

    # -- dispositifs : les compteurs de jours, déjà calculés ailleurs --------
    etats = {e.type: e for e in dispositifs_service.etats(base, sejour_id, jour)}
    en_place = {t: e for t, e in etats.items() if e.en_place}
    for type_, cle in (
        ("intubation", "jours_intubation"),
        ("sedation", "jours_sedation"),
        ("kt_central", "jours_kt_central"),
        ("kta", "jours_kta"),
        ("sonde_urinaire", "jours_sonde_urinaire"),
        ("sng", "jours_sng"),
        ("eer", "jours_eer"),
    ):
        f[cle] = en_place[type_].jour if type_ in en_place else None
    for type_ in ("sng", "tracheotomie", "intubation", "sedation", "kt_central",
                  "kta", "sonde_urinaire", "eer", "gastrostomie"):
        f[f"{type_}_en_place"] = type_ in en_place
    f["ventile"] = "intubation" in en_place or "tracheotomie" in en_place

    # -- séjour --------------------------------------------------------------
    admission = parse_date(sejour["date_admission"])
    reference = parse_date(jour)
    f["jour_hospitalisation"] = (
        (reference - admission).days + 1 if admission and reference else None
    )
    f["age"] = age_ans(sejour.get("date_naissance"), jour)
    f["poids_kg"] = sejour.get("poids_kg")
    f["sortie_prononcee"] = bool(sejour.get("date_heure_sortie"))

    # -- biologie ------------------------------------------------------------
    resultats = bilans_service.resultats_du_sejour(base, sejour_id)
    derniers: dict[str, float] = {}
    for ligne in resultats:
        if ligne["date_heure"][:10] <= jour and ligne["valeur_num"] is not None:
            derniers[ligne["analyte"]] = ligne["valeur_num"]
    for id_analyte, nom in _ANALYTES_SUIVIS.items():
        f[nom] = derniers.get(id_analyte)
    dates = [l["date_heure"][:10] for l in resultats if l["date_heure"][:10] <= jour]
    if dates and reference:
        f["jours_depuis_bilan"] = (reference - parse_date(max(dates))).days
    else:
        f["jours_depuis_bilan"] = None

    gaz = bilans_service.dernier_gaz_du_sang(base, sejour_id) or {}
    calculees = {
        v.cle: v.valeur
        for v in calculs.toutes_les_valeurs(
            resultats=derniers,
            gaz=gaz,
            poids_kg=sejour.get("poids_kg"),
            taille_cm=sejour.get("taille_cm"),
            age_ans=f["age"],
            sexe=sejour.get("sexe"),
        )
    }
    f["clairance"] = calculees.get("clairance_cg")
    f["pao2_fio2"] = calculees.get("pf")

    # -- évolution du jour ---------------------------------------------------
    elements = evolution_service.elements_du_jour(base, sejour_id, jour)
    f["rass"] = elements.get("rass")
    f["glasgow"] = elements.get("glasgow")
    f["temperature"] = elements.get("temperature")
    f["tete_de_lit_surelevee"] = (
        None if elements.get("tete_de_lit") in (None, "non_renseigne")
        else elements.get("tete_de_lit") == "oui"
    )
    f["nb_escarres"] = len(evolution_service.escarres(base, sejour_id, actives_seulement=True))

    # -- prescrit ------------------------------------------------------------
    lignes = prescriptions_service.lignes_actives_le(base, sejour_id, jour)
    familles = _familles_prescrites(lignes)
    f["analgesie_prescrite"] = "analgesie" in familles
    f["thromboprophylaxie_prescrite"] = "thromboprophylaxie" in familles
    f["prophylaxie_ulcere_prescrite"] = "prophylaxie_ulcere" in familles
    f["insuline_prescrite"] = "insuline" in familles
    f["nutrition_prescrite"] = "nutrition" in familles or any(
        (l.get("sous_type") or "").startswith("nutrition") for l in lignes
    )
    f["nb_lignes_prescrites"] = len(lignes)
    return f


def rappels(base: Base, sejour_id: str, date_jour: str | None = None) -> list[dict]:
    """Les rappels déclenchés, message déjà mis en forme."""
    donnees = faits(base, sejour_id, date_jour)
    declenchees = moteur.declenchees(fichiers_regles.toutes_les_regles(), donnees)
    return [
        {
            "code": r.code,
            "libelle": r.libelle,
            "message": _formater(r.message, donnees),
            "gravite": r.gravite,
            "source": r.source,
            "valide": r.valide,
        }
        for r in declenchees
    ]


def checklist(base: Base, sejour_id: str, date_jour: str | None = None) -> list:
    fichier = fichiers_regles.checklist()
    return moteur.evaluer_checklist(
        fichier.get("items", ()), faits(base, sejour_id, date_jour)
    )


def _formater(message: str, donnees: dict) -> str:
    """Remplace {fait} par sa valeur. Un fait manquant laisse le texte tel
    quel plutôt que de faire tomber l'écran."""
    try:
        return message.format(**{k: _joli(v) for k, v in donnees.items()})
    except (KeyError, IndexError, ValueError):
        return message


def _joli(valeur):
    if isinstance(valeur, float):
        texte = f"{valeur:.2f}".rstrip("0").rstrip(".")
        return texte.replace(".", ",")
    return valeur
