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


def _sans_accent(texte: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", texte.lower())
        if unicodedata.category(c) != "Mn"
    )


def horaires_par_defaut(produit: str | None, rythme: str | None) -> tuple[int, ...]:
    """L'heure de prise proposée à la saisie d'une ligne.

    C'est l'horaire du rythme (une prise → 8 h), sauf pour les produits qui se
    donnent traditionnellement à une autre heure : l'enoxaparine préventive
    est du soir, et la prescrire à 8 h obligeait à corriger l'horaire à chaque
    ligne (demande du service, 8 septembre). Les exceptions sont déclarées
    dans `referentiels/horaires_par_produit.json`, pas ici.
    """
    from .. import referentiels

    nom = _sans_accent(produit or "")
    if nom:
        for regle in referentiels.charger("horaires_par_produit"):
            rythmes = regle.get("rythmes")
            if rythmes and rythme not in rythmes:
                continue
            if any(_sans_accent(f) in nom for f in regle.get("fragments", ())):
                return tuple(regle["horaires"])
    return horaires_pour_rythme(rythme)


def analyser_horaires(texte: str | None) -> str | None:
    """Lit des heures tapées à la main — « 20 », « 8h 20h », « 8, 14, 20 ».

    Renvoie la forme normalisée « 8,14,20 » que stocke `horaires_override`, ou
    None si rien d'exploitable n'a été tapé : une saisie illisible ne doit pas
    effacer silencieusement l'horaire du rythme.
    """
    if not texte or not texte.strip():
        return None
    heures = []
    for morceau in texte.replace("h", " ").replace(";", " ").replace(",", " ").split():
        try:
            heure = int(morceau)
        except ValueError:
            continue
        if 0 <= heure <= 24:
            heures.append(heure)
    return ",".join(str(h) for h in heures) or None


# --------------------------------------------------------------------------
# Vitesses réglées dans la journée (P.S.E. et perfusions)
# --------------------------------------------------------------------------

def heures_de_la_journee() -> tuple[int, ...]:
    """Les 24 heures dans l'ordre de la feuille : 8 h d'abord, 7 h en dernier.

    La colonne « 0 » en tête n'a jamais rien voulu dire pour personne : la
    relève du matin ouvre la feuille, et la grille imprimée suit cet ordre.
    """
    debut = config.HEURE_DEBUT_JOURNEE
    return tuple(range(debut, 24)) + tuple(range(0, debut))


def horodatage_dans_journee(date_jour: str | date, heure: int) -> str:
    """L'horodatage d'une heure de la journée du service (8 h → 8 h).

    Une heure d'avant l'ouverture appartient au petit matin du lendemain :
    c'est la nuit de *cette* feuille-là, pas celle de la précédente.
    """
    from .dates import lendemain

    jour = parse_date(date_jour)
    if heure < config.HEURE_DEBUT_JOURNEE:
        jour = lendemain(jour)
    return f"{jour.isoformat()}T{heure % 24:02d}:00"


def fenetre_journee(date_jour: str | date) -> tuple[str, str]:
    """La journée du service : de 8 h à 8 h le lendemain.

    C'est la fenêtre que couvre la grille horaire imprimée (8 h → 7 h). Un
    réglage noté à 2 h du matin appartient donc à la journée ouverte la veille,
    pas à celle qui commencera six heures plus tard — c'est ce que dit la
    feuille, et c'est ainsi que la garde la remplit.
    """
    jour = parse_date(date_jour)
    heure = config.HEURE_DEBUT_JOURNEE
    from .dates import lendemain

    return (f"{jour.isoformat()}T{heure:02d}:00",
            f"{lendemain(jour).isoformat()}T{heure:02d}:00")


def vitesses_par_heure(
    vitesse_initiale: float | None, reglages: list[dict], date_jour: str | date
) -> dict[int, float]:
    """La vitesse à écrire dans chaque case horaire d'une journée.

    Une seringue ne se règle pas une fois pour toutes : elle part à 25 cc/h et
    on la descend à 15 à 16 h. Jusqu'ici la feuille n'imprimait que la vitesse
    de départ, dans la colonne dose — la suite se réécrivait à la main tous les
    jours (demande du service, 8 septembre).

    Ce qui est rendu : la vitesse en vigueur à l'ouverture de la journée, puis
    chaque changement à son heure. Un réglage antérieur à la journée ne
    s'imprime pas, il fixe seulement la vitesse d'ouverture.
    """
    ouverture = config.HEURE_DEBUT_JOURNEE
    debut, fin = fenetre_journee(date_jour)
    en_vigueur = vitesse_initiale
    par_heure: dict[int, float] = {}
    for reglage in sorted(reglages, key=lambda r: r.get("date_heure") or ""):
        horodatage = reglage.get("date_heure") or ""
        if horodatage < debut:
            en_vigueur = reglage["vitesse"]
        elif horodatage < fin:
            try:
                par_heure[int(horodatage[11:13]) % 24] = reglage["vitesse"]
            except ValueError:
                continue
    # La vitesse d'ouverture ne s'écrit que si rien ne la remplace déjà à cette
    # heure-là : un réglage noté à 8 h pile prime sur elle.
    if en_vigueur is not None and ouverture not in par_heure:
        par_heure[ouverture] = en_vigueur
    return par_heure


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
# Deux niveaux : l'épisode et ses versions de posologie (SPEC §5.1)
# --------------------------------------------------------------------------

#: Ce qu'une version de posologie décide, et que l'épisode ne décide pas.
CHAMPS_POSOLOGIE = (
    "dose", "unite", "rythme", "horaires_override", "condition_texte",
    "dilution", "nb_ampoules", "vitesse", "volume_dilution", "volume_24h",
    "additifs",
)


def posologie_en_vigueur(posologies: list[dict], a_la_date: str | date) -> dict | None:
    """La posologie qui s'applique ce jour-là : la dernière commencée avant ou
    ce jour même.

    Une version vaut jusqu'à ce que la suivante commence — il n'y a pas de date
    de fin à tenir à jour, donc pas de trou ni de recouvrement possible entre
    deux versions. Deux versions commencées le même jour (une dose corrigée
    dans la foulée) se départagent par l'ordre d'écriture : la dernière écrite
    est celle qui vaut.

    Rien avant la première : une posologie ne s'applique pas rétroactivement à
    des jours où elle n'était pas prescrite. Relire la pancarte de J2 doit
    montrer ce qui a été donné à J2, pas ce qu'on donne aujourd'hui.
    """
    reference = parse_date(a_la_date)
    applicables = [
        p for p in posologies
        if not p.get("supprime") and parse_date(p["date_debut"]) <= reference
    ]
    if not applicables:
        return None
    return max(
        applicables,
        key=lambda p: (parse_date(p["date_debut"]), p.get("cree_le") or ""),
    )


def appliquer_posologie(ligne: dict, posologie: dict | None) -> dict:
    """L'épisode vu avec la posologie d'un jour donné.

    Le reste du logiciel lit une « ligne » qui porte à la fois l'identité du
    traitement et sa dose ; c'est ici que les deux niveaux se recomposent, une
    fois, au lieu que chaque écran refasse la jointure à sa façon.

    Sans posologie pour ce jour-là — cas d'une base ancienne, avant que les
    versions n'existent — la ligne est rendue telle quelle : sa posologie
    d'introduction reste la seule qu'on connaisse, et l'inventer serait pire.
    """
    if posologie is None:
        return dict(ligne)
    fusion = dict(ligne)
    for champ in CHAMPS_POSOLOGIE:
        fusion[champ] = posologie.get(champ)
    fusion["posologie_id"] = posologie["id"]
    fusion["posologie_depuis"] = posologie["date_debut"]
    fusion["posologie_motif"] = posologie.get("motif_changement")
    return fusion


def posologie_differente(posologie: dict, champs: dict) -> bool:
    """Y a-t-il vraiment un changement ? Réenregistrer une ligne sans rien
    toucher ne doit pas créer une version : l'historique deviendrait illisible
    et « J4 : dose inchangée » n'apprend rien à personne."""
    return any(
        _comparable(posologie.get(c)) != _comparable(champs.get(c))
        for c in CHAMPS_POSOLOGIE
    )


def _comparable(valeur):
    """1 et 1.0 sont la même dose ; "" et None sont la même absence."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    return valeur


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


def dose_affichee(posologie: dict) -> str:
    """« 1g x3/j », « 25 cc/h » — la posologie seule, sans le compteur ni le
    produit. Sert à comparer deux versions d'un même traitement, là où répéter
    le nom du produit à chaque ligne n'apprendrait rien.
    """
    morceaux = []
    if posologie.get("dose") is not None:
        morceaux.append(f"{_nombre(posologie['dose'])}{posologie.get('unite') or ''}")
    if posologie.get("dilution"):
        morceaux.append(str(posologie["dilution"]))
    if posologie.get("vitesse") is not None:
        morceaux.append(f"{_nombre(posologie['vitesse'])} cc/h")
    if posologie.get("volume_24h") is not None:
        morceaux.append(f"{_nombre(posologie['volume_24h'])} mL/24 h")
    if posologie.get("rythme") and posologie["rythme"] != "continu":
        morceaux.append(str(posologie["rythme"]))
    return " ".join(morceaux)


def libelle_ligne(ligne: dict, a_la_date: str | date) -> str:
    """Texte complet d'une ligne tel qu'affiché sur la pancarte, ex.
    « J2 Targocid 400mg x2/j » ou « Introduction de Targocid 400mg x2/j ».
    Le corps de la description suit la voie (SPEC §5.2) : un PSE ne montre
    jamais de rythme, un PO ne montre jamais de vitesse."""
    etiquette = etiquette_jour(ligne, a_la_date)
    morceaux = [etiquette.texte, ligne["produit"]]
    voie = ligne.get("voie")

    if voie == "PSE":
        if ligne.get("dilution"):
            morceaux.append(str(ligne["dilution"]))
        if ligne.get("vitesse") is not None:
            morceaux.append(f"— vitesse {_nombre(ligne['vitesse'])}")
    elif voie == "ENTREES":
        if ligne.get("vitesse") is not None:
            morceaux.append(f"v{_nombre(ligne['vitesse'])}")
        if ligne.get("volume_24h") is not None:
            morceaux.append(f"{_nombre(ligne['volume_24h'])} mL/24 h")
        if ligne.get("additifs"):
            morceaux.append(str(ligne["additifs"]))
    elif voie in ("SOINS", "KINE"):
        if ligne.get("rythme"):
            morceaux.append(ligne["rythme"])
    else:
        if ligne.get("dose") is not None:
            morceaux.append(f"{_nombre(ligne['dose'])}{ligne.get('unite') or ''}")
        if ligne.get("rythme") and ligne["rythme"] not in ("continu", "conditionnel"):
            horaires = horaires_affiches(ligne["rythme"], ligne.get("horaires_override"))
            suffixe = f" ({horaires})" if horaires else ""
            morceaux.append(f"{ligne['rythme']}{suffixe}")
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


def _nombre_fr(valeur) -> str:
    """Comme `_nombre`, mais avec la virgule décimale française — pour les
    phrases lues à l'écran, pas pour les libellés de pancarte."""
    return _nombre(valeur).replace(".", ",")


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


@dataclass(frozen=True)
class BilanHydrique:
    """Le bilan des 24 h : ce qui est entré, ce qui est sorti, ce qui reste.

    Chaque composante est gardée à part plutôt que fondue dans un seul chiffre :
    un bilan positif de 800 mL ne se lit pas pareil selon qu'il vient d'une
    diurèse effondrée ou d'un litre de remplissage, et c'est le détail qu'on
    relit à la visite.

    Ce qui manque manque : le net n'est calculé que si la diurèse et le poids
    sont là (règle 3 de `calculs.py` — un calcul n'invente jamais une valeur
    par défaut). Une case vide dit « non mesuré », jamais « zéro ».
    """

    entrees_ml: float
    detail_entrees: list[tuple[str, float]]
    diurese_ml: float | None
    drains_ml: float
    detail_drains: list[tuple[str, float]]
    poids_kg: float | None
    temperature_c: float | None
    pertes_base_ml: float | None
    majoration_fievre_ml: float | None
    formule_insensibles: str

    @property
    def pertes_insensibles_ml(self) -> float | None:
        if self.pertes_base_ml is None:
            return None
        return self.pertes_base_ml + (self.majoration_fievre_ml or 0)

    @property
    def sorties_ml(self) -> float | None:
        """Sorties mesurées et pertes insensibles réunies."""
        if self.diurese_ml is None or self.pertes_insensibles_ml is None:
            return None
        return self.diurese_ml + self.drains_ml + self.pertes_insensibles_ml

    @property
    def net_ml(self) -> float | None:
        sorties = self.sorties_ml
        return None if sorties is None else self.entrees_ml - sorties

    @property
    def manquants(self) -> list[str]:
        """Ce qu'il faudrait saisir pour que le bilan se calcule."""
        absents = []
        if self.diurese_ml is None:
            absents.append("la diurèse des 24 h")
        if self.poids_kg is None:
            absents.append("le poids (pertes insensibles)")
        return absents


def pertes_insensibles_24h(
    poids_kg: float | None,
    temperature_c: float | None,
    reglages: dict | None = None,
) -> tuple[float | None, float | None, str]:
    """(pertes de base, majoration fièvre, formule) sur 24 h.

    Convention du service (8 septembre 2026), tenue dans
    `referentiels/bilan_hydrique.json` pour qu'un senior puisse la revoir sans
    reprogrammer : 0,5 mL/kg/h à 37 °C, majorées de 2 mL/kg/24 h par degré
    au-dessus — ou d'un forfait par degré, selon le mode choisi.

    Sans poids, rien n'est calculé : une perte insensible sans poids n'existe
    pas, et un chiffre inventé dans un bilan hydrique est pire que pas de
    chiffre du tout.

    `reglages` sert à essayer une autre convention sans toucher au fichier —
    c'est ce que fait le test du mode forfait.
    """
    if reglages is None:
        from .. import referentiels

        reglages = referentiels.charger("bilan_hydrique")
    par_kg_h = reglages["pertes_insensibles_ml_kg_h"]
    reference = reglages["temperature_reference_c"]
    # Une phrase lue par un médecin français : virgule décimale.
    formule = f"{_nombre_fr(par_kg_h)} mL/kg/h × 24 h à {_nombre_fr(reference)} °C"

    if not poids_kg:
        return None, None, formule
    base = par_kg_h * poids_kg * 24

    if temperature_c is None or temperature_c <= reference:
        return base, 0.0, formule

    degres = temperature_c - reference
    if reglages["majoration_fievre_mode"] == "forfait":
        forfait = reglages["majoration_fievre_forfait_ml_par_degre"]
        majoration = forfait * degres
        formule += f", + {_nombre_fr(forfait)} mL par degré au-dessus"
    else:
        par_kg = reglages["majoration_fievre_ml_kg_24h_par_degre"]
        majoration = par_kg * poids_kg * degres
        formule += f", + {_nombre_fr(par_kg)} mL/kg/24 h par degré au-dessus"
    return base, majoration, formule


def bilan_hydrique(
    lignes_actives: list[dict],
    *,
    diurese_ml: float | None,
    drains: list[tuple[str, float]] | None = None,
    poids_kg: float | None,
    temperature_c: float | None,
) -> BilanHydrique:
    """Le bilan des 24 h, tel que le service l'a défini (8 septembre 2026) :

        entrées − (diurèse + drains + pertes insensibles)

    Les entrées viennent du prescrit — c'est déjà ce que calcule
    `volume_entrees_24h`. Les sorties se saisissent dans le plan
    hémodynamique de l'évolution : elles sont relevées au lit du malade, le
    logiciel n'a aucun moyen de les deviner.
    """
    entrees = volume_entrees_24h(lignes_actives)
    drains = list(drains or [])
    base, majoration, formule = pertes_insensibles_24h(poids_kg, temperature_c)
    return BilanHydrique(
        entrees_ml=entrees.total_ml,
        detail_entrees=entrees.detail,
        diurese_ml=diurese_ml,
        drains_ml=sum(v for _l, v in drains),
        detail_drains=drains,
        poids_kg=poids_kg,
        temperature_c=temperature_c,
        pertes_base_ml=base,
        majoration_fievre_ml=majoration,
        formule_insensibles=formule,
    )


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
