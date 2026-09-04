"""Scores de gravité — barèmes déclaratifs (feuille de route, bloc 9).

Un score de gravité est une table de points publiée. La mettre en dur dans le
code, c'est la rendre invérifiable : personne, dans le service, ne peut relire
du Python pour contrôler qu'un palier est au bon endroit. Les barèmes vivent
donc dans `regles/score_*.json`, sous la même forme que les règles d'aide, et
se relisent ligne à ligne face à la publication d'origine.

Le moteur, lui, ne connaît aucun score : il applique des paliers à des faits,
dans l'ordre, premier palier vrai gagnant.

Trois précautions, sans lesquelles un score fait plus de mal que de bien :

1. **Une donnée manquante n'est pas une donnée normale.** Elle vaut zéro point
   par convention, mais le score est alors marqué incomplet et la liste des
   variables manquantes est rendue avec lui. Un IGS II calculé sur la moitié
   des variables n'est pas un IGS II.
2. **Un score est une description, pas une décision.** La mortalité prédite
   décrit une population, pas le patient qu'on a devant soi.
3. Les barèmes livrés sont marqués non validés tant qu'un senior ne les a pas
   relus contre la publication.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .regles import Regle, declenchee


@dataclass(frozen=True)
class Composante:
    code: str
    libelle: str
    points: int
    valeur: object = None
    renseignee: bool = True
    note: str = ""


@dataclass(frozen=True)
class Score:
    code: str
    libelle: str
    total: int
    composantes: tuple[Composante, ...]
    manquantes: tuple[str, ...]
    version: str = ""
    source: str = ""
    valide: bool = False

    @property
    def complet(self) -> bool:
        return not self.manquantes

    @property
    def resume(self) -> str:
        if self.complet:
            return f"{self.libelle} {self.total}"
        return f"{self.libelle} {self.total} (incomplet : {len(self.manquantes)} variables manquantes)"


def _points_variable(variable: dict, faits: dict) -> Composante:
    nom = variable["fait"]
    valeur = faits.get(nom)
    renseignee = valeur is not None
    points = 0
    if renseignee:
        for palier in variable.get("paliers", ()):
            regle = Regle.depuis_dict(
                {
                    "code": nom, "libelle": nom, "message": "",
                    "conditions": palier.get("si", []),
                    "combinaison": palier.get("combinaison", "et"),
                }
            )
            if declenchee(regle, faits):
                points = int(palier["points"])
                break
    return Composante(
        code=nom,
        libelle=variable.get("libelle", nom),
        points=points,
        valeur=valeur,
        renseignee=renseignee,
        note=variable.get("note", ""),
    )


def calculer(bareme: dict, faits: dict) -> Score:
    composantes = tuple(
        _points_variable(v, faits) for v in bareme.get("variables", ())
    )
    manquantes = tuple(
        c.libelle for c in composantes
        if not c.renseignee and not next(
            (v.get("facultative") for v in bareme["variables"] if v["fait"] == c.code),
            False,
        )
    )
    return Score(
        code=bareme.get("code", ""),
        libelle=bareme.get("libelle", bareme.get("titre", "")),
        total=sum(c.points for c in composantes),
        composantes=composantes,
        manquantes=manquantes,
        version=bareme.get("version", ""),
        source=bareme.get("source", ""),
        valide=bool(bareme.get("valide")),
    )


# --------------------------------------------------------------------------
# Mortalité prédite par l'IGS II
# --------------------------------------------------------------------------

def mortalite_predite_igs2(total: int | None) -> float | None:
    """Probabilité de décès hospitalier prédite par l'IGS II.

        logit = −7,7631 + 0,0737 × IGS II + 0,9971 × ln(IGS II + 1)
        P = e^logit / (1 + e^logit)

    Le Gall J-R, Lemeshow S, Saulnier F. A new Simplified Acute Physiology
    Score (SAPS II) based on a European/North American multicenter study.
    JAMA 1993;270(24):2957-63.

    ⚠️ Cette probabilité décrit une population, pas un patient. Elle n'est
    valable qu'avec un score complet, calculé sur les valeurs les plus
    défavorables des 24 premières heures, et son étalonnage vieillit : un
    rapport entre mortalité observée et mortalité prédite se lit comme un
    indicateur de case-mix, jamais comme un pronostic individuel.
    """
    if total is None or total < 0:
        return None
    logit = -7.7631 + 0.0737 * total + 0.9971 * math.log(total + 1)
    return round(math.exp(logit) / (1 + math.exp(logit)), 4)


# --------------------------------------------------------------------------
# Jours sans ventilation (ventilator-free days)
# --------------------------------------------------------------------------

def jours_sans_ventilation(
    *,
    jours_ventile: int | None,
    decede: bool,
    duree_suivi_jours: int = 28,
    jours_observes: int | None = None,
) -> int | None:
    """Jours vivant et sans ventilation mécanique à J28.

    Convention usuelle des essais de réanimation : **un patient décédé avant
    la fin de la période compte 0**, quelle qu'ait été sa durée de ventilation.
    C'est ce qui empêche le critère de récompenser un décès précoce — et c'est
    exactement le piège qu'un calcul naïf (« 28 − jours de ventilation »)
    tendrait au service.

    Schoenfeld DA, Bernard GR. Statistical evaluation of ventilator-free days
    as an efficacy measure in clinical trials of treatments for acute
    respiratory distress syndrome. Crit Care Med 2002;30(8):1772-7.

    Rend None tant que la période n'est pas écoulée et que le patient est
    toujours hospitalisé : le critère n'est pas encore calculable.
    """
    if decede:
        return 0
    if jours_ventile is None:
        return None
    if jours_observes is not None and jours_observes < duree_suivi_jours:
        return None
    return max(duree_suivi_jours - min(jours_ventile, duree_suivi_jours), 0)
