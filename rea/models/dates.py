"""Calculs de dates, d'âges et de jours d'hospitalisation (SPEC §3.1, §5.4)."""

from __future__ import annotations

from datetime import date, datetime


def parse_date(valeur: str | date | None) -> date | None:
    """Accepte une date ISO ('2026-09-01' ou '2026-09-01T08:00:00') ou déjà
    un objet date/datetime. Renvoie None pour une valeur absente — pas de
    valeur par défaut silencieuse (règle de conception 7)."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    texte = str(valeur)[:10]
    return date.fromisoformat(texte)


def age_ans(date_naissance: str | date | None, a_la_date: str | date | None = None) -> int | None:
    """Âge en années révolues à une date donnée (par défaut : aujourd'hui)."""
    naissance = parse_date(date_naissance)
    if naissance is None:
        return None
    reference = parse_date(a_la_date) or date.today()
    age = reference.year - naissance.year
    if (reference.month, reference.day) < (naissance.month, naissance.day):
        age -= 1
    return age


def jour_hospitalisation(date_admission: str | date, a_la_date: str | date | None = None) -> int:
    """Jour d'hospitalisation (J1 le jour de l'admission)."""
    admission = parse_date(date_admission)
    reference = parse_date(a_la_date) or date.today()
    if admission is None:
        raise ValueError("date_admission est requise")
    return (reference - admission).days + 1


def jour_traitement(date_debut: str | date, a_la_date: str | date | None = None) -> int:
    """Numéro de jour d'une ligne de traitement (J1 = jour d'introduction)."""
    debut = parse_date(date_debut)
    reference = parse_date(a_la_date) or date.today()
    if debut is None:
        raise ValueError("date_debut est requise")
    return (reference - debut).days + 1


def duree_sejour_jours(date_admission: str | date, date_sortie: str | date | None = None) -> int:
    """Durée de séjour en jours. Si le séjour est en cours, jusqu'à aujourd'hui."""
    admission = parse_date(date_admission)
    fin = parse_date(date_sortie) or date.today()
    if admission is None:
        raise ValueError("date_admission est requise")
    return (fin - admission).days + 1


def lendemain(reference: str | date | None = None) -> date:
    from datetime import timedelta

    base = parse_date(reference) or date.today()
    return base + timedelta(days=1)


def format_date_fr(valeur: str | date | None) -> str:
    d = parse_date(valeur)
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")
