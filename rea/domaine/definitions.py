"""Définitions standard appliquées aux données du service (bloc 15).

Trois définitions publiées, écrites une fois, appliquées de la même façon à
tous les séjours. C'est ce qui permet de dire « 34 SDRA » sans que personne
n'ait à demander « selon quels critères ? ».

Deux règles tenues partout ici :

* **Une définition non applicable n'est pas une définition négative.** Sans
  gaz du sang, on ne peut pas dire qu'il n'y a pas de SDRA ; la fonction rend
  alors `applicable = False`, et l'appelant ne doit pas la compter comme un cas
  négatif. C'est la règle des trois états, appliquée aux critères.
* **Ce que la donnée ne permet pas est dit, pas contourné.** Chaque résultat
  porte la liste de ce qui manquait pour trancher.

Couche C4, fonctions pures.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Verdict:
    """Le résultat d'une définition appliquée à un patient."""

    definition: str
    rempli: bool
    applicable: bool
    stade: str = ""
    criteres: tuple[str, ...] = ()
    manquants: tuple[str, ...] = field(default_factory=tuple)
    reference: str = ""

    @property
    def texte(self) -> str:
        if not self.applicable:
            return f"{self.definition} : non applicable (manque {', '.join(self.manquants)})"
        if not self.rempli:
            return f"{self.definition} : critères non remplis"
        return f"{self.definition} : {self.stade}" if self.stade else f"{self.definition} : oui"


_BERLIN = (
    "ARDS Definition Task Force. Acute respiratory distress syndrome: "
    "the Berlin Definition. JAMA 2012;307(23):2526-33."
)
_KDIGO = (
    "KDIGO Acute Kidney Injury Work Group. KDIGO clinical practice guideline "
    "for acute kidney injury. Kidney Int Suppl 2012;2(1):1-138."
)
_SEPSIS3 = (
    "Singer M, Deutschman CS, Seymour CW, et al. The Third International "
    "Consensus Definitions for Sepsis and Septic Shock (Sepsis-3). "
    "JAMA 2016;315(8):801-10."
)


def sdra_berlin(
    *,
    pao2_fio2: float | None,
    peep: float | None,
    ventile: bool | None,
    delai_jours: int | None = None,
    imagerie_bilaterale: bool | None = None,
    origine_cardiaque_exclue: bool | None = None,
) -> Verdict:
    """SDRA selon la définition de Berlin, et son stade.

        léger    200 < PaO₂/FiO₂ ≤ 300
        modéré   100 < PaO₂/FiO₂ ≤ 200
        sévère         PaO₂/FiO₂ ≤ 100
        avec PEP (ou CPAP pour le stade léger) ≥ 5 cmH₂O.

    Les critères de délai (≤ 7 jours), d'imagerie bilatérale et d'exclusion
    d'une origine cardiaque ne sont pas déductibles des données saisies : ils
    sont demandés à l'appelant, et leur absence rend la définition non
    applicable plutôt que faussement positive.
    """
    manquants = []
    if pao2_fio2 is None:
        manquants.append("PaO₂/FiO₂")
    if peep is None:
        manquants.append("PEP")
    if not ventile:
        manquants.append("support ventilatoire")
    if imagerie_bilaterale is None:
        manquants.append("imagerie bilatérale")
    if origine_cardiaque_exclue is None:
        manquants.append("exclusion d'une origine cardiaque")
    if delai_jours is None:
        manquants.append("délai depuis l'agression")
    if manquants:
        return Verdict("SDRA (Berlin)", False, False, manquants=tuple(manquants),
                       reference=_BERLIN)

    criteres = []
    if not imagerie_bilaterale or not origine_cardiaque_exclue or delai_jours > 7:
        return Verdict("SDRA (Berlin)", False, True, reference=_BERLIN)
    if peep < 5:
        return Verdict("SDRA (Berlin)", False, True,
                       criteres=("PEP < 5 cmH₂O",), reference=_BERLIN)

    if pao2_fio2 <= 100:
        stade = "sévère"
    elif pao2_fio2 <= 200:
        stade = "modéré"
    elif pao2_fio2 <= 300:
        stade = "léger"
    else:
        return Verdict("SDRA (Berlin)", False, True, reference=_BERLIN)
    criteres.append(f"PaO₂/FiO₂ = {pao2_fio2:g} avec PEP ≥ 5")
    return Verdict("SDRA (Berlin)", True, True, stade, tuple(criteres), reference=_BERLIN)


def ira_kdigo(
    *,
    creatinine: float | None,
    creatinine_base: float | None,
    diurese_ml_kg_h: float | None = None,
    duree_oligurie_h: float | None = None,
    epuration_en_cours: bool = False,
) -> Verdict:
    """Insuffisance rénale aiguë selon KDIGO, en µmol/L.

        stade 1  créatinine × 1,5 à 1,9  ou  hausse ≥ 26,5 µmol/L
        stade 2  créatinine × 2 à 2,9
        stade 3  créatinine × 3, ou ≥ 354 µmol/L, ou épuration extra-rénale

    Le critère de diurèse est pris en compte s'il est fourni. Sans créatinine
    de référence, le stade par créatinine n'est pas calculable — d'où la
    créatinine antérieure demandée à l'admission : elle ne se retrouve pas
    après coup.
    """
    if epuration_en_cours:
        return Verdict("IRA (KDIGO)", True, True, "stade 3",
                       ("épuration extra-rénale en cours",), reference=_KDIGO)

    stade = 0
    criteres = []
    manquants = []

    if creatinine is None:
        manquants.append("créatinine")
    elif creatinine_base is None:
        manquants.append("créatinine de référence")
    else:
        rapport = creatinine / creatinine_base
        hausse = creatinine - creatinine_base
        if rapport >= 3 or creatinine >= 354:
            stade = max(stade, 3)
            criteres.append(f"créatinine × {rapport:.1f}")
        elif rapport >= 2:
            stade = max(stade, 2)
            criteres.append(f"créatinine × {rapport:.1f}")
        elif rapport >= 1.5 or hausse >= 26.5:
            stade = max(stade, 1)
            criteres.append(
                f"créatinine × {rapport:.1f}" if rapport >= 1.5
                else f"hausse de {hausse:.0f} µmol/L"
            )

    if diurese_ml_kg_h is not None and duree_oligurie_h is not None:
        if diurese_ml_kg_h < 0.3 and duree_oligurie_h >= 24:
            stade = max(stade, 3)
            criteres.append("diurèse < 0,3 mL/kg/h ≥ 24 h")
        elif diurese_ml_kg_h < 0.5 and duree_oligurie_h >= 12:
            stade = max(stade, 2)
            criteres.append("diurèse < 0,5 mL/kg/h ≥ 12 h")
        elif diurese_ml_kg_h < 0.5 and duree_oligurie_h >= 6:
            stade = max(stade, 1)
            criteres.append("diurèse < 0,5 mL/kg/h ≥ 6 h")

    if stade == 0 and manquants:
        return Verdict("IRA (KDIGO)", False, False, manquants=tuple(manquants),
                       reference=_KDIGO)
    return Verdict("IRA (KDIGO)", stade > 0, True,
                   f"stade {stade}" if stade else "", tuple(criteres),
                   reference=_KDIGO)


def qsofa(
    *,
    frequence_respiratoire: float | None,
    pas: float | None,
    glasgow: float | None,
) -> Verdict:
    """qSOFA : FR ≥ 22, PAS ≤ 100 mmHg, Glasgow < 15. Deux critères sur trois
    signalent un risque, hors réanimation surtout.

    ⚠️ Le qSOFA est un signal d'alerte, **pas** la définition du sepsis : le
    sepsis se définit par une infection suspectée et une augmentation du SOFA
    d'au moins 2 points.
    """
    valeurs = {
        "FR ≥ 22": (frequence_respiratoire, lambda v: v >= 22),
        "PAS ≤ 100": (pas, lambda v: v <= 100),
        "Glasgow < 15": (glasgow, lambda v: v < 15),
    }
    manquants = tuple(nom for nom, (v, _) in valeurs.items() if v is None)
    remplis = tuple(nom for nom, (v, test) in valeurs.items() if v is not None and test(v))
    if manquants:
        return Verdict("qSOFA", len(remplis) >= 2, False, f"{len(remplis)}/3",
                       remplis, manquants, reference=_SEPSIS3)
    return Verdict("qSOFA", len(remplis) >= 2, True, f"{len(remplis)}/3",
                   remplis, reference=_SEPSIS3)


def sepsis3(
    *,
    infection_suspectee: bool | None,
    sofa_actuel: int | None,
    sofa_initial: int | None = 0,
    lactate: float | None = None,
    vasopresseurs: bool | None = None,
    hypotension_persistante: bool | None = None,
) -> Verdict:
    """Sepsis-3 : infection suspectée **et** hausse du SOFA ≥ 2 points.

    Choc septique : sepsis + besoin de vasopresseurs pour maintenir une PAM
    ≥ 65 mmHg + lactate > 2 mmol/L malgré un remplissage adéquat.

    L'infection suspectée est un jugement clinique : le logiciel ne le déduit
    pas de la présence d'un antibiotique — un antibiotique peut être
    prophylactique, et un sepsis peut précéder toute prescription.
    """
    manquants = []
    if infection_suspectee is None:
        manquants.append("infection suspectée")
    if sofa_actuel is None:
        manquants.append("SOFA")
    if manquants:
        return Verdict("Sepsis-3", False, False, manquants=tuple(manquants),
                       reference=_SEPSIS3)

    delta = sofa_actuel - (sofa_initial or 0)
    if not infection_suspectee or delta < 2:
        return Verdict("Sepsis-3", False, True, reference=_SEPSIS3)

    criteres = (f"infection suspectée, hausse du SOFA de {delta} points",)
    if vasopresseurs and lactate is not None and lactate > 2 and hypotension_persistante:
        return Verdict("Sepsis-3", True, True, "choc septique",
                       criteres + ("vasopresseurs et lactate > 2 mmol/L",),
                       reference=_SEPSIS3)
    return Verdict("Sepsis-3", True, True, "sepsis", criteres, reference=_SEPSIS3)
