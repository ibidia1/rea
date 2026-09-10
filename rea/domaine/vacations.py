"""Les trois équipes qui se relaient (SPEC §5.8).

Deux vacations de six heures le jour, une de douze la nuit : 7 h – 13 h,
13 h – 19 h, 19 h – 7 h. L'infirmier qui prend son poste veut voir *ce qu'il
va donner pendant ces heures-là*, pour le préparer — pas la pancarte des
vingt-quatre heures dans laquelle il faudrait retrouver ses prises.

Le seul vrai piège est la nuit, et il tient à ce qu'elle franchit minuit :
« 19 h à 7 h » n'est pas un intervalle où l'heure de début est plus petite que
celle de fin, et tout calcul naïf (`debut <= heure < fin`) rend la vacation de
nuit vide. Les heures de nuit sont 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6 —
elles se calculent ici une fois pour toutes, et nulle part ailleurs.

Les horaires sont dans `referentiels/vacations.json` : un service qui passe en
deux fois douze heures les change sans reprogrammer.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache


@lru_cache(maxsize=1)
def _table() -> tuple[tuple[str, str, int, int], ...]:
    from .. import referentiels

    return tuple(
        (v[0], v[1], int(v[2]), int(v[3])) for v in referentiels.charger("vacations")
    )


def codes() -> tuple[str, ...]:
    return tuple(v[0] for v in _table())


def libelle(code: str | None) -> str:
    for c, nom, _d, _f in _table():
        if c == code:
            return nom
    return code or "—"


def bornes(code: str) -> tuple[int, int]:
    for c, _nom, debut, fin in _table():
        if c == code:
            return debut, fin
    raise KeyError(f"Vacation inconnue : {code}")


def horaire(code: str) -> str:
    debut, fin = bornes(code)
    return f"{debut} h – {fin} h"


def heures(code: str) -> tuple[int, ...]:
    """Les heures pleines couvertes par la vacation, dans l'ordre du poste.

    C'est ici que la nuit est traitée : quand la fin est plus petite ou égale
    au début, la vacation passe minuit et se poursuit sur les petites heures.
    """
    debut, fin = bornes(code)
    if debut < fin:
        return tuple(range(debut, fin))
    return tuple(range(debut, 24)) + tuple(range(0, fin))


def contient(code: str, heure: int) -> bool:
    return heure % 24 in heures(code)


def vacation_de(heure: int) -> str | None:
    """Quelle vacation couvre cette heure. None si les horaires laissent un
    trou — ce qui serait une erreur du référentiel, pas une situation
    normale."""
    for code in codes():
        if contient(code, heure):
            return code
    return None


def vacation_courante(instant: datetime | None = None) -> str | None:
    return vacation_de((instant or datetime.now()).hour)


def fenetre(code: str, jour: str | date) -> tuple[datetime, datetime]:
    """Le début et la fin de la vacation, ce jour-là, en horodatages.

    Une vacation de nuit ouverte le 9 se termine le 10 au matin : c'est la
    même équipe, la même feuille, et il faut que les deux bouts le disent.
    """
    from .dates import parse_date

    debut_h, fin_h = bornes(code)
    jour_debut = parse_date(jour)
    depart = datetime.combine(jour_debut, datetime.min.time()) + timedelta(hours=debut_h)
    arrivee = datetime.combine(jour_debut, datetime.min.time()) + timedelta(hours=fin_h)
    if fin_h <= debut_h:
        arrivee += timedelta(days=1)
    return depart, arrivee


def jour_de_vacation(instant: datetime | None = None) -> tuple[str, date]:
    """La vacation en cours et le jour auquel elle est rattachée.

    À 2 h du matin le 10, l'équipe de nuit est celle qui a pris son poste à
    19 h **le 9** : c'est ce jour-là qui compte pour retrouver ses affectations
    et ses administrations. Se tromper ici, c'est afficher à l'infirmière de
    nuit un poste vide au milieu de sa garde.
    """
    instant = instant or datetime.now()
    code = vacation_de(instant.hour)
    if code is None:
        return "", instant.date()
    debut, _fin = bornes(code)
    jour = instant.date()
    if debut > instant.hour:          # on a franchi minuit depuis la prise de poste
        jour -= timedelta(days=1)
    return code, jour


def prises_de_la_vacation(
    lignes_actives: list[dict], code: str
) -> list[tuple[int, dict]]:
    """Les prises à donner pendant cette vacation, dans l'ordre des heures.

    C'est le cœur de l'écran infirmier : « ce que je vais donner sur mon
    poste », et non la pancarte des vingt-quatre heures où il faudrait
    retrouver ses prises une à une.

    Trois familles de lignes, trois traitements différents :

    * celles qui ont des **horaires** (PO, IV, SC…) : on retient les prises
      dont l'heure tombe dans la vacation ;
    * celles qui **coulent en continu** (PSE, perfusions, nutrition) : elles
      n'ont pas d'heure de prise, elles sont présentes toute la vacation. On
      les rend à l'heure d'ouverture du poste, une seule fois — les faire
      apparaître à chaque heure donnerait douze cases à cocher pour une
      seringue qu'on ne touche pas ;
    * celles qui sont **conditionnelles** (« si douleur ») : elles n'ont pas
      d'horaire non plus et n'ont pas à être préparées ; elles sont rendues à
      part par `prises_conditionnelles`.

    L'ordre est celui du poste : une vacation de nuit commence à 19 h et
    finit à 6 h, donc 23 h vient avant 2 h.
    """
    from . import prescription as presc

    heures_du_poste = heures(code)
    rang = {heure: i for i, heure in enumerate(heures_du_poste)}
    prises: list[tuple[int, dict]] = []
    for ligne in lignes_actives:
        if _est_continu(ligne):
            prises.append((heures_du_poste[0], ligne))
            continue
        if ligne.get("rythme") == "conditionnel":
            continue
        for heure in presc.horaires_pour_rythme(
            ligne.get("rythme"), ligne.get("horaires_override")
        ):
            if (heure % 24) in rang:
                prises.append((heure % 24, ligne))
    return sorted(prises, key=lambda p: (rang[p[0]], p[1].get("produit") or ""))


def prises_conditionnelles(lignes_actives: list[dict]) -> list[dict]:
    """Les « si besoin » — à connaître, pas à préparer."""
    return [
        ligne for ligne in lignes_actives
        if ligne.get("rythme") == "conditionnel" and not _est_continu(ligne)
    ]


def _est_continu(ligne: dict) -> bool:
    """Ce qui coule sans heure de prise : seringues, perfusions, nutrition."""
    if ligne.get("voie") == "PSE":
        return True
    if ligne.get("voie") == "ENTREES":
        return True
    return ligne.get("rythme") == "continu"
