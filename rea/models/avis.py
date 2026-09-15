"""Mise en forme d'un avis spécialisé (SPEC §7). Fonction pure : pas de base,
pas de HTML."""

from __future__ import annotations

from .. import listes
from .dates import format_date_fr


def ligne_avis(avis: dict) -> str:
    """« Avis CCVT (09/09) : Rsdt X : Pas d'indication chirurgicale ».

    La forme vient du service (8 septembre) : la spécialité et la date d'abord,
    parce que c'est ce qu'on cherche du regard, puis qui a répondu — un avis de
    senior et un avis de résident n'engagent pas la même chose, et c'est sur
    cette ligne qu'on décide de rappeler ou non le service.
    """
    specialite = listes.libelle(listes.SPECIALITES_AVIS, avis.get("specialite"),
                                avis.get("specialite") or "")
    morceaux = [f"Avis {specialite}"]
    if avis.get("date_avis"):
        morceaux.append(f" ({format_date_fr(avis['date_avis'])[:5]})")
    signataire = _signataire(avis)
    ligne = "".join(morceaux) + " : "
    if signataire:
        ligne += f"{signataire} : "
    return ligne + (avis.get("texte") or "").strip()


def _signataire(avis: dict) -> str:
    """« Dr X », « Rsdt X », ou le nom seul si le grade n'a pas été précisé."""
    nom = (avis.get("nom") or "").strip()
    grade = listes.libelle(listes.GRADES_AVIS, avis.get("grade"), "")
    if nom and grade:
        return f"{grade} {nom}"
    return nom or grade
