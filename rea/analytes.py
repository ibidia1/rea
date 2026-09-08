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
    # Codes standards (feuille de route §5) : ils ne coûtent rien à stocker et
    # valent tout à l'analyse. Le LOINC identifie l'examen, l'UCUM normalise
    # l'unité — c'est lui qui empêche de confondre µmol/L et mg/L.
    #
    # ⚠️ Ces correspondances sont une PROPOSITION, pas une source validée
    # (question ouverte B de la feuille de route : « source des fichiers CIM-10,
    # LOINC et ATC ? »). Tant que `LOINC_VALIDE` est faux, l'export doit les
    # marquer comme provisoires plutôt que de les présenter comme sûrs.
    code_loinc: str | None = None
    unite_ucum: str | None = None
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
        Analyte("hb", "Hb", "g/dL", borne_basse=12, borne_haute=17, code_loinc="718-7", unite_ucum="g/dL"),
        Analyte("hte", "Hématocrite", "%", borne_basse=36, borne_haute=50, code_loinc="4544-3", unite_ucum="%"),
        Analyte("plq", "PLQ", "10³/µL", borne_basse=150, borne_haute=400, code_loinc="777-3", unite_ucum="10*3/uL"),
        Analyte("gb", "GB", "10³/µL", borne_basse=4, borne_haute=10, code_loinc="6690-2", unite_ucum="10*3/uL"),
    )),
    GroupeAnalytes("hemostase", "Hémostase", (
        Analyte("tp", "TP", "%", borne_basse=70, borne_haute=100, code_loinc="5894-1", unite_ucum="%"),
        Analyte("inr", "INR", "", borne_basse=0.8, borne_haute=1.2, code_loinc="6301-6", unite_ucum="1"),
        Analyte("tca", "TCA", "s", borne_basse=25, borne_haute=38, code_loinc="14979-9", unite_ucum="s"),
    )),
    GroupeAnalytes("ionogramme", "Ionogramme", (
        Analyte("na", "Na⁺", "mmol/L", borne_basse=135, borne_haute=145, code_loinc="2951-2", unite_ucum="mmol/L"),
        Analyte("k", "K⁺", "mmol/L", borne_basse=3.5, borne_haute=5.0, code_loinc="2823-3", unite_ucum="mmol/L"),
        Analyte("cl", "Cl⁻", "mmol/L", borne_basse=98, borne_haute=107, code_loinc="2075-0", unite_ucum="mmol/L"),
        Analyte("ca", "Ca²⁺", "mmol/L", borne_basse=2.2, borne_haute=2.6, code_loinc="17861-6", unite_ucum="mmol/L"),
        Analyte("mg", "Mg²⁺", "mmol/L", borne_basse=0.7, borne_haute=1.0, code_loinc="19123-9", unite_ucum="mmol/L"),
        Analyte("phosphore", "Phosphore", "mmol/L", borne_basse=0.8, borne_haute=1.5,
                code_loinc="2777-1", unite_ucum="mmol/L"),
        # Bicarbonate veineux (ionogramme) — distinct du HCO₃⁻ artériel posé
        # avec chaque gaz du sang (table gaz_du_sang) : deux prélèvements
        # différents, jamais la même valeur recopiée.
        Analyte("hco3_iono", "HCO₃⁻", "mmol/L", borne_basse=22, borne_haute=28,
                code_loinc="1963-8", unite_ucum="mmol/L"),
    )),
    GroupeAnalytes("metabolique", "Métabolique", (
        # Exigées par l'alignement ANZICS (SPEC §9.5) et indispensables aux
        # corrections calculées : natrémie à la glycémie, calcémie à l'albumine.
        Analyte("glycemie", "Glycémie", "mmol/L", borne_basse=3.9, borne_haute=7.8,
                code_loinc="14749-6", unite_ucum="mmol/L"),
        Analyte("albumine", "Albumine", "g/L", borne_basse=35, borne_haute=50,
                code_loinc="1751-7", unite_ucum="g/L"),
    )),
    GroupeAnalytes("renale", "Fonction rénale", (
        Analyte("creat", "Créatinine", "µmol/L", borne_basse=60, borne_haute=110, code_loinc="14682-9", unite_ucum="umol/L"),
        Analyte("uree", "Urée", "mmol/L", borne_basse=2.5, borne_haute=7.5, code_loinc="22664-7", unite_ucum="mmol/L"),
    )),
    GroupeAnalytes("inflammation", "Inflammation", (
        Analyte("crp", "CRP", "mg/L", borne_haute=5, code_loinc="1988-5", unite_ucum="mg/L"),
        # La PCT était demandable (referentiels/examens_a_demander.json) sans
        # être saisissable : le résultat revenait du laboratoire et n'avait nulle
        # part où s'écrire. Elle a sa ligne au bilan infectieux, avec la CRP
        # (demande du service, 8 septembre).
        Analyte("pct", "PCT", "µg/L", borne_haute=0.5, code_loinc="33959-8",
                unite_ucum="ug/L"),
    )),
    GroupeAnalytes("hepatique", "Bilan hépatique", (
        Analyte("asat", "ASAT", "UI/L", borne_haute=40, code_loinc="1920-8", unite_ucum="U/L"),
        Analyte("alat", "ALAT", "UI/L", borne_haute=40, code_loinc="1742-6", unite_ucum="U/L"),
        Analyte("ggt", "GGT", "UI/L", borne_haute=55, code_loinc="2324-2", unite_ucum="U/L"),
        Analyte("pal", "PAL", "UI/L", borne_haute=130, code_loinc="6768-6", unite_ucum="U/L"),
        Analyte("bili", "Bili totale", "µmol/L", borne_haute=21, code_loinc="1975-2", unite_ucum="umol/L"),
        Analyte("bili_d", "Bili directe", "µmol/L", borne_haute=5, code_loinc="1968-7", unite_ucum="umol/L"),
        Analyte("bili_i", "Bili indirecte", "µmol/L", calcule=True, code_loinc="1971-1", unite_ucum="umol/L"),
    )),
    GroupeAnalytes("lipidique", "Bilan lipidique", (
        # Stockées en mmol/L (unité canonique) — la saisie en g/L n'est
        # qu'une bascule d'affichage, convertie avant enregistrement.
        Analyte("ct", "CT", "mmol/L", code_loinc="2093-3", unite_ucum="mmol/L"),
        Analyte("hdl", "HDL-c", "mmol/L", code_loinc="2085-9", unite_ucum="mmol/L"),
        Analyte("ldl", "LDL-c", "mmol/L", code_loinc="2089-1", unite_ucum="mmol/L"),
        Analyte("tg", "TG", "mmol/L", code_loinc="2571-8", unite_ucum="mmol/L"),
    )),
)

# Ordre de saisie à l'écran, demandé par le service (8 septembre). Le gaz du
# sang est traité à part, avant tout le reste : c'est le seul bilan qu'on
# refait plusieurs fois dans la journée. Viennent ensuite la chimie, puis
# l'hémato ; ce qui ne se demande pas tous les jours passe derrière, replié.
#
# Cet ordre ne vaut que pour la saisie : `GROUPES` garde l'ordre du catalogue,
# celui de la cinétique et des exports.
ORDRE_SAISIE: tuple[str, ...] = (
    "ionogramme", "metabolique", "renale", "inflammation",   # chimie
    "nfs", "hemostase",                                      # hémato
)
GROUPES_OCCASIONNELS: tuple[str, ...] = ("hepatique", "lipidique")


def groupes_de_saisie() -> tuple[tuple[GroupeAnalytes, ...], tuple[GroupeAnalytes, ...]]:
    """(groupes courants, groupes non systématiques), dans l'ordre de saisie.

    Un groupe ajouté au catalogue et oublié dans les deux listes ci-dessus
    n'est jamais perdu de vue : il rejoint les non systématiques, replié mais
    saisissable — un analyte qu'on ne peut plus taper vaut un analyte perdu.
    """
    par_code = {g.code: g for g in GROUPES}
    courants = tuple(par_code[c] for c in ORDRE_SAISIE if c in par_code)
    occasionnels = tuple(par_code[c] for c in GROUPES_OCCASIONNELS if c in par_code)
    connus = {g.code for g in courants + occasionnels}
    return courants, occasionnels + tuple(g for g in GROUPES if g.code not in connus)


# Les correspondances LOINC ci-dessus n'ont pas encore été vérifiées contre le
# référentiel officiel. Mettre à True le jour où un senior ou une source
# officielle les a relues, ligne à ligne.
LOINC_VALIDE = False
VERSION_CATALOGUE = "2026-09-03-provisoire"

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
