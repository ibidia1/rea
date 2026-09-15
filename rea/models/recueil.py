"""Des niveaux lus dans un sac, une diurèse (SPEC §5.8).

L'infirmier ne mesure pas ce qui sort. Il lit **ce que le sac contient** : 120
à 8 h, 210 à 9 h, 300 à 10 h. Et quand le sac est presque plein — ou
simplement pour ne pas perdre le compte — il le jette et en met un neuf, si
bien que le chiffre repart de zéro (pratique du service, 10 septembre).

Le logiciel additionnait ces cases. C'était faux deux fois. Additionner des
niveaux recompte la même urine à chaque heure : un patient qui fait 100 mL/h
pendant douze heures produit 1 200 mL, et la somme des niveaux lus en annonce
7 800 — le chiffre grandit avec le nombre d'heures relevées, pas avec ce que
le patient produit, donc l'équipe la plus consciencieuse fausse le plus le
bilan. Et un sac jeté sans que le logiciel le sache se lit comme une diurèse
qui s'effondre.

Ce module fait la soustraction que personne ne doit faire au lit du malade :

    sortie(h) = niveau(h) − niveau du relevé précédent dans le même sac

et, après un sac jeté, le relevé suivant se compte à partir de zéro.

Deux règles de sûreté valent d'être dites, parce qu'elles décident de chiffres
qu'un médecin lira :

* **le premier relevé d'un séjour n'est pas une sortie.** Le sac contenait
  déjà quelque chose ; l'attribuer à l'heure où on a commencé à regarder
  inventerait une diurèse.
* **un niveau qui baisse sans sac déclaré jeté** n'est jamais compté en
  négatif. Quelqu'un a vidé le sac sans le dire ; on compte le niveau lu — le
  minimum certain — et on le signale, au lieu de retrancher de la journée une
  urine qui a bien été produite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Releve:
    """Un niveau lu sur le sac, à un instant, et s'il a été jeté ensuite."""

    instant: datetime
    niveau_ml: float
    sac_jete: bool = False


@dataclass(frozen=True)
class Sortie:
    """Ce qui est sorti entre le relevé précédent et celui-ci.

    `volume_ml` à None veut dire « pas calculable » — jamais zéro : rien à
    quoi comparer n'est pas la même chose que rien qui soit sorti.
    """

    instant: datetime
    niveau_ml: float
    volume_ml: float | None
    sac_jete: bool
    anomalie: str | None = None

    @property
    def heure(self) -> int:
        return self.instant.hour


def sorties(releves: list[Releve]) -> list[Sortie]:
    """Les volumes sortis, relevé par relevé, dans l'ordre du temps."""
    ordonnes = sorted(releves, key=lambda r: r.instant)
    resultat: list[Sortie] = []
    reference: float | None = None      # le niveau auquel comparer
    for releve in ordonnes:
        anomalie = None
        if reference is None:
            # Premier relevé connu : le sac contenait déjà quelque chose, on
            # ne sait pas depuis quand. Ce niveau ouvre le compte, il ne le
            # remplit pas.
            volume = None
        elif releve.niveau_ml >= reference:
            volume = releve.niveau_ml - reference
        else:
            volume = releve.niveau_ml
            anomalie = (
                f"niveau en baisse ({_mL(reference)} → {_mL(releve.niveau_ml)}) "
                "sans sac déclaré jeté : sac probablement vidé sans le dire, "
                f"{_mL(releve.niveau_ml)} comptés"
            )
        resultat.append(
            Sortie(
                instant=releve.instant,
                niveau_ml=releve.niveau_ml,
                volume_ml=volume,
                sac_jete=releve.sac_jete,
                anomalie=anomalie,
            )
        )
        reference = 0.0 if releve.sac_jete else releve.niveau_ml
    return resultat


@dataclass(frozen=True)
class Total:
    """Le total d'une fenêtre, et de quoi savoir ce qu'il vaut."""

    volume_ml: float | None
    heures_comptees: int
    #: Relevés de la fenêtre dont le volume n'a pas pu être calculé — faute de
    #: relevé précédent. Les taire ferait passer un total amputé pour complet.
    heures_sans_reference: int = 0
    anomalies: tuple[str, ...] = ()

    @property
    def complet(self) -> bool:
        return self.heures_sans_reference == 0 and not self.anomalies


def total(
    sorties_calculees: list[Sortie], debut: datetime, fin: datetime
) -> Total:
    """La somme sur [debut, fin[ — bornes en horodatage, pas en heures.

    En horodatage parce qu'une journée d'infirmerie franchit minuit : « les
    heures 7 à 6 » ne se compare pas, « du 9 à 7 h au 10 à 7 h » se compare.
    """
    retenues = [s for s in sorties_calculees if debut <= s.instant < fin]
    if not retenues:
        return Total(volume_ml=None, heures_comptees=0)
    volumes = [s.volume_ml for s in retenues if s.volume_ml is not None]
    return Total(
        volume_ml=sum(volumes) if volumes else None,
        heures_comptees=len(volumes),
        heures_sans_reference=sum(1 for s in retenues if s.volume_ml is None),
        anomalies=tuple(s.anomalie for s in retenues if s.anomalie),
    )


def _mL(valeur: float) -> str:
    return f"{valeur:.0f} mL"
