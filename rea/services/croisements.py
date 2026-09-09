"""Croiser deux variables d'une cohorte (bloc 19).

Les indicateurs de `statistiques.py` répondent à « comment va le service ? ».
Ce module répond à une autre famille de questions, celles qu'on se pose en
staff : *la mortalité est-elle différente selon le rapport PaO₂/FiO₂ ? selon
le E/e' ? combien de temps un patient reste-t-il ventilé sous telle molécule ?*

Le principe est volontairement simple et se tient en une phrase : on découpe
la cohorte en tranches selon un **facteur**, et on affiche un **résultat** par
tranche, avec l'effectif de chaque tranche à côté.

Ce que ce module refuse de faire, parce que ce sont les erreurs qui font
publier des choses fausses :

* **Afficher un taux sur trois patients.** Sous `EFFECTIF_MINIMAL`, la tranche
  garde son effectif mais son résultat est marqué non interprétable. Dans un
  service de douze lits, un croisement à quatre tranches vide les cases très
  vite, et « 100 % de mortalité » sur deux patients n'est pas un résultat.
* **Confondre absence et zéro.** Un séjour dont le facteur n'est pas
  renseigné n'entre dans aucune tranche : il est compté à part, et ce nombre
  est affiché. Une variable renseignée chez un tiers des patients produit un
  croisement sur un tiers des patients, et il faut le voir.
* **Laisser croire à une causalité.** Aucun test statistique n'est calculé
  ici, et c'est délibéré : un p-value affiché à côté d'un tableau descriptif
  univarié, monocentrique et non ajusté serait lu comme une preuve. Ce que
  produit ce module, ce sont des hypothèses à vérifier — et chaque résultat
  le dit.

Ce qu'il faut savoir pour lire ce qui en sort : les tranches d'une variable
continue sont découpées sur **la distribution de la cohorte elle-même**
(quartiles) sauf si on donne des seuils cliniques — pour le PaO₂/FiO₂, les
seuils de Berlin sont proposés par défaut.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .. import analytes as catalogue
from ..db import Base
from ..domaine import temperature as temp_dom
from ..domaine.dates import age_ans, parse_date
from . import dispositifs as dispositifs_service
from . import scores as scores_service
from . import statistiques as stats

#: En deçà, une proportion n'est pas affichée comme un résultat. Ce n'est pas
#: un seuil statistique — c'est le nombre en dessous duquel un chiffre en
#: pourcentage induit franchement en erreur.
EFFECTIF_MINIMAL = 5

#: Seuils cliniques proposés par défaut pour certains facteurs continus.
#: Ailleurs, on découpe en quartiles de la cohorte.
SEUILS_CLINIQUES: dict[str, tuple[float, ...]] = {
    "pafi_min": (100, 200, 300),      # définition de Berlin
    "age": (40, 65, 80),
    "igs2": (30, 50, 70),
}


@dataclass(frozen=True)
class Variable:
    code: str
    libelle: str
    genre: str          # "continu" ou "categoriel"
    unite: str = ""
    note: str = ""


@dataclass
class Strate:
    libelle: str
    effectif: int
    renseignes: int
    texte: str
    valeur: float | None = None
    interpretable: bool = True


@dataclass
class Croisement:
    facteur: Variable
    resultat: Variable
    strates: list[Strate] = field(default_factory=list)
    non_renseignes: int = 0
    total: int = 0
    avertissements: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Ce qu'on peut croiser
# --------------------------------------------------------------------------

RESULTATS: tuple[Variable, ...] = (
    Variable("deces", "Mortalité en réanimation", "proportion",
             note="calculée sur les séjours clos uniquement"),
    Variable("duree_sejour", "Durée de séjour", "duree", "jours"),
    Variable("duree_ventilation", "Durée de ventilation mécanique", "duree", "jours"),
    Variable("jours_sans_ventilation", "Jours sans ventilation à J28", "duree", "jours",
             note="un patient décédé avant J28 compte 0 — c'est la définition"),
)

_FACTEURS_FIXES: tuple[Variable, ...] = (
    Variable("age", "Âge", "continu", "ans"),
    Variable("igs2", "IGS II à l'admission", "continu", "points"),
    Variable("sofa_max", "SOFA maximal du séjour", "continu", "points"),
    Variable("pafi_min", "PaO₂/FiO₂ le plus bas", "continu", "mmHg",
             note="tranches de Berlin par défaut"),
    Variable("traumatique", "Admission traumatique", "categoriel"),
    Variable("sexe", "Sexe", "categoriel"),
)

#: Comment résumer la série d'un analyte en une valeur par séjour.
MODES_ANALYTE = {
    "premier": "première valeur",
    "min": "valeur la plus basse",
    "max": "valeur la plus haute",
    "dernier": "dernière valeur",
}


def facteurs_disponibles(base: Base) -> list[Variable]:
    """Les facteurs proposables, y compris les analytes ajoutés par le service.

    Le catalogue de biologie est ouvert (un E/e' ajouté dans l'écran Bilans
    devient un analyte comme un autre) : il apparaît donc ici sans qu'on ait
    à l'inscrire dans ce fichier. C'est ce qui rend « mortalité selon le
    E/e' » possible sans reprogrammer quoi que ce soit.
    """
    from . import analytes_locaux

    analytes_locaux.charger_dans_le_catalogue(base)
    variables = list(_FACTEURS_FIXES)
    # `GROUPES` est le catalogue livré ; `groupe_local()` porte les analytes
    # que le service a ajoutés lui-même. Oublier le second, c'est justement
    # rendre impossible « mortalité selon le E/e' » — l'exemple demandé.
    groupes = list(catalogue.GROUPES)
    local = catalogue.groupe_local()
    if local:
        groupes.append(local)
    for groupe in groupes:
        for analyte in groupe.analytes:
            for mode, libelle_mode in MODES_ANALYTE.items():
                variables.append(Variable(
                    f"bio:{analyte.id}:{mode}",
                    f"{analyte.libelle} — {libelle_mode}",
                    "continu", analyte.unite,
                ))
    variables.extend(_facteurs_produits(base))
    return variables


def _facteurs_produits(base: Base) -> list[Variable]:
    """Un facteur « a reçu ce produit » par molécule réellement prescrite.

    On ne propose que ce que le service a effectivement prescrit : une liste
    de tous les antibiotiques du monde donnerait cent facteurs vides.
    """
    produits = base.requete(
        "SELECT produit, COUNT(DISTINCT sejour_id) AS n FROM prescription_ligne "
        "WHERE supprime = 0 GROUP BY produit HAVING n >= 2 ORDER BY n DESC"
    )
    return [
        Variable(f"produit:{p['produit']}", f"A reçu {p['produit']}", "categoriel",
                 note=f"{p['n']} séjours concernés")
        for p in produits
    ]


def variable(code: str, base: Base | None = None) -> Variable | None:
    for v in _FACTEURS_FIXES + RESULTATS:
        if v.code == code:
            return v
    if code.startswith("bio:"):
        _, id_analyte, mode = code.split(":", 2)
        analyte = catalogue.analyte(id_analyte)
        libelle = analyte.libelle if analyte else id_analyte
        unite = analyte.unite if analyte else ""
        return Variable(code, f"{libelle} — {MODES_ANALYTE.get(mode, mode)}",
                        "continu", unite)
    if code.startswith("produit:"):
        return Variable(code, f"A reçu {code.split(':', 1)[1]}", "categoriel")
    return None


# --------------------------------------------------------------------------
# Lire une valeur par séjour
# --------------------------------------------------------------------------

def valeur_facteur(base: Base, sejour: dict, code: str):
    """La valeur du facteur pour ce séjour, ou None si non renseignée.

    None veut dire « on ne sait pas », jamais « zéro » ni « non » : c'est ce
    qui fait qu'un séjour sans la donnée sort du croisement au lieu d'aller
    grossir une tranche par défaut.
    """
    if code == "age":
        return age_ans(sejour.get("date_naissance"), sejour.get("date_admission"))
    if code == "igs2":
        return scores_service.igs2(base, sejour["id"]).total
    if code == "sofa_max":
        serie = [total for _jour, total in scores_service.evolution_sofa(base, sejour["id"])]
        return max(serie) if serie else None
    if code == "pafi_min":
        return _pafi_min(base, sejour["id"])
    if code == "traumatique":
        return "Traumatique" if sejour.get("traumatique") else "Non traumatique"
    if code == "sexe":
        return sejour.get("sexe") or None
    if code.startswith("bio:"):
        _, id_analyte, mode = code.split(":", 2)
        return _resume_analyte(base, sejour["id"], id_analyte, mode)
    if code.startswith("produit:"):
        produit = code.split(":", 1)[1]
        recu = base.une_ligne(
            "SELECT 1 AS oui FROM prescription_ligne "
            "WHERE sejour_id = ? AND produit = ? AND supprime = 0 LIMIT 1",
            (sejour["id"], produit),
        )
        return "Oui" if recu else "Non"
    return None


def _resume_analyte(base: Base, sejour_id: str, id_analyte: str, mode: str):
    valeurs = [
        ligne["valeur_num"]
        for ligne in base.requete(
            "SELECT valeur_num FROM bilan_resultat WHERE sejour_id = ? "
            "AND analyte = ? AND supprime = 0 AND valeur_num IS NOT NULL "
            "ORDER BY date_heure",
            (sejour_id, id_analyte),
        )
    ]
    if not valeurs:
        return None
    return {"premier": valeurs[0], "dernier": valeurs[-1],
            "min": min(valeurs), "max": max(valeurs)}.get(mode)


def _pafi_min(base: Base, sejour_id: str) -> float | None:
    """Le pire rapport PaO₂/FiO₂ du séjour.

    Le rapport n'est pas stocké : il se recalcule à partir de chaque gaz du
    sang, et seuls ceux qui portent les deux valeurs comptent. Un gaz sans
    FiO₂ — air ambiant — n'a pas de rapport, il n'en vaut pas zéro.
    """
    rapports = []
    for gaz in base.requete(
        "SELECT pao2, fio2 FROM gaz_du_sang WHERE sejour_id = ? AND supprime = 0",
        (sejour_id,),
    ):
        if gaz["pao2"] and gaz["fio2"]:
            rapports.append(gaz["pao2"] / (gaz["fio2"] / 100))
    return round(min(rapports)) if rapports else None


def valeur_resultat(base: Base, sejour: dict, code: str):
    if code == "deces":
        if not sejour.get("date_sortie"):
            return None          # séjour en cours : l'issue n'est pas connue
        return bool(stats._est_decede(sejour))
    if code == "duree_sejour":
        return stats.duree_sejour_jours(sejour)
    if code == "duree_ventilation":
        return dispositifs_service.duree_ventilation_jours(base, sejour["id"])
    if code == "jours_sans_ventilation":
        return scores_service.jours_sans_ventilation(base, sejour["id"])
    return None


# --------------------------------------------------------------------------
# Le croisement lui-même
# --------------------------------------------------------------------------

def croiser(
    base: Base,
    sejours: list[dict],
    *,
    code_facteur: str,
    code_resultat: str,
    seuils: tuple[float, ...] | None = None,
) -> Croisement:
    facteur = variable(code_facteur, base) or Variable(code_facteur, code_facteur, "categoriel")
    resultat = variable(code_resultat) or Variable(code_resultat, code_resultat, "duree")

    couples = []
    non_renseignes = 0
    for sejour in sejours:
        v = valeur_facteur(base, sejour, code_facteur)
        if v is None:
            non_renseignes += 1
            continue
        couples.append((v, valeur_resultat(base, sejour, code_resultat)))

    if facteur.genre == "continu":
        groupes = _tranches_continues(couples, seuils or SEUILS_CLINIQUES.get(code_facteur))
    else:
        groupes = _tranches_categorielles(couples)

    croisement = Croisement(
        facteur=facteur, resultat=resultat,
        non_renseignes=non_renseignes, total=len(sejours),
    )
    for libelle, valeurs in groupes:
        croisement.strates.append(_resumer(libelle, valeurs, resultat))

    if non_renseignes:
        croisement.avertissements.append(
            f"{non_renseignes} séjour(s) sur {len(sejours)} n'ont pas cette "
            f"donnée : ils ne sont dans aucune tranche."
        )
    if any(not s.interpretable for s in croisement.strates):
        croisement.avertissements.append(
            f"Certaines tranches comptent moins de {EFFECTIF_MINIMAL} séjours : "
            "leur résultat n'est pas affiché en proportion."
        )
    croisement.avertissements.append(
        "Descriptif, univarié, non ajusté et monocentrique : ce tableau "
        "fabrique une hypothèse, il ne démontre rien."
    )
    return croisement


def _tranches_continues(couples, seuils):
    """Découpe par seuils cliniques si on en donne, par quartiles sinon."""
    valeurs = sorted(v for v, _r in couples)
    if not valeurs:
        return []
    if not seuils:
        if len(valeurs) < 4:
            return [("Toutes valeurs", couples)]
        q = statistics.quantiles(valeurs, n=4)
        seuils = tuple(round(x, 2) for x in q)
    bornes = [None, *seuils, None]
    groupes = []
    for i in range(len(bornes) - 1):
        bas, haut = bornes[i], bornes[i + 1]
        dedans = [
            (v, r) for v, r in couples
            if (bas is None or v >= bas) and (haut is None or v < haut)
        ]
        if bas is None:
            libelle = f"< {_nb(haut)}"
        elif haut is None:
            libelle = f"≥ {_nb(bas)}"
        else:
            libelle = f"{_nb(bas)} – {_nb(haut)}"
        groupes.append((libelle, dedans))
    return groupes


def _tranches_categorielles(couples):
    par_categorie: dict[str, list] = {}
    for v, r in couples:
        par_categorie.setdefault(str(v), []).append((v, r))
    return sorted(par_categorie.items())


def _resumer(libelle: str, couples: list, resultat: Variable) -> Strate:
    effectif = len(couples)
    renseignes = [r for _v, r in couples if r is not None]

    if not renseignes:
        return Strate(libelle, effectif, 0, "—", None, False)

    if resultat.genre == "proportion":
        positifs = sum(1 for r in renseignes if r)
        if len(renseignes) < EFFECTIF_MINIMAL:
            return Strate(
                libelle, effectif, len(renseignes),
                f"{positifs}/{len(renseignes)} — trop peu pour un pourcentage",
                None, False,
            )
        part = positifs / len(renseignes)
        return Strate(
            libelle, effectif, len(renseignes),
            f"{positifs}/{len(renseignes)} ({part * 100:.0f} %)", part * 100,
        )

    mediane = statistics.median(renseignes)
    if len(renseignes) >= 4:
        q1, _q2, q3 = statistics.quantiles(renseignes, n=4)
        detail = f" (IQR {_nb(q1)}–{_nb(q3)})"
    else:
        detail = ""
    return Strate(
        libelle, effectif, len(renseignes),
        f"médiane {_nb(mediane)} {resultat.unite}{detail}", float(mediane),
        len(renseignes) >= EFFECTIF_MINIMAL,
    )


def _nb(valeur: float) -> str:
    """Un nombre lisible : sans décimale quand il est entier."""
    if valeur is None:
        return "—"
    if float(valeur).is_integer():
        return str(int(valeur))
    return f"{valeur:.1f}".replace(".", ",")


# --------------------------------------------------------------------------
# Délai d'apyrexie sous une molécule
# --------------------------------------------------------------------------
# « À partir de combien de jours un patient décroche sous telle molécule ? »
# Décrocher, c'est **ne plus être fébrile** (définition du service,
# 9 septembre) : ni fébrile ni subfébrile — apyrétique.
#
# Ce n'est pas un croisement en tranches mais un délai jusqu'à un événement,
# donc un module à part. Le piège de ce genre de calcul a un nom : ne compter
# que ceux qui ont décroché. Un patient encore fébrile à l'arrêt du traitement
# n'a pas un délai « très long », il n'a **pas** de délai — et l'oublier fait
# paraître efficace une molécule sous laquelle personne ne décroche.


@dataclass
class Apyrexie:
    produit: str
    episodes: int = 0            # traitements commencés chez un patient fébrile
    decroches: int = 0           # devenus apyrétiques avant la fin du traitement
    delais: list[int] = field(default_factory=list)
    jamais_decroches: int = 0
    sans_temperature: int = 0    # température non mesurée au départ
    avertissements: list[str] = field(default_factory=list)

    @property
    def delai_median(self) -> float | None:
        return statistics.median(self.delais) if self.delais else None

    @property
    def part_decroches(self) -> float | None:
        if self.episodes < EFFECTIF_MINIMAL:
            return None
        return self.decroches / self.episodes


def delai_apyrexie(base: Base, sejours: list[dict], produit: str) -> Apyrexie:
    """Combien de jours avant l'apyrexie, sous ce produit.

    Un épisode compte si le patient était **fébrile le jour où le traitement
    a commencé** : sans fièvre au départ, il n'y a rien à mesurer. Le délai
    est le nombre de jours jusqu'au premier jour apyrétique, le jour de début
    comptant pour J1 — la même convention que les compteurs J de la pancarte.

    Une température non mesurée n'est jamais lue comme une apyrexie : ce
    serait faire décrocher tout patient qu'on a simplement cessé de mesurer.
    """
    resultat = Apyrexie(produit=produit)
    for sejour in sejours:
        for episode in base.requete(
            "SELECT id, date_debut, date_arret FROM prescription_ligne "
            "WHERE sejour_id = ? AND produit = ? AND supprime = 0 "
            "ORDER BY date_debut",
            (sejour["id"], produit),
        ):
            _compter_episode(base, sejour, episode, resultat)

    if resultat.sans_temperature:
        resultat.avertissements.append(
            f"{resultat.sans_temperature} traitement(s) écartés : température "
            "non mesurée le jour du début."
        )
    if resultat.jamais_decroches:
        resultat.avertissements.append(
            f"{resultat.jamais_decroches} patient(s) sur {resultat.episodes} "
            "n'ont pas décroché avant la fin du traitement. Ils ne sont pas "
            "dans la médiane — la lire seule ferait paraître efficace une "
            "molécule sous laquelle personne ne décroche."
        )
    if resultat.episodes < EFFECTIF_MINIMAL:
        resultat.avertissements.append(
            f"Moins de {EFFECTIF_MINIMAL} traitements : rien à conclure."
        )
    resultat.avertissements.append(
        "Aucun ajustement sur la gravité, le germe ou les traitements "
        "associés : ce délai décrit, il ne compare pas."
    )
    return resultat


def _compter_episode(base: Base, sejour: dict, episode: dict, resultat: Apyrexie) -> None:
    temperatures = _temperatures_du_sejour(base, sejour["id"])
    debut = episode["date_debut"]
    if not temp_dom.est_febrile(temperatures.get(debut)):
        if temperatures.get(debut) is None:
            resultat.sans_temperature += 1
        return

    resultat.episodes += 1
    fin = episode["date_arret"] or sejour.get("date_sortie") or max(temperatures, default=debut)
    jours = sorted(j for j in temperatures if debut <= j <= str(fin)[:10])
    for jour in jours:
        if temp_dom.est_apyretique(temperatures[jour]):
            resultat.decroches += 1
            resultat.delais.append(
                (parse_date(jour) - parse_date(debut)).days + 1
            )
            return
    resultat.jamais_decroches += 1


def _temperatures_du_sejour(base: Base, sejour_id: str) -> dict[str, float]:
    """date_jour -> température relevée ce jour-là (plan infectieux)."""
    return {
        ligne["date_jour"]: ligne["valeur_num"]
        for ligne in base.requete(
            "SELECT date_jour, valeur_num FROM evolution_element "
            "WHERE sejour_id = ? AND cle = 'temperature' AND supprime = 0 "
            "AND valeur_num IS NOT NULL ORDER BY date_jour",
            (sejour_id,),
        )
    }
