"""Scores de gravité calculés sur le dossier (bloc 9).

Les barèmes sont des fichiers (`regles/score_*.json`), le moteur est dans
`domaine/scores.py` ; ce module ne fait que rassembler les bonnes valeurs aux
bonnes dates :

* **IGS II** : les valeurs les plus défavorables des 24 premières heures. Le
  dossier ne garde aujourd'hui qu'une valeur par jour pour les constantes
  cliniques ; le score est donc calculé sur les valeurs du jour d'admission, ce
  qui est dit à l'écran. Une pancarte horaire, le jour où elle existera, le
  rendra exact sans changer le barème.
* **SOFA** : recalculé chaque jour, sur les valeurs de ce jour-là.
"""

from __future__ import annotations

from datetime import date

from .. import aides as fichiers
from ..db import Base
from ..domaine import scores as dom
from ..domaine.dates import parse_date
from . import aides as faits_service
from . import bilans as bilans_service
from . import dispositifs as dispositifs_service
from . import evolution as evolution_service

# Analytes supplémentaires que les scores demandent et que les rappels
# n'utilisaient pas.
_ANALYTES_SCORES = {"uree": "uree", "gb": "gb", "bili": "bilirubine"}


def _faits_du_jour(base: Base, sejour_id: str, jour: str) -> dict:
    f = dict(faits_service.faits(base, sejour_id, jour))

    for ligne in bilans_service.resultats_du_sejour(base, sejour_id):
        if ligne["date_heure"][:10] <= jour and ligne["valeur_num"] is not None:
            nom = _ANALYTES_SCORES.get(ligne["analyte"])
            if nom:
                f[nom] = ligne["valeur_num"]
    f.setdefault("uree", None)
    f.setdefault("gb", None)
    f.setdefault("bilirubine", None)

    gaz = bilans_service.dernier_gaz_du_sang(base, sejour_id, jour) or {}
    f["bicarbonates"] = gaz.get("hco3")

    elements = evolution_service.elements_du_jour(base, sejour_id, jour)
    f["pam"] = elements.get("pam")
    f["diurese_24h"] = elements.get("diurese_24h")
    # Une seule valeur par jour est enregistrée : elle tient lieu de valeur la
    # plus défavorable, faute de pancarte horaire.
    f["fc_max_24h"] = elements.get("fc")
    f["pas_min_24h"] = elements.get("pas")
    f["temperature_max_24h"] = elements.get("temperature")

    sejour = base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sejour_id,))
    for colonne, nom in (("type_admission", "type_admission"),
                         ("maladie_chronique_igs2", "maladie_chronique")):
        valeur = (sejour or {}).get(colonne)
        f[nom] = None if valeur in (None, "", "non_renseigne") else valeur
    return f


def sofa(base: Base, sejour_id: str, date_jour: str | None = None) -> dom.Score:
    jour = date_jour or date.today().isoformat()
    return dom.calculer(fichiers.bareme("sofa"), _faits_du_jour(base, sejour_id, jour))


def igs2(base: Base, sejour_id: str) -> dom.Score:
    sejour = base.une_ligne("SELECT date_admission FROM sejour WHERE id = ?", (sejour_id,))
    jour = (sejour or {}).get("date_admission", "")[:10] or date.today().isoformat()
    return dom.calculer(fichiers.bareme("igs2"), _faits_du_jour(base, sejour_id, jour))


def mortalite_predite(base: Base, sejour_id: str) -> float | None:
    """Uniquement sur un IGS II complet : un score amputé prédirait une
    mortalité faussement basse, ce qui est le sens le plus dangereux."""
    score = igs2(base, sejour_id)
    return dom.mortalite_predite_igs2(score.total) if score.complet else None


def evolution_sofa(base: Base, sejour_id: str) -> list[tuple[str, int]]:
    """Le SOFA jour par jour depuis l'admission — c'est sa variation qui
    porte l'information, pas sa valeur d'un jour isolé."""
    sejour = base.une_ligne("SELECT date_admission FROM sejour WHERE id = ?", (sejour_id,))
    debut = parse_date((sejour or {}).get("date_admission"))
    if not debut:
        return []
    fin = parse_date(
        (base.une_ligne("SELECT date_sortie FROM sejour WHERE id = ?", (sejour_id,)) or {})
        .get("date_sortie")
    ) or date.today()
    serie = []
    jour = debut
    while jour <= fin:
        score = sofa(base, sejour_id, jour.isoformat())
        if any(c.renseignee for c in score.composantes):
            serie.append((jour.isoformat(), score.total))
        jour = date.fromordinal(jour.toordinal() + 1)
    return serie


def jours_sans_ventilation(base: Base, sejour_id: str, duree: int = 28) -> int | None:
    sejour = base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sejour_id,))
    if sejour is None:
        return None
    admission = parse_date(sejour["date_admission"])
    fin_suivi = parse_date(sejour.get("date_sortie")) or date.today()
    jours_observes = (fin_suivi - admission).days if admission else None
    decede = (
        sejour.get("mode_sortie") == "deces"
        or sejour.get("deces_reanimation") == 1
        or sejour.get("statut_j28") == "decede"
    )
    return dom.jours_sans_ventilation(
        jours_ventile=dispositifs_service.duree_ventilation_jours(base, sejour_id),
        decede=decede,
        duree_suivi_jours=duree,
        jours_observes=jours_observes,
    )
