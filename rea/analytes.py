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
    # Bornes usuelles de l'adulte, servant UNIQUEMENT à colorer une valeur
    # hors norme dans la vue de cinétique. Question ouverte 8 : à valider par
    # un senior avant de s'y fier. Aucune décision clinique n'en dépend.
    borne_basse: float | None = None
    borne_haute: float | None = None

    def hors_bornes(self, valeur: float | None) -> str | None:
        """'bas', 'haut', ou None. None aussi quand aucune borne n'est
        définie — on ne signale jamais ce qu'on ne sait pas juger."""
        if valeur is None:
            return None
        if self.borne_basse is not None and valeur < self.borne_basse:
            return "bas"
        if self.borne_haute is not None and valeur > self.borne_haute:
            return "haut"
        return None


@dataclass(frozen=True)
class GroupeAnalytes:
    code: str
    titre: str
    analytes: tuple[Analyte, ...]


GROUPES: tuple[GroupeAnalytes, ...] = (
    GroupeAnalytes("nfs", "NFS", (
        Analyte("hb", "Hb", "g/dL", borne_basse=12, borne_haute=17),
        Analyte("hte", "Hématocrite", "%", borne_basse=36, borne_haute=50),
        Analyte("plq", "PLQ", "10³/µL", borne_basse=150, borne_haute=400),
        Analyte("gb", "GB", "10³/µL", borne_basse=4, borne_haute=10),
    )),
    GroupeAnalytes("hemostase", "Hémostase", (
        Analyte("tp", "TP", "%", borne_basse=70, borne_haute=100),
        Analyte("inr", "INR", "", borne_basse=0.8, borne_haute=1.2),
        Analyte("tca", "TCA", "s", borne_basse=25, borne_haute=38),
    )),
    GroupeAnalytes("ionogramme", "Ionogramme", (
        Analyte("na", "Na⁺", "mmol/L", borne_basse=135, borne_haute=145),
        Analyte("k", "K⁺", "mmol/L", borne_basse=3.5, borne_haute=5.0),
        Analyte("cl", "Cl⁻", "mmol/L", borne_basse=98, borne_haute=107),
        Analyte("ca", "Ca²⁺", "mmol/L", borne_basse=2.2, borne_haute=2.6),
    )),
    GroupeAnalytes("renale", "Fonction rénale", (
        Analyte("creat", "Créatinine", "µmol/L", borne_basse=60, borne_haute=110),
        Analyte("uree", "Urée", "mmol/L", borne_basse=2.5, borne_haute=7.5),
    )),
    GroupeAnalytes("inflammation", "Inflammation", (
        Analyte("crp", "CRP", "mg/L", borne_haute=5),
    )),
    GroupeAnalytes("hepatique", "Bilan hépatique", (
        Analyte("asat", "ASAT", "UI/L", borne_haute=40),
        Analyte("alat", "ALAT", "UI/L", borne_haute=40),
        Analyte("ggt", "GGT", "UI/L", borne_haute=55),
        Analyte("pal", "PAL", "UI/L", borne_haute=130),
        Analyte("bili", "Bili totale", "µmol/L", borne_haute=21),
        Analyte("bili_d", "Bili directe", "µmol/L", borne_haute=5),
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
