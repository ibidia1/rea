"""Catalogue des analytes de bilan (SPEC §7).

Reprend directement la structure du fichier HTML de saisie des bilans déjà
utilisé au service (fourni le 2 septembre 2026) : mêmes groupes, mêmes
libellés, même unité, même regroupement dans le texte généré. Le gaz du
sang et la ventilation ont leur propre table (`gaz_du_sang`, SPEC §7.3) —
ils ne sont pas dans ce catalogue.

Ajouter un analyte : une ligne dans le groupe concerné, rien d'autre à
changer — le formulaire, le stockage et le texte généré suivent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Analyte:
    id: str
    libelle: str
    unite: str
    calcule: bool = False  # dérivé d'autres valeurs, jamais saisi directement


@dataclass(frozen=True)
class GroupeAnalytes:
    code: str
    titre: str
    analytes: tuple[Analyte, ...]


GROUPES: tuple[GroupeAnalytes, ...] = (
    GroupeAnalytes("nfs", "NFS", (
        Analyte("hb", "Hb", "g/dL"),
        Analyte("hte", "Hématocrite", "%"),
        Analyte("plq", "PLQ", "10³/µL"),
        Analyte("gb", "GB", "10³/µL"),
    )),
    GroupeAnalytes("hemostase", "Hémostase", (
        Analyte("tp", "TP", "%"),
        Analyte("inr", "INR", ""),
        Analyte("tca", "TCA", "s"),
    )),
    GroupeAnalytes("ionogramme", "Ionogramme", (
        Analyte("na", "Na⁺", "mmol/L"),
        Analyte("k", "K⁺", "mmol/L"),
        Analyte("cl", "Cl⁻", "mmol/L"),
        Analyte("ca", "Ca²⁺", "mmol/L"),
    )),
    GroupeAnalytes("renale", "Fonction rénale", (
        Analyte("creat", "Créatinine", "µmol/L"),
        Analyte("uree", "Urée", "mmol/L"),
    )),
    GroupeAnalytes("inflammation", "Inflammation", (
        Analyte("crp", "CRP", "mg/L"),
    )),
    GroupeAnalytes("hepatique", "Bilan hépatique", (
        Analyte("asat", "ASAT", "UI/L"),
        Analyte("alat", "ALAT", "UI/L"),
        Analyte("ggt", "GGT", "UI/L"),
        Analyte("pal", "PAL", "UI/L"),
        Analyte("bili", "Bili totale", "µmol/L"),
        Analyte("bili_d", "Bili directe", "µmol/L"),
        Analyte("bili_i", "Bili indirecte", "µmol/L", calcule=True),
    )),
    GroupeAnalytes("lipidique", "Bilan lipidique", (
        # Stockées en mmol/L (unité canonique) — la saisie en g/L n'est
        # qu'une bascule d'affichage, convertie avant enregistrement.
        Analyte("ct", "CT", "mmol/L"),
        Analyte("hdl", "HDL-c", "mmol/L"),
        Analyte("ldl", "LDL-c", "mmol/L"),
        Analyte("tg", "TG", "mmol/L"),
    )),
)

# Facteurs de conversion mmol/L -> g/L (identiques au fichier HTML fourni).
FACTEURS_LIPIDES: dict[str, float] = {"ct": 0.387, "hdl": 0.387, "ldl": 0.387, "tg": 0.886}

# Regroupement utilitaire : id d'analyte -> (groupe, Analyte)
_INDEX: dict[str, tuple[GroupeAnalytes, Analyte]] = {
    analyte.id: (groupe, analyte) for groupe in GROUPES for analyte in groupe.analytes
}


def analyte(id_: str) -> Analyte:
    return _INDEX[id_][1]


def groupe_de(id_: str) -> GroupeAnalytes:
    return _INDEX[id_][0]


def tous_les_ids(inclure_calcules: bool = True) -> tuple[str, ...]:
    return tuple(
        a.id for g in GROUPES for a in g.analytes if inclure_calcules or not a.calcule
    )


MODES_VENTILATOIRES = ("VAC", "VS AI", "Masque", "Lunette", "Air ambiant")
MODES_AVEC_DEBIT = ("Masque", "Lunette")
