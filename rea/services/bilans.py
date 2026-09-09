"""Écran 5 — Bilans (SPEC §7). Intègre le fichier HTML de saisie déjà
utilisé au service : mêmes analytes (`rea.analytes`), même texte généré.

Stockage en **format long** (règle de conception 4) : une ligne par mesure
dans `bilan_resultat`, jamais une colonne par jour — c'est ce qui permet les
courbes de cinétique (SPEC §7.2) et l'export recherche sans transformation.

Calculs automatiques, jamais saisis (SPEC pptx écran 5) : rapport PaO₂/FiO₂,
bilirubine indirecte, conversion mmol/L ↔ g/L.

Les bornes de normalité ne servent qu'à colorer une valeur dans la vue de
cinétique ; elles restent une question ouverte (§10, n°8) et aucune décision
clinique n'en dépend.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import analytes as cat
from .. import listes
from ..db import Base


# --------------------------------------------------------------------------
# Calculs automatiques — jamais une dose, seulement des rapports (SPEC §3.1)
# --------------------------------------------------------------------------

def rapport_pao2_fio2(pao2: float | None, fio2: float | None) -> float | None:
    """FiO₂ saisie en % (ex. 50) — le rapport attend une fraction."""
    if pao2 is None or fio2 is None or fio2 == 0:
        return None
    return round(pao2 / (fio2 / 100))


def bilirubine_indirecte(bili_totale: float | None, bili_directe: float | None) -> float | None:
    if bili_totale is None or bili_directe is None:
        return None
    indirecte = bili_totale - bili_directe
    return round(indirecte, 1) if indirecte >= 0 else None


def mmol_vers_gl(id_analyte: str, valeur_mmol: float | None) -> float | None:
    if valeur_mmol is None:
        return None
    return round(valeur_mmol * cat.FACTEURS_LIPIDES[id_analyte], 2)


def gl_vers_mmol(id_analyte: str, valeur_gl: float | None) -> float | None:
    if valeur_gl is None:
        return None
    return round(valeur_gl / cat.FACTEURS_LIPIDES[id_analyte], 2)


# --------------------------------------------------------------------------
# Enregistrement — format long, une ligne par analyte non vide
# --------------------------------------------------------------------------

def enregistrer_resultats(
    base: Base,
    sejour_id: str,
    date_heure: str,
    valeurs: dict[str, float | None],
    *,
    utilisateur_id: str | None = None,
    saisie_forcee: bool = False,
) -> list[str]:
    """`valeurs` : id d'analyte (voir `rea.analytes`) -> nombre ou None.
    Les analytes calculés (`bili_i`) sont dérivés ici, pas attendus en
    entrée. Retourne les id des lignes créées."""
    valeurs = dict(valeurs)
    if "bili" in valeurs or "bili_d" in valeurs:
        valeurs["bili_i"] = bilirubine_indirecte(valeurs.get("bili"), valeurs.get("bili_d"))

    ids_crees = []
    for id_analyte, valeur in valeurs.items():
        if valeur is None:
            continue
        a = cat.analyte(id_analyte)
        ids_crees.append(
            base.inserer(
                "bilan_resultat",
                {
                    "sejour_id": sejour_id,
                    "date_heure": date_heure,
                    "analyte": id_analyte,
                    "valeur_num": float(valeur),
                    "unite": a.unite,
                    # Codes standards recopiés depuis le catalogue : c'est ce
                    # qui rend l'export exploitable sans table de
                    # correspondance a posteriori (feuille de route §5).
                    "code_loinc": a.code_loinc,
                    "unite_ucum": a.unite_ucum,
                    "source": "saisie",
                    "saisie_forcee": int(saisie_forcee),
                },
                utilisateur_id=utilisateur_id,
            )
        )
    return ids_crees


def enregistrer_gaz_du_sang(
    base: Base,
    sejour_id: str,
    date_heure: str,
    *,
    ph: float | None = None,
    pao2: float | None = None,
    paco2: float | None = None,
    hco3: float | None = None,
    lactate: float | None = None,
    mode_ventilatoire: str | None = None,
    debit_o2: float | None = None,
    fio2: float | None = None,
    pep: float | None = None,
    fr: float | None = None,
    spo2: float | None = None,
    sao2: float | None = None,
    vt: float | None = None,
    ai: float | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "gaz_du_sang",
        {
            "sejour_id": sejour_id,
            "date_heure": date_heure,
            "ph": ph,
            "pao2": pao2,
            "paco2": paco2,
            "hco3": hco3,
            "lactate": lactate,
            "mode_ventilatoire": mode_ventilatoire,
            "debit_o2": debit_o2,
            "fio2": fio2,
            "pep": pep,
            "fr": fr,
            "spo2": spo2,
            "sao2": sao2,
            "vt": vt,
            "ai": ai,
        },
        utilisateur_id=utilisateur_id,
    )


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------

def resultats_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM bilan_resultat WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_heure",
        (sejour_id,),
    )


def historique_analyte(base: Base, sejour_id: str, id_analyte: str) -> list[dict]:
    """Série temporelle d'un seul analyte — pour les courbes de cinétique
    (SPEC §7.2)."""
    return base.requete(
        "SELECT date_heure, valeur_num FROM bilan_resultat "
        "WHERE sejour_id = ? AND analyte = ? AND supprime = 0 ORDER BY date_heure",
        (sejour_id, id_analyte),
    )


def gaz_du_sang_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM gaz_du_sang WHERE sejour_id = ? AND supprime = 0 ORDER BY date_heure",
        (sejour_id,),
    )


def _plus_recent(lignes: list[dict], date_jour: str | None) -> dict | None:
    """La ligne la plus récente, filtrée sur un jour si fourni (partie date
    de `date_heure`)."""
    candidates = [l for l in lignes if not date_jour or l["date_heure"].startswith(date_jour)]
    return candidates[-1] if candidates else None


def dernier_gaz_du_sang(base: Base, sejour_id: str, date_jour: str | None = None) -> dict | None:
    return _plus_recent(gaz_du_sang_du_sejour(base, sejour_id), date_jour)


def resultats_du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[str, dict]:
    """id d'analyte -> dernière ligne de ce jour-là."""
    par_analyte: dict[str, dict] = {}
    for ligne in resultats_du_sejour(base, sejour_id):
        if ligne["date_heure"].startswith(date_jour):
            par_analyte[ligne["analyte"]] = ligne  # la dernière écrase les précédentes
    return par_analyte


# --------------------------------------------------------------------------
# Texte généré — même regroupement que le fichier HTML fourni
# --------------------------------------------------------------------------

def _ligne(titre: str, paires: list[tuple[str, float | str | None, str]]) -> str | None:
    remplies = [(lib, v, u) for lib, v, u in paires if v is not None and v != ""]
    if not remplies:
        return None
    morceaux = []
    for lib, v, u in remplies:
        texte_v = v if isinstance(v, str) else _formate_nombre(v)
        suffixe = f" {u}" if u else ""
        morceaux.append(f"{lib} = {texte_v}{suffixe}")
    return f"- {titre} : " + " ; ".join(morceaux)


def _formate_nombre(v: float) -> str:
    if float(v) == int(v):
        return str(int(v))
    return str(v)


def texte_genere(base: Base, sejour_id: str, date_jour: str) -> str:
    """Reproduit le format du fichier HTML fourni : un groupe par ligne,
    seuls les champs remplis apparaissent (SPEC pptx écran 5 : « Seuls les
    champs remplis sortent »)."""
    r = resultats_du_jour(base, sejour_id, date_jour)

    def v(id_analyte: str) -> float | None:
        ligne = r.get(id_analyte)
        return ligne["valeur_num"] if ligne else None

    lignes = []
    # L'ordre du catalogue, pas une liste recopiée ici : elle divergeait de
    # l'écran de saisie à la première réorganisation, et l'observation ne se
    # relisait plus dans l'ordre où elle avait été remplie. Les analytes
    # ajoutés par le service y entrent du même coup.
    courants, occasionnels = cat.groupes_de_saisie()
    for groupe in courants + occasionnels:
        paires = [(a.libelle, v(a.id), a.unite) for a in groupe.analytes]
        texte = _ligne(groupe.titre, paires)
        if texte:
            lignes.append(texte)

    gds = dernier_gaz_du_sang(base, sejour_id, date_jour)
    if gds:
        code_mode = gds["mode_ventilatoire"]
        mode = listes.libelle_mode_court(code_mode)
        parametres = listes.parametres_du_mode(code_mode)
        if "debit_o2" in parametres and gds["debit_o2"]:
            mode = f"{mode} {_formate_nombre(gds['debit_o2'])}L"
        # Seuls les paramètres qui ont un sens pour ce mode : une PEP recopiée
        # sous air ambiant est une valeur que personne n'a mesurée.
        vent = _ligne("Ventilation", [
            ("Mode", mode, ""),
            *[(lib, gds[cle] if cle in parametres else None, unite)
              for cle, lib, unite in (("fio2", "FiO₂", "%"), ("pep", "PEP", "cmH₂O"),
                                      ("fr", "FR", "/min"), ("ai", "AI", "cmH₂O"),
                                      ("vt", "Vt", "mL"))],
            ("SpO₂", gds["spo2"], "%"),
        ])
        if vent:
            lignes.append(vent)
        ratio = rapport_pao2_fio2(gds["pao2"], gds["fio2"])
        gaz = _ligne("Gaz du sang", [
            ("pH", gds["ph"], ""), ("PaO₂", gds["pao2"], "mmHg"), ("PaCO₂", gds["paco2"], "mmHg"),
            ("HCO₃⁻", gds["hco3"], "mmol/L"), ("Lactates", gds["lactate"], "mmol/L"),
            ("PaO₂/FiO₂", ratio, ""),
        ])
        if gaz:
            lignes.append(gaz)

    return "\n".join(lignes)

# --------------------------------------------------------------------------
# Cinétique — la façon dont un clinicien lit des bilans (SPEC §7.2)
# --------------------------------------------------------------------------
# Un médecin ne lit pas une valeur isolée : il lit une ligne d'analyte à
# travers les jours, et ce qui a bougé depuis la veille. D'où : un tableau
# analytes × dates, une variation par rapport au prélèvement précédent, et
# des panneaux par organe plutôt qu'une liste alphabétique.

PANELS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("infection", "Infection", ("crp", "gb", "plq")),
    ("renal", "Rénal", ("creat", "uree", "k", "na")),
    ("hemato", "Hématologie", ("hb", "hte", "plq", "tp", "inr")),
    ("hepatique", "Hépatique", ("asat", "alat", "bili", "bili_d", "ggt", "pal")),
    ("iono", "Ionogramme", ("na", "k", "cl", "ca")),
)


def dates_de_prelevement(base: Base, sejour_id: str) -> list[str]:
    """Dates-heures distinctes, de la plus ancienne à la plus récente."""
    lignes = base.requete(
        "SELECT DISTINCT date_heure FROM bilan_resultat "
        "WHERE sejour_id = ? AND supprime = 0 ORDER BY date_heure",
        (sejour_id,),
    )
    return [l["date_heure"] for l in lignes]


def tableau_par_date(
    base: Base, sejour_id: str, ids_analytes: list[str] | None = None
) -> tuple[list[str], dict[str, dict[str, float]]]:
    """(dates, {analyte: {date: valeur}}) — la matrice que lit le clinicien.

    Une seule valeur par analyte et par prélèvement : si le même analyte a
    été saisi deux fois pour le même horodatage, la dernière écrase, comme
    une correction de saisie.
    """
    resultats = resultats_du_sejour(base, sejour_id)
    if ids_analytes:
        resultats = [r for r in resultats if r["analyte"] in ids_analytes]
    matrice: dict[str, dict[str, float]] = {}
    dates: list[str] = []
    for r in resultats:
        if r["date_heure"] not in dates:
            dates.append(r["date_heure"])
        matrice.setdefault(r["analyte"], {})[r["date_heure"]] = r["valeur_num"]
    return sorted(dates), matrice


@dataclass
class Variation:
    """Dernière valeur d'un analyte et ce qui a changé depuis la précédente."""

    analyte: str
    libelle: str
    unite: str
    valeur: float | None
    precedente: float | None
    date_heure: str | None
    alerte: str | None  # 'bas' / 'haut' / None

    @property
    def delta(self) -> float | None:
        if self.valeur is None or self.precedente is None:
            return None
        return round(self.valeur - self.precedente, 2)


def dernieres_variations(base: Base, sejour_id: str, ids_analytes: list[str]) -> list[Variation]:
    """Pour chaque analyte demandé : dernière valeur, valeur précédente,
    et signalement hors bornes. C'est ce qui alimente les tuiles de tête."""
    variations = []
    for id_analyte in ids_analytes:
        historique = historique_analyte(base, sejour_id, id_analyte)
        a = cat.analyte(id_analyte)
        derniere = historique[-1] if historique else None
        precedente = historique[-2] if len(historique) >= 2 else None
        valeur = derniere["valeur_num"] if derniere else None
        variations.append(
            Variation(
                analyte=id_analyte,
                libelle=a.libelle,
                unite=a.unite,
                valeur=valeur,
                precedente=precedente["valeur_num"] if precedente else None,
                date_heure=derniere["date_heure"] if derniere else None,
                alerte=a.hors_bornes(valeur),
            )
        )
    return variations


def analytes_renseignes(base: Base, sejour_id: str) -> list[str]:
    """Analytes réellement saisis pour ce séjour, dans l'ordre du catalogue —
    inutile de proposer une courbe pour un analyte jamais mesuré."""
    presents = {r["analyte"] for r in resultats_du_sejour(base, sejour_id)}
    return [i for i in cat.tous_les_ids() if i in presents]
