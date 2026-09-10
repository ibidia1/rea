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

import json
from datetime import date

from .. import aides as fichiers
from ..db import Base
from ..domaine import calculs
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
    # La PAM n'est plus saisie : elle se déduit de la PAS et de la PAD. Les
    # évolutions écrites avant ce changement en portent encore une — c'est
    # elle qui prime, parce qu'elle a pu être relevée sur un cathéter
    # artériel, ce que le calcul au brassard ne remplace pas.
    f["pam"] = elements.get("pam")
    if f["pam"] is None:
        f["pam"] = calculs.pression_arterielle_moyenne(
            pas=elements.get("pas"), pad=elements.get("pad")
        ).valeur
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


def historiser(
    base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None
) -> None:
    """Garde une trace datée du SOFA du jour, pour l'export recherche.

    Le score est déjà recalculé à chaque affichage — cette fonction ne calcule
    rien de plus, elle écrit ce qui vient d'être montré à l'écran. Sans elle,
    `score_quotidien` (bloc 9, table exportée) restait structurellement vide :
    personne n'écrivait jamais dedans, même si le SOFA était affiché tous les
    jours.

    Idempotente : un même jour réécrit met à jour la ligne existante plutôt
    que d'en créer une seconde (`score_quotidien` porte un index unique sur
    sejour_id, date_jour, score).
    """
    score = sofa(base, sejour_id, date_jour)
    valeurs = {
        "sejour_id": sejour_id,
        "date_jour": date_jour,
        "score": score.code,
        "valeur": score.total if score.complet else None,
        "detail": json.dumps(
            {
                "complet": score.complet,
                "manquantes": score.manquantes,
                "composantes": [
                    {"code": c.code, "points": c.points, "renseignee": c.renseignee}
                    for c in score.composantes
                ],
            },
            ensure_ascii=False,
        ),
    }
    # Le SOFA se calcule **avant** la transaction : il lit tout le dossier du
    # jour, et le faire à l'intérieur tiendrait le verrou pendant ce temps.
    # Seul le « lire puis écrire » y entre, car `score_quotidien` porte un
    # index unique sur (séjour, jour, score) : deux écrans ouverts sur le même
    # patient auraient sinon fait échouer le second.
    with base.transaction():
        existant = base.une_ligne(
            "SELECT id FROM score_quotidien WHERE sejour_id = ? AND date_jour = ? "
            "AND score = ?",
            (sejour_id, date_jour, score.code),
        )
        if existant:
            base.mettre_a_jour(
                "score_quotidien", existant["id"],
                {k: v for k, v in valeurs.items()
                 if k not in ("sejour_id", "date_jour", "score")},
                utilisateur_id=utilisateur_id,
            )
        else:
            base.inserer("score_quotidien", valeurs, utilisateur_id=utilisateur_id)


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
