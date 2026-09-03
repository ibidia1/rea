"""Contrôles de cohérence à la saisie (feuille de route, bloc 4).

Le meilleur ratio de la feuille de route : deux heures qui valent plus, pour la
qualité de la base, que vingt heures de statistiques plus tard. On ne rattrape
pas une donnée fausse saisie il y a huit mois.

**Un avertissement n'est jamais un blocage.** Le médecin peut toujours forcer ;
la valeur forcée est marquée comme telle en base (`saisie_forcee`), pour qu'un
relecteur puisse la retrouver.

Couche C2, fonctions pures : aucune lecture de base, aucun accès réseau, rien à
afficher. Elles reçoivent des valeurs et rendent des avertissements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .. import analytes as cat
from .dates import parse_date


@dataclass(frozen=True)
class Avertissement:
    champ: str
    message: str
    # 'improbable' : physiologiquement douteux, souvent une faute de frappe.
    # 'impossible' : logiquement faux, comme une sortie avant l'admission.
    gravite: str = "improbable"


# --------------------------------------------------------------------------
# Bornes physiologiques — à distinguer des bornes usuelles
# --------------------------------------------------------------------------
# Les bornes usuelles (rea/analytes.py) disent « anormal » : une kaliémie à 6,2
# est hors normes mais parfaitement réelle. Celles-ci disent « impossible chez
# un patient vivant » : une kaliémie à 45 est une faute de frappe ou une erreur
# d'unité. Deux notions différentes, deux jeux de bornes.
BORNES_PHYSIOLOGIQUES: dict[str, tuple[float, float]] = {
    "hb": (2, 25),
    "hte": (5, 70),
    "plq": (1, 2000),
    "gb": (0.1, 200),
    "tp": (1, 130),
    "inr": (0.5, 20),
    "tca": (10, 300),
    "na": (90, 200),
    "k": (1, 10),
    "cl": (60, 160),
    "ca": (1, 5),
    "creat": (10, 2500),
    "uree": (0.5, 100),
    "crp": (0, 600),
    "asat": (1, 20000),
    "alat": (1, 20000),
    "ggt": (1, 5000),
    "pal": (1, 5000),
    "bili": (0, 900),
    "bili_d": (0, 900),
    "ct": (0.5, 20),
    "hdl": (0.1, 5),
    "ldl": (0.1, 15),
    "tg": (0.1, 30),
}

# Gaz du sang et ventilation : mêmes bornes « patient vivant ».
BORNES_GAZ: dict[str, tuple[float, float]] = {
    "ph": (6.5, 8.0),
    "pao2": (10, 700),
    "paco2": (5, 200),
    "hco3": (2, 60),
    "lactate": (0, 40),
    "fio2": (21, 100),
    "pep": (0, 30),
    "fr": (1, 80),
    "spo2": (10, 100),
}


def verifier_bilan(valeurs: dict[str, float | None]) -> list[Avertissement]:
    """Valeurs de bilan hors bornes physiologiques — typiquement une virgule
    déplacée ou une unité confondue."""
    avertissements = []
    for id_analyte, valeur in valeurs.items():
        if valeur is None:
            continue
        bornes = BORNES_PHYSIOLOGIQUES.get(id_analyte)
        if not bornes:
            continue
        basse, haute = bornes
        if not (basse <= valeur <= haute):
            libelle = cat.analyte(id_analyte).libelle if id_analyte in cat._INDEX else id_analyte
            unite = cat.analyte(id_analyte).unite if id_analyte in cat._INDEX else ""
            avertissements.append(
                Avertissement(
                    id_analyte,
                    f"{libelle} à {valeur} {unite} — attendu entre {basse} et {haute}. "
                    "Erreur de frappe ou d'unité ?",
                )
            )
    return avertissements


def verifier_gaz_du_sang(valeurs: dict[str, float | None]) -> list[Avertissement]:
    avertissements = []
    for champ, valeur in valeurs.items():
        if valeur is None:
            continue
        bornes = BORNES_GAZ.get(champ)
        if not bornes:
            continue
        basse, haute = bornes
        if not (basse <= valeur <= haute):
            avertissements.append(
                Avertissement(champ, f"{champ} à {valeur} — attendu entre {basse} et {haute}.")
            )
    return avertissements


# --------------------------------------------------------------------------
# Cohérence des dates — une date impossible est une erreur, pas une surprise
# --------------------------------------------------------------------------

def verifier_sejour(
    *,
    date_admission: str | date | None,
    date_sortie: str | date | None = None,
    date_naissance: str | date | None = None,
    aujourdhui: str | date | None = None,
) -> list[Avertissement]:
    avertissements = []
    admission = parse_date(date_admission)
    sortie = parse_date(date_sortie)
    naissance = parse_date(date_naissance)
    reference = parse_date(aujourdhui) or date.today()

    if admission and sortie and sortie < admission:
        avertissements.append(
            Avertissement("date_sortie", "La sortie précède l'admission.", "impossible")
        )
    if admission and admission > reference:
        avertissements.append(
            Avertissement("date_admission", "L'admission est dans le futur.", "impossible")
        )
    if naissance:
        if naissance > reference:
            avertissements.append(
                Avertissement("date_naissance", "La naissance est dans le futur.", "impossible")
            )
        else:
            age = (reference - naissance).days // 365
            if age > 120:
                avertissements.append(
                    Avertissement("date_naissance", f"Âge calculé de {age} ans.")
                )
        if admission and naissance > admission:
            avertissements.append(
                Avertissement(
                    "date_naissance", "La naissance suit l'admission.", "impossible"
                )
            )
    return avertissements


def verifier_dispositif(
    *,
    date_pose: str | date | None,
    date_retrait: str | date | None = None,
    date_admission: str | date | None = None,
    aujourdhui: str | date | None = None,
) -> list[Avertissement]:
    """Le cas cité par la feuille de route : extubation avant l'intubation."""
    avertissements = []
    pose = parse_date(date_pose)
    retrait = parse_date(date_retrait)
    admission = parse_date(date_admission)
    reference = parse_date(aujourdhui) or date.today()

    if pose and retrait and retrait < pose:
        avertissements.append(
            Avertissement("date_retrait", "Le retrait précède la pose.", "impossible")
        )
    if pose and pose > reference:
        avertissements.append(
            Avertissement("date_pose", "La pose est dans le futur.", "impossible")
        )
    if pose and admission and pose < admission:
        avertissements.append(
            Avertissement("date_pose", "La pose précède l'admission en réanimation.")
        )
    return avertissements


def verifier_prescription(
    *,
    date_debut: str | date | None,
    duree_prevue_jours: int | None = None,
    dose: float | None = None,
    vitesse: float | None = None,
    volume_24h: float | None = None,
    date_admission: str | date | None = None,
) -> list[Avertissement]:
    avertissements = []
    debut = parse_date(date_debut)
    admission = parse_date(date_admission)

    if debut and admission and debut < admission:
        avertissements.append(
            Avertissement("date_debut", "La prescription commence avant l'admission.")
        )
    if duree_prevue_jours is not None and duree_prevue_jours > 60:
        avertissements.append(
            Avertissement("duree_prevue_jours", f"Durée prévue de {duree_prevue_jours} jours.")
        )
    if dose is not None and dose > 10000:
        avertissements.append(
            Avertissement("dose", f"Dose de {dose} — erreur d'unité ?")
        )
    if vitesse is not None and vitesse > 500:
        avertissements.append(
            Avertissement("vitesse", f"Vitesse de {vitesse} cc/h.")
        )
    if volume_24h is not None and volume_24h > 10000:
        avertissements.append(
            Avertissement("volume_24h", f"Volume de {volume_24h} mL sur 24 h.")
        )
    return avertissements


def resume(avertissements: list[Avertissement]) -> str:
    return " · ".join(a.message for a in avertissements)
