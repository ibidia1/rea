"""Cohortes, indicateurs de service et tableau descriptif (blocs 16 à 18).

Trois choses que ce module refuse de faire, parce qu'elles produisent des
chiffres faux à l'air juste :

* **Compter un dénominateur qu'on n'a pas.** Un taux d'infection pour 1000
  jours de dispositif n'existe pas si les dates de pose et de retrait ne sont
  pas saisies : la fonction rend alors le dénominateur nul et le taux `None`,
  jamais zéro.
* **Confondre « non renseigné » et « non ».** Une proportion est toujours
  rendue avec le nombre de dossiers réellement renseignés, qui devient son
  dénominateur — c'est ce que demande STROBE.
* **Comparer des périodes sans le dire.** Chaque résultat porte le nombre de
  séjours et la période sur lesquels il est calculé.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from .. import referentiels
from ..db import Base
from ..domaine.dates import age_ans, parse_date
from . import dispositifs as dispositifs_service
from . import microbiologie as micro_service
from . import prescriptions as prescriptions_service
from . import scores as scores_service


# --------------------------------------------------------------------------
# Constructeur de cohorte (bloc 17)
# --------------------------------------------------------------------------

@dataclass
class Filtres:
    date_debut: str | None = None
    date_fin: str | None = None
    traumatique: bool | None = None
    age_min: int | None = None
    age_max: int | None = None
    provenances: tuple[str, ...] = ()
    modes_sortie: tuple[str, ...] = ()
    motifs: tuple[str, ...] = ()
    dispositifs: tuple[str, ...] = ()
    decedes: bool | None = None
    sejours_clos_seulement: bool = False

    def resume(self) -> str:
        morceaux = []
        if self.date_debut or self.date_fin:
            morceaux.append(f"admissions du {self.date_debut or '…'} au {self.date_fin or '…'}")
        if self.traumatique is not None:
            morceaux.append("traumatiques" if self.traumatique else "non traumatiques")
        if self.age_min is not None or self.age_max is not None:
            morceaux.append(f"âge {self.age_min or 0}–{self.age_max or 120} ans")
        if self.provenances:
            morceaux.append("provenance : " + ", ".join(self.provenances))
        if self.motifs:
            morceaux.append("motif : " + ", ".join(self.motifs))
        if self.dispositifs:
            morceaux.append("ayant eu : " + ", ".join(self.dispositifs))
        if self.decedes is not None:
            morceaux.append("décédés" if self.decedes else "survivants")
        if self.sejours_clos_seulement:
            morceaux.append("séjours clos")
        return " · ".join(morceaux) or "tous les séjours"


def cohorte(base: Base, filtres: Filtres | None = None) -> list[dict]:
    """Les séjours retenus, avec leur patient. Les filtres sont combinés par ET."""
    filtres = filtres or Filtres()
    sejours = base.requete(
        "SELECT s.*, p.date_naissance, p.sexe, p.identifiant_etude "
        "FROM sejour s JOIN patient p ON p.id = s.patient_id "
        "WHERE s.supprime = 0 ORDER BY s.date_admission"
    )
    retenus = []
    for s in sejours:
        admission = (s["date_admission"] or "")[:10]
        if filtres.date_debut and admission < filtres.date_debut:
            continue
        if filtres.date_fin and admission > filtres.date_fin:
            continue
        if filtres.sejours_clos_seulement and not s.get("date_sortie"):
            continue
        if filtres.traumatique is not None and bool(s.get("traumatique")) != filtres.traumatique:
            continue
        age = age_ans(s.get("date_naissance"), admission)
        if filtres.age_min is not None and (age is None or age < filtres.age_min):
            continue
        if filtres.age_max is not None and (age is None or age > filtres.age_max):
            continue
        if filtres.provenances and s.get("provenance_type") not in filtres.provenances:
            continue
        if filtres.modes_sortie and s.get("mode_sortie") not in filtres.modes_sortie:
            continue
        if filtres.motifs:
            codes = {
                m["code"] for m in base.requete(
                    "SELECT code FROM sejour_motif WHERE sejour_id = ? AND supprime = 0",
                    (s["id"],),
                )
            }
            if not codes & set(filtres.motifs):
                continue
        if filtres.dispositifs:
            types = {
                d["type"] for d in dispositifs_service.du_sejour(base, s["id"])
            }
            if not types & set(filtres.dispositifs):
                continue
        if filtres.decedes is not None and _est_decede(s) != filtres.decedes:
            continue
        retenus.append(s)
    return retenus


def _est_decede(sejour: dict) -> bool:
    return (
        sejour.get("mode_sortie") == "deces"
        or sejour.get("deces_reanimation") == 1
        or sejour.get("statut_j28") == "decede"
    )


def duree_sejour_jours(sejour: dict, a_la_date: str | None = None) -> int | None:
    debut = parse_date(sejour.get("date_admission"))
    fin = parse_date(sejour.get("date_sortie")) or parse_date(a_la_date) or date.today()
    return (fin - debut).days + 1 if debut else None


def journees_hospitalisation(base: Base, sejours: list[dict]) -> int:
    return sum(duree_sejour_jours(s) or 0 for s in sejours)


# --------------------------------------------------------------------------
# Tableau descriptif — Table 1 de STROBE (bloc 18)
# --------------------------------------------------------------------------

@dataclass
class LigneTableau:
    libelle: str
    valeur: str
    renseignes: int
    total: int
    note: str = ""

    @property
    def manquants(self) -> int:
        return self.total - self.renseignes


def _mediane_iqr(valeurs: list[float]) -> str:
    if not valeurs:
        return "—"
    valeurs = sorted(valeurs)
    mediane = statistics.median(valeurs)
    if len(valeurs) >= 4:
        q1 = statistics.median(valeurs[: len(valeurs) // 2])
        q3 = statistics.median(valeurs[(len(valeurs) + 1) // 2:])
        return f"{mediane:g} [{q1:g} – {q3:g}]"
    return f"{mediane:g}"


def _proportion(nb: int, renseignes: int) -> str:
    if renseignes == 0:
        return "—"
    return f"{nb} ({nb / renseignes * 100:.0f} %)"


def table_1(base: Base, sejours: list[dict]) -> list[LigneTableau]:
    """Le tableau descriptif attendu en tête de tout article observationnel.

    Chaque ligne porte le nombre de dossiers renseignés : STROBE demande de
    déclarer les données manquantes, pas de les diluer dans un pourcentage
    calculé sur l'effectif total.
    """
    total = len(sejours)
    lignes: list[LigneTableau] = []
    if total == 0:
        return lignes

    ages = [
        a for a in (age_ans(s.get("date_naissance"), s["date_admission"]) for s in sejours)
        if a is not None
    ]
    lignes.append(LigneTableau("Âge (ans), médiane [IQR]", _mediane_iqr(ages), len(ages), total))

    sexes = [s.get("sexe") for s in sejours if s.get("sexe") not in (None, "non_renseigne")]
    hommes = sum(1 for s in sexes if s == "M")
    lignes.append(LigneTableau("Sexe masculin", _proportion(hommes, len(sexes)), len(sexes), total))

    poids = [s["poids_kg"] for s in sejours if s.get("poids_kg")]
    lignes.append(LigneTableau("Poids (kg), médiane [IQR]", _mediane_iqr(poids), len(poids), total))

    trauma_connus = [s for s in sejours if s.get("traumatique") is not None]
    trauma = sum(1 for s in trauma_connus if s["traumatique"])
    lignes.append(
        LigneTableau("Admission traumatique", _proportion(trauma, len(trauma_connus)),
                     len(trauma_connus), total)
    )

    provenances = referentiels.charger("provenances")
    connues = [s for s in sejours if s.get("provenance_type")]
    for code, libelle in provenances:
        nb = sum(1 for s in connues if s["provenance_type"] == code)
        if nb:
            lignes.append(
                LigneTableau(f"  Provenance : {libelle}", _proportion(nb, len(connues)),
                             len(connues), total)
            )

    igs = [scores_service.igs2(base, s["id"]) for s in sejours]
    complets = [score.total for score in igs if score.complet]
    lignes.append(
        LigneTableau("IGS II, médiane [IQR]", _mediane_iqr(complets), len(complets), total,
                     "calculé sur les seuls scores complets ; barème non encore validé")
    )

    durees = [d for d in (duree_sejour_jours(s) for s in sejours) if d is not None]
    lignes.append(
        LigneTableau("Durée de séjour (jours), médiane [IQR]", _mediane_iqr(durees),
                     len(durees), total,
                     "séjours en cours inclus, comptés jusqu'à aujourd'hui")
    )

    ventiles = [s for s in sejours
                if dispositifs_service.duree_ventilation_jours(base, s["id"]) > 0]
    lignes.append(
        LigneTableau("Ventilation mécanique", _proportion(len(ventiles), total), total, total)
    )
    jours_vm = [dispositifs_service.duree_ventilation_jours(base, s["id"]) for s in ventiles]
    lignes.append(
        LigneTableau("  Durée de ventilation (jours), médiane [IQR]", _mediane_iqr(jours_vm),
                     len(jours_vm), total)
    )

    clos = [s for s in sejours if s.get("date_sortie")]
    deces = sum(1 for s in clos if _est_decede(s))
    lignes.append(
        LigneTableau("Décès en réanimation", _proportion(deces, len(clos)), len(clos), total,
                     "sur les seuls séjours clos")
    )
    return lignes


# --------------------------------------------------------------------------
# Taux d'infections liées aux dispositifs (bloc 16)
# --------------------------------------------------------------------------

@dataclass
class Taux:
    libelle: str
    numerateur: int
    denominateur: int
    unite: str = "pour 1000 jours-dispositif"
    note: str = ""

    @property
    def valeur(self) -> float | None:
        """None, jamais zéro, quand le dénominateur est absent : « pas de
        données » et « aucune infection » ne se disent pas de la même façon."""
        if self.denominateur <= 0:
            return None
        return round(self.numerateur / self.denominateur * 1000, 2)

    @property
    def texte(self) -> str:
        if self.valeur is None:
            return f"{self.libelle} : incalculable (aucun jour-dispositif enregistré)"
        return (f"{self.libelle} : {self.valeur} {self.unite} "
                f"({self.numerateur} / {self.denominateur} jours)")


# Quel type d'infection se rapporte à quels dispositifs — la définition ECDC
# rapporte chaque infection aux jours d'exposition du dispositif en cause.
_DISPOSITIFS_PAR_INFECTION = {
    "pavm": ("intubation", "tracheotomie"),
    "ilc": ("kt_central", "picc"),
    "iu": ("sonde_urinaire", "ktsp"),
}
_LIBELLES_TAUX = {
    "pavm": "Pneumonies acquises sous ventilation",
    "ilc": "Infections liées au cathéter",
    "iu": "Infections urinaires sur sonde",
}


def taux_infections_dispositifs(base: Base, sejours: list[dict]) -> list[Taux]:
    """Taux pour 1000 jours-dispositif, dénominateur ECDC.

    Rapporter les infections au nombre de patients plutôt qu'aux jours
    d'exposition fait paraître bon un service qui ventile peu et mauvais un
    service qui ventile longtemps ; c'est pour cela que le dénominateur est
    en jours de dispositif.

    ECDC. Surveillance of healthcare-associated infections and prevention
    indicators in European intensive care units — HAI-Net ICU protocol.
    """
    resultats = []
    for type_infection, types_dispositif in _DISPOSITIFS_PAR_INFECTION.items():
        jours = 0
        infections = 0
        for s in sejours:
            for type_dispositif in types_dispositif:
                jours += dispositifs_service.jours_dispositif_total(
                    base, s["id"], type_dispositif
                )
            for infection in micro_service.infections_du_sejour(base, s["id"]):
                if infection["type"] == type_infection and (
                    micro_service.acquise_en_reanimation(s, infection)
                ):
                    infections += 1
        resultats.append(
            Taux(_LIBELLES_TAUX[type_infection], infections, jours,
                 note="infections acquises seulement (≥ 48 h après l'admission)")
        )
    return resultats


# --------------------------------------------------------------------------
# Consommation d'antibiotiques (bloc 14)
# --------------------------------------------------------------------------

def consommation_antibiotiques(base: Base, sejours: list[dict]) -> dict:
    """Jours de traitement antibiotique pour 1000 journées d'hospitalisation.

    Le DOT (days of therapy) est retenu plutôt que la DDD tant que la table
    officielle des doses définies journalières n'a pas été saisie : une DDD
    recopiée de mémoire donnerait des chiffres faux et invérifiables, alors
    que le DOT ne demande aucun barème et se compare d'une année sur l'autre.
    Le fichier `referentiels/antibiotiques_ddd.json` attend cette table.
    """
    fragments = referentiels.charger(
        "antibiotiques_ddd", "fragments_antibiotiques"
    )
    journees = journees_hospitalisation(base, sejours)
    jours_traitement = 0
    molecules: dict[str, int] = {}
    for s in sejours:
        # Un épisode par traitement, pas une par changement de dose : compter
        # les versions doublerait la durée d'antibiothérapie de tout patient
        # dont la posologie a été adaptée une fois (SPEC §5.1).
        for ligne in prescriptions_service.episodes(base, s["id"]):
            produit = (ligne.get("produit") or "").lower()
            trouve = next((f for f in fragments if f in produit), None)
            if not trouve:
                continue
            debut = parse_date(ligne.get("date_debut"))
            fin = parse_date(ligne.get("date_arret")) or parse_date(s.get("date_sortie")) or date.today()
            duree = (fin - debut).days + 1 if debut else 0
            jours_traitement += max(duree, 0)
            molecules[trouve] = molecules.get(trouve, 0) + max(duree, 0)
    ddd_disponible = bool(
        referentiels.charger("antibiotiques_ddd", "molecules")
    )
    return {
        "journees_hospitalisation": journees,
        "jours_de_traitement": jours_traitement,
        "dot_pour_1000_journees": (
            round(jours_traitement / journees * 1000, 1) if journees else None
        ),
        "par_molecule": dict(sorted(molecules.items(), key=lambda kv: -kv[1])),
        "ddd_disponible": ddd_disponible,
        "note": (
            "Exprimé en jours de traitement (DOT). La table officielle des DDD "
            "n'est pas renseignée : voir referentiels/antibiotiques_ddd.json."
        ) if not ddd_disponible else "",
    }


# --------------------------------------------------------------------------
# Mortalité observée et attendue
# --------------------------------------------------------------------------

def mortalite(base: Base, sejours: list[dict]) -> dict:
    """Mortalité observée, et rapport à la mortalité prédite par l'IGS II.

    Le rapport observé/prédit (SMR) ne se lit que sur des séjours clos et des
    scores complets ; sinon il compare une mortalité réelle à une prédiction
    faite sur des dossiers incomplets, ce qui la sous-estime toujours.
    """
    clos = [s for s in sejours if s.get("date_sortie")]
    deces = [s for s in clos if _est_decede(s)]
    predits = []
    for s in clos:
        p = scores_service.mortalite_predite(base, s["id"])
        if p is not None:
            predits.append(p)
    attendus = sum(predits) if predits else None
    return {
        "sejours_clos": len(clos),
        "deces": len(deces),
        "mortalite_observee": round(len(deces) / len(clos), 3) if clos else None,
        "scores_complets": len(predits),
        "deces_attendus": round(attendus, 1) if attendus is not None else None,
        "rapport_observe_attendu": (
            round(len(deces) / attendus, 2)
            if attendus and len(predits) == len(clos) and attendus > 0 else None
        ),
        "note": (
            "Rapport non calculé : tous les séjours clos n'ont pas un IGS II "
            "complet." if len(predits) != len(clos) else ""
        ),
    }
