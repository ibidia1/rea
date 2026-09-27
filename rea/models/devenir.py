"""Le devenir du patient à J28 (SPEC §9.2) — ce qu'on sait, ce qu'on déduit.

La mortalité à J28 compte les décès survenus dans les 28 jours qui suivent
l'admission, **où qu'ils surviennent** : en réanimation, dans le service
d'aval ou à domicile. Le logiciel n'a pas à demander ce qu'il sait déjà :

* décédé en réanimation avant J28 → décédé à J28 ;
* encore en réanimation à J28 (ou sorti après) → vivant à J28, puisqu'il y
  était ce jour-là ;
* sorti vivant avant J28 → **inconnu** tant que personne ne l'a vérifié.

Seul ce dernier cas demande un geste (un appel, un dossier consulté). C'est
cette liste-là qu'on présente au service, pas tous les séjours — relancer
un patient mort en réanimation serait absurde, et le faire saisir à la main
une source d'erreurs.
"""

from __future__ import annotations

from datetime import date, timedelta

from .dates import parse_date

#: Horizon du devenir, en jours après l'admission.
HORIZON_JOURS = 28

STATUTS = ("vivant", "decede", "perdu_de_vue")


def _date_j28(sejour: dict) -> date | None:
    admission = parse_date(sejour.get("date_admission"))
    return admission + timedelta(days=HORIZON_JOURS) if admission else None


def deces_en_reanimation(sejour: dict) -> bool:
    return (sejour.get("mode_sortie") == "deces"
            or sejour.get("deces_reanimation") == 1)


def statut_j28(sejour: dict, aujourdhui: date | None = None) -> str | None:
    """« vivant », « decede », « perdu_de_vue », ou None si on ne sait pas
    (encore). Une saisie explicite l'emporte toujours sur la déduction."""
    saisi = sejour.get("statut_j28")
    if saisi in STATUTS:
        return saisi
    j28 = _date_j28(sejour)
    if j28 is None:
        return None
    sortie = parse_date(sejour.get("date_sortie"))
    if deces_en_reanimation(sejour) and sortie is not None:
        return "decede" if sortie <= j28 else "vivant"
    if sortie is None or sortie > j28:
        # En réanimation le jour J28 : vivant ce jour-là, si J28 est passé.
        return "vivant" if (aujourdhui or date.today()) >= j28 else None
    return None


def a_relancer(sejour: dict, aujourdhui: date | None = None) -> bool:
    """Sorti vivant avant J28, J28 passé, et personne n'a encore vérifié."""
    j28 = _date_j28(sejour)
    if j28 is None or (aujourdhui or date.today()) < j28:
        return False
    return statut_j28(sejour, aujourdhui) is None


def decede_avant_j28(sejour: dict) -> bool:
    return statut_j28(sejour) == "decede"
