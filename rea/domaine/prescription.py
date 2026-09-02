"""Logique de la pancarte (SPEC §5) — horaires, compteurs de jours, bilan
hydrique. Cette fonction calcule des dates, des horaires et des volumes ;
elle ne calcule jamais une dose (SPEC §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .. import config
from .dates import jour_traitement, parse_date

# --------------------------------------------------------------------------
# Horaires (SPEC §5.3)
# --------------------------------------------------------------------------

def horaires_pour_rythme(rythme: str | None, override: str | None = None) -> tuple[int, ...]:
    """Horaires en heures entières (0-24). `override` est la liste modifiée
    par le prescripteur pour cette ligne précise, ex. "8,14,20,2"."""
    if override:
        return tuple(int(h.strip()) for h in override.split(",") if h.strip() != "")
    if rythme is None:
        return ()
    return config.HORAIRES_PAR_RYTHME.get(rythme, ())


def horaires_affiches(rythme: str | None, override: str | None = None) -> str:
    heures = horaires_pour_rythme(rythme, override)
    if not heures:
        return ""
    return "-".join(f"{h}h" if h < 24 else "24h" for h in heures)


# --------------------------------------------------------------------------
# Nombre de prises par jour — utile au bilan hydrique (SPEC §5.6)
# --------------------------------------------------------------------------

NB_PRISES_PAR_RYTHME: dict[str, float] = {
    "x1/j": 1,
    "x2/j": 2,
    "x3/j": 3,
    "x4/j": 4,
    "x6/j": 6,
    "1j/2": 0.5,
    "continu": 0,
    "conditionnel": 0,
}


def nb_prises_par_jour(rythme: str | None) -> float:
    if rythme is None:
        return 0
    return NB_PRISES_PAR_RYTHME.get(rythme, 0)


# --------------------------------------------------------------------------
# Ligne active à une date, compteur de jours (SPEC §5.1, §5.4)
# --------------------------------------------------------------------------

def ligne_active_le(ligne: dict, a_la_date: str | date) -> bool:
    """Une ligne (active ou pas encore arrêtée) est-elle en vigueur ce
    jour-là ? Une ligne dupliquée n'existe jamais (décision v1.3) : on
    calcule la présence par intersection avec sa période."""
    if ligne.get("statut") == "arretee" and ligne.get("date_arret"):
        if parse_date(a_la_date) > parse_date(ligne["date_arret"]):
            return False
    debut = parse_date(ligne["date_debut"])
    reference = parse_date(a_la_date)
    if reference < debut:
        return False
    date_arret = parse_date(ligne.get("date_arret"))
    if date_arret is not None and reference > date_arret:
        return False
    return True


@dataclass
class EtiquetteJour:
    """Ce qu'on affiche devant une ligne de prescription un jour donné."""

    jour: int
    duree_prevue: int | None
    introduction: bool
    dernier_jour: bool
    echue: bool  # au-delà de la durée prévue — jamais supprimée, signalée

    @property
    def texte(self) -> str:
        if self.introduction:
            return "Introduction de"
        if self.duree_prevue:
            return f"J{self.jour}/{self.duree_prevue}"
        return f"J{self.jour}"


def etiquette_jour(ligne: dict, a_la_date: str | date) -> EtiquetteJour:
    """SPEC §5.4 :
    - jour d'introduction  → « Introduction de … »
    - jour suivant, sans durée prévue → « J2 … »
    - avec durée prévue → « J{n}/{durée} … », y compris le dernier jour
    """
    jour = jour_traitement(ligne["date_debut"], a_la_date)
    duree = ligne.get("duree_prevue_jours")
    return EtiquetteJour(
        jour=jour,
        duree_prevue=duree,
        introduction=(jour <= 1),
        dernier_jour=bool(duree) and jour == duree,
        echue=bool(duree) and jour > duree,
    )


def libelle_ligne(ligne: dict, a_la_date: str | date) -> str:
    """Texte complet d'une ligne tel qu'affiché sur la pancarte, ex.
    « J2 Targocid 400mg x2/j » ou « Introduction de Targocid 400mg x2/j »."""
    etiquette = etiquette_jour(ligne, a_la_date)
    morceaux = [etiquette.texte, ligne["produit"]]
    if ligne.get("dose") is not None:
        morceaux.append(f"{_nombre(ligne['dose'])}{ligne.get('unite') or ''}")
    if ligne.get("rythme") and ligne["rythme"] not in ("continu", "conditionnel"):
        rythme_affiche = ligne["rythme"].replace("x", "x")
        horaires = horaires_affiches(ligne["rythme"], ligne.get("horaires_override"))
        suffixe = f" ({horaires})" if horaires else ""
        morceaux.append(f"{rythme_affiche}{suffixe}")
    elif ligne.get("rythme") == "conditionnel" and ligne.get("condition_texte"):
        morceaux.append(f"si {ligne['condition_texte']}")
    elif ligne.get("rythme") == "continu" and ligne.get("vitesse") is not None:
        morceaux.append(f"— vitesse {_nombre(ligne['vitesse'])}")
    if ligne.get("nb_ampoules"):
        morceaux.append(f"({_nombre(ligne['nb_ampoules'])} amp)")
    texte = " ".join(str(m) for m in morceaux if m)
    if etiquette.dernier_jour:
        texte += "  ← dernier jour"
    return texte


def _nombre(valeur) -> str:
    if valeur is None:
        return ""
    if float(valeur) == int(valeur):
        return str(int(valeur))
    return str(valeur).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# Bilan hydrique — entrées sur 24 h (SPEC §5.6)
# --------------------------------------------------------------------------

@dataclass
class BilanEntrees:
    total_ml: float = 0.0
    detail: list[tuple[str, float]] = field(default_factory=list)

    def ajouter(self, libelle: str, volume_ml: float) -> None:
        if volume_ml:
            self.total_ml += volume_ml
            self.detail.append((libelle, volume_ml))


def volume_entrees_24h(lignes_actives: list[dict]) -> BilanEntrees:
    """SPEC §5.6 :
        Σ (perfusions : vitesse cc/h × 24)
      + Σ (PSE : vitesse cc/h × 24)
      + Σ (médicaments IV : volume de dilution × nombre de prises)
      + nutrition entérale (volume/j)
      + nutrition parentérale (volume/j)
    Les sorties restent manuscrites — ce bilan ne porte que les entrées.
    """
    bilan = BilanEntrees()
    for ligne in lignes_actives:
        voie = ligne.get("voie")
        vitesse = ligne.get("vitesse")
        if voie == "PSE" and vitesse:
            bilan.ajouter(f"{ligne['produit']} (PSE)", float(vitesse) * 24)
        elif voie == "ENTREES":
            sous_type = ligne.get("sous_type")
            if sous_type == "perfusion" and vitesse:
                bilan.ajouter(ligne["produit"], float(vitesse) * 24)
            elif sous_type in ("nutrition_enterale", "nutrition_parenterale"):
                volume = ligne.get("volume_24h")
                if volume:
                    bilan.ajouter(ligne["produit"], float(volume))
        elif voie == "IV":
            volume_dilution = ligne.get("volume_dilution")
            prises = nb_prises_par_jour(ligne.get("rythme"))
            if volume_dilution and prises:
                bilan.ajouter(ligne["produit"], float(volume_dilution) * prises)
    return bilan
