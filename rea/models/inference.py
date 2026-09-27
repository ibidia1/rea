"""Les outils statistiques du service, écrits à la main (couche domaine).

Pourquoi à la main : le poste du service n'installe que Streamlit, et ces
calculs tiennent chacun en quelques lignes vérifiables — un intervalle de
Wilson, un intervalle de Poisson exact, un Kaplan-Meier, une aire sous la
courbe ROC, les limites d'une carte de contrôle. Chaque fonction cite sa
méthode ; les tests la vérifient contre des valeurs publiées.

Ce que ce module apporte à l'écran Recherche, c'est la **précision** d'un
chiffre. Dans un service de douze lits, « 30 % de mortalité » sur dix patients
veut dire « quelque part entre 11 et 60 % » : l'intervalle de confiance dit
cela, là où une p-value ne le dit pas. On affiche donc des intervalles, pas des
tests — le choix déjà fait pour les croisements (un tableau univarié, non
ajusté, monocentrique ne démontre rien, et un « p < 0,05 » à côté serait lu
comme une preuve).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Quantile de la loi normale pour un intervalle à 95 %.
Z95 = 1.959963984540054


@dataclass(frozen=True)
class Intervalle:
    """Une estimation et son intervalle de confiance à 95 %."""

    valeur: float
    bas: float
    haut: float

    def texte(self, *, pourcent: bool = False, decimales: int = 0) -> str:
        f = 100 if pourcent else 1
        u = " %" if pourcent else ""
        fmt = f"{{:.{decimales}f}}"
        return (f"{fmt.format(self.valeur * f)}{u} "
                f"[IC95 {fmt.format(self.bas * f)}–{fmt.format(self.haut * f)}]"
                ).replace(".", ",")


# --------------------------------------------------------------------------
# Proportions — intervalle de Wilson
# --------------------------------------------------------------------------

def wilson(succes: int, n: int, z: float = Z95) -> Intervalle | None:
    """Intervalle de Wilson (score) d'une proportion.

    Préféré à l'intervalle « p ± 1,96·√(p(1-p)/n) » qui, sur les petits
    effectifs d'un service, sort de [0 ; 1] et donne un intervalle nul pour
    0/8 — comme si zéro décès sur huit patients prouvait une mortalité nulle.
    Wilson EB. J Am Stat Assoc 1927;22:209-12 ; Brown, Cai, DasGupta. Stat
    Sci 2001;16:101-33.
    """
    if n <= 0 or succes < 0 or succes > n:
        return None
    p = succes / n
    z2 = z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    demi = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return Intervalle(p, max(0.0, centre - demi), min(1.0, centre + demi))


# --------------------------------------------------------------------------
# Comptes et taux — Poisson exact
# --------------------------------------------------------------------------

def _poisson_cdf(k: int, lam: float) -> float:
    """P(X ≤ k) pour X ~ Poisson(lam), en logarithmes pour rester stable."""
    if lam <= 0:
        return 1.0
    total, terme = 0.0, -lam
    for i in range(k + 1):
        if i:
            terme += math.log(lam) - math.log(i)
        total += math.exp(terme)
    return min(total, 1.0)


def _bissection(f, bas: float, haut: float) -> float:
    for _ in range(200):
        milieu = (bas + haut) / 2
        if f(milieu):
            haut = milieu
        else:
            bas = milieu
    return (bas + haut) / 2


def poisson_exact(k: int, alpha: float = 0.05) -> tuple[float, float]:
    """Intervalle exact (Garwood) du paramètre d'une loi de Poisson observée
    à k. Garwood F. Biometrika 1936;28:437-42."""
    if k < 0:
        raise ValueError("k doit être positif")
    haut_recherche = max(10.0, k * 4 + 20)
    bas = 0.0 if k == 0 else _bissection(
        lambda lam: 1 - _poisson_cdf(k - 1, lam) >= alpha / 2, 0.0, haut_recherche)
    haut = _bissection(lambda lam: _poisson_cdf(k, lam) <= alpha / 2, 0.0, haut_recherche)
    return bas, haut


def taux(evenements: int, exposition: float, par: float = 1000) -> Intervalle | None:
    """Un taux (infections pour 1000 jours-dispositif, extubations non
    programmées pour 100 jours de ventilation…) et son intervalle exact."""
    if exposition <= 0:
        return None
    bas, haut = poisson_exact(evenements)
    return Intervalle(evenements / exposition * par,
                      bas / exposition * par, haut / exposition * par)


def rapport_standardise(observes: int, attendus: float) -> Intervalle | None:
    """Rapport observé / attendu (SMR), intervalle exact sur les observés.

    Les décès attendus sont une somme de probabilités prédites : on les
    traite comme connus, l'incertitude portant sur les observés (méthode
    usuelle ; Breslow & Day, IARC 1987, vol. II).
    """
    if attendus <= 0:
        return None
    bas, haut = poisson_exact(observes)
    return Intervalle(observes / attendus, bas / attendus, haut / attendus)


# --------------------------------------------------------------------------
# Délais jusqu'à un événement — Kaplan-Meier
# --------------------------------------------------------------------------

@dataclass
class KaplanMeier:
    """Courbe de Kaplan-Meier : pour chaque instant où survient un
    événement, la proportion encore « sans événement »."""

    temps: list[float] = field(default_factory=list)
    survie: list[float] = field(default_factory=list)
    effectif: int = 0
    evenements: int = 0
    censures: int = 0

    @property
    def mediane(self) -> float | None:
        """Premier instant où la courbe passe sous 50 %. None si elle ne
        l'atteint pas : la médiane n'est alors pas estimable, et le dire vaut
        mieux que de rendre la médiane des seuls patients qui ont eu
        l'événement."""
        for t, s in zip(self.temps, self.survie):
            if s <= 0.5:
                return t
        return None

    def proportion_evenement_a(self, t: float) -> float | None:
        """1 − S(t) : la part ayant eu l'événement au temps t."""
        if not self.effectif:
            return None
        s = 1.0
        for ti, si in zip(self.temps, self.survie):
            if ti > t:
                break
            s = si
        return 1 - s


def kaplan_meier(observations: list[tuple[float, bool]]) -> KaplanMeier:
    """`observations` : (délai, événement survenu ?). Un délai sans événement
    est **censuré** : le patient est suivi jusque-là, puis on ne sait plus.

    C'est exactement le piège du délai d'apyrexie : un patient encore fébrile
    à l'arrêt du traitement n'a pas un délai long, il a un délai inconnu au-
    delà de sa durée de suivi. L'ignorer fait paraître efficace un traitement
    sous lequel peu de patients décrochent. Kaplan EL, Meier P. J Am Stat
    Assoc 1958;53:457-81.
    """
    km = KaplanMeier(effectif=len(observations))
    km.evenements = sum(1 for _t, e in observations if e)
    km.censures = km.effectif - km.evenements
    a_risque = len(observations)
    s = 1.0
    for t in sorted({t for t, _e in observations}):
        d = sum(1 for ti, e in observations if ti == t and e)
        c = sum(1 for ti, e in observations if ti == t and not e)
        if d:
            s *= 1 - d / a_risque
            km.temps.append(t)
            km.survie.append(s)
        a_risque -= d + c
    return km


# --------------------------------------------------------------------------
# Discrimination d'un score — aire sous la courbe ROC
# --------------------------------------------------------------------------

def auroc(scores_evenement: list[float], scores_sans: list[float]) -> Intervalle | None:
    """Aire sous la courbe ROC (statistique C) et son IC de Hanley-McNeil.

    Répond à : « le score classe-t-il plus haut ceux qui meurent ? ». 0,5 =
    pas mieux que le hasard, 0,8 = bonne discrimination. Hanley JA, McNeil
    BJ. Radiology 1982;143:29-36.
    """
    n1, n2 = len(scores_evenement), len(scores_sans)
    if not n1 or not n2:
        return None
    concordants = 0.0
    for a in scores_evenement:
        for b in scores_sans:
            concordants += 1.0 if a > b else 0.5 if a == b else 0.0
    aire = concordants / (n1 * n2)
    q1 = aire / (2 - aire)
    q2 = 2 * aire * aire / (1 + aire)
    variance = (aire * (1 - aire) + (n1 - 1) * (q1 - aire ** 2)
                + (n2 - 1) * (q2 - aire ** 2)) / (n1 * n2)
    se = math.sqrt(max(variance, 0.0))
    return Intervalle(aire, max(0.0, aire - Z95 * se), min(1.0, aire + Z95 * se))


# --------------------------------------------------------------------------
# Suivi dans le temps — carte de contrôle p
# --------------------------------------------------------------------------

@dataclass
class PointControle:
    periode: str
    n: int
    evenements: int
    proportion: float | None
    limite_basse: float | None
    limite_haute: float | None
    signal: str = ""          # pourquoi ce point mérite qu'on s'y arrête


def carte_p(periodes: list[tuple[str, int, int]], *, serie_minimale: int = 8
            ) -> tuple[float | None, list[PointControle]]:
    """Carte de contrôle p (Shewhart) : `periodes` = (libellé, n, événements).

    La ligne centrale est la proportion moyenne ; les limites à ±3 écarts-
    types dépendent de l'effectif du mois — un mois à 4 admissions a des
    limites larges, c'est normal. Un point est signalé s'il sort des limites
    (cause spéciale probable) ou s'il appartient à une série d'au moins huit
    points du même côté de la ligne centrale (glissement durable). Tout le
    reste est la variation ordinaire, qu'il ne faut pas « expliquer » mois
    par mois. Benneyan JC et al. Qual Saf Health Care 2003;12:458-64.
    """
    total_n = sum(n for _p, n, _e in periodes)
    if not total_n:
        return None, []
    centre = sum(e for _p, _n, e in periodes) / total_n
    points = []
    for libelle, n, e in periodes:
        if n <= 0:
            points.append(PointControle(libelle, 0, 0, None, None, None))
            continue
        sigma = math.sqrt(centre * (1 - centre) / n)
        points.append(PointControle(
            libelle, n, e, e / n,
            max(0.0, centre - 3 * sigma), min(1.0, centre + 3 * sigma),
        ))
    for p in points:
        if p.proportion is None:
            continue
        if p.proportion > p.limite_haute or p.proportion < p.limite_basse:
            p.signal = "hors des limites"
    # Série : points consécutifs strictement du même côté de la ligne.
    serie: list[PointControle] = []
    cote_courant = 0
    for p in points + [None]:
        cote = 0 if p is None or p.proportion is None else (
            1 if p.proportion > centre else -1 if p.proportion < centre else 0)
        if cote and cote == cote_courant:
            serie.append(p)
            continue
        if len(serie) >= serie_minimale:
            for q in serie:
                q.signal = q.signal or f"série de {len(serie)} du même côté"
        serie = [p] if cote else []
        cote_courant = cote
    return centre, points
