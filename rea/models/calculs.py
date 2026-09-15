"""Valeurs dérivées d'un bilan (couche C2).

Trois règles, qui découlent du SPEC §3.1 :

1. Le logiciel calcule des **grandeurs physiologiques**, jamais une dose et
   jamais une adaptation de posologie. Une clairance est une grandeur ; ce
   qu'on en fait reste au médecin.
2. Chaque calcul porte **sa formule et sa référence** dans le code. Une
   définition non écrite est une définition qui changera silencieusement.
3. Un calcul rend `None` dès qu'il manque une donnée. Il n'invente jamais une
   valeur par défaut — c'est la règle des trois états appliquée aux calculs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValeurCalculee:
    """Une valeur dérivée, avec de quoi la justifier à un relecteur."""

    cle: str
    libelle: str
    valeur: float | None
    unite: str
    formule: str
    reference: str
    commentaire: str | None = None

    @property
    def disponible(self) -> bool:
        return self.valeur is not None


# --------------------------------------------------------------------------
# Clairance de la créatinine
# --------------------------------------------------------------------------

def clairance_cockcroft_gault(
    *,
    creatinine_umol_l: float | None,
    poids_kg: float | None,
    age_ans: int | None,
    sexe: str | None,
) -> ValeurCalculee:
    """Cockcroft & Gault, 1976 — la formule qui demande le poids, d'où
    l'ajout du poids à l'admission.

        Cl = (140 − âge) × poids × k / créatinine(µmol/L)
        k = 1,23 chez l'homme · 1,04 chez la femme

    ⚠️ Le résultat est une **grandeur physiologique**, pas une consigne. Le
    logiciel n'en déduit jamais une adaptation de posologie (SPEC §3.1).
    """
    valeur = None
    if (
        creatinine_umol_l
        and poids_kg
        and age_ans is not None
        and sexe in ("M", "F")
        and creatinine_umol_l > 0
    ):
        k = 1.23 if sexe == "M" else 1.04
        valeur = round((140 - age_ans) * poids_kg * k / creatinine_umol_l, 1)
        if valeur < 0:
            valeur = None  # âge supérieur à 140 : la formule n'a plus de sens
    return ValeurCalculee(
        cle="clairance_cg",
        libelle="Clairance (Cockcroft-Gault)",
        valeur=valeur,
        unite="mL/min",
        formule="(140 − âge) × poids × k / créatinine ; k = 1,23 H / 1,04 F",
        reference="Cockcroft DW, Gault MH. Nephron 1976;16:31-41",
        commentaire="Grandeur physiologique — aucune adaptation de dose n'en est déduite.",
    )


# --------------------------------------------------------------------------
# Poids idéal théorique
# --------------------------------------------------------------------------

def poids_ideal_devine(*, taille_cm: float | None, sexe: str | None) -> ValeurCalculee:
    """Formule de Devine, adaptée aux centimètres :

        Homme : 50   + 0,91 × (taille − 152,4)
        Femme : 45,5 + 0,91 × (taille − 152,4)

    Le poids idéal ne remplace jamais le poids réel : il sert de référence
    (volume courant en ventilation protectrice, par exemple). Les deux sont
    conservés côte à côte, le réel étant celui qui entre dans la clairance.
    """
    valeur = None
    # En dessous d'environ 1,20 m, la formule sort de son domaine de validité
    # et rendrait un poids absurde : on préfère ne rien afficher.
    if taille_cm and taille_cm >= 120 and sexe in ("M", "F"):
        base_poids = 50.0 if sexe == "M" else 45.5
        valeur = round(base_poids + 0.91 * (taille_cm - 152.4), 1)
    return ValeurCalculee(
        cle="poids_ideal",
        libelle="Poids idéal (Devine)",
        valeur=valeur,
        unite="kg",
        formule="50 (H) ou 45,5 (F) + 0,91 × (taille − 152,4)",
        reference="Devine BJ. Drug Intell Clin Pharm 1974;8:650-5",
        commentaire="Référence théorique — ne remplace pas le poids réel.",
    )


# --------------------------------------------------------------------------
# Valeurs corrigées — « si disponibles », jamais imposées
# --------------------------------------------------------------------------

def natremie_corrigee(
    *, natremie_mmol_l: float | None, glycemie_mmol_l: float | None
) -> ValeurCalculee:
    """Natrémie corrigée à la glycémie.

        Na corrigée = Na + 1,6 × (glycémie − 5,6) / 5,6      [mmol/L]

    soit +1,6 mmol/L par tranche de 100 mg/dL (5,6 mmol/L) au-dessus de la
    normale. En dessous de 5,6 mmol/L de glycémie, la correction n'a pas lieu
    d'être : on rend la natrémie telle quelle.
    """
    valeur = None
    if natremie_mmol_l is not None and glycemie_mmol_l is not None:
        exces = max(glycemie_mmol_l - 5.6, 0)
        valeur = round(natremie_mmol_l + 1.6 * exces / 5.6, 1)
    return ValeurCalculee(
        cle="na_corrige",
        libelle="Natrémie corrigée",
        valeur=valeur,
        unite="mmol/L",
        formule="Na + 1,6 × (glycémie − 5,6) / 5,6",
        reference="Katz MA. N Engl J Med 1973;289:843-4",
    )


def calcemie_corrigee(
    *, calcemie_mmol_l: float | None, albumine_g_l: float | None
) -> ValeurCalculee:
    """Calcémie corrigée à l'albuminémie.

        Ca corrigée = Ca + 0,02 × (40 − albumine)            [mmol/L]

    Indispensable en réanimation, où l'hypoalbuminémie fait sous-estimer la
    calcémie totale.
    """
    valeur = None
    if calcemie_mmol_l is not None and albumine_g_l is not None:
        valeur = round(calcemie_mmol_l + 0.02 * (40 - albumine_g_l), 2)
    return ValeurCalculee(
        cle="ca_corrige",
        libelle="Calcémie corrigée",
        valeur=valeur,
        unite="mmol/L",
        formule="Ca + 0,02 × (40 − albumine)",
        reference="Payne RB et al. Br Med J 1973;4:643-6",
    )


def rapport_pao2_fio2(pao2: float | None, fio2: float | None) -> ValeurCalculee:
    """Rapport P/F. La FiO₂ est saisie en % ; le rapport attend une fraction."""
    valeur = None
    if pao2 is not None and fio2:
        valeur = round(pao2 / (fio2 / 100))
    return ValeurCalculee(
        cle="pf",
        libelle="PaO₂/FiO₂",
        valeur=valeur,
        unite="",
        formule="PaO₂ / (FiO₂ / 100)",
        reference="Définition de Berlin, JAMA 2012;307:2526-33",
    )


def pression_arterielle_moyenne(
    *, pas: float | None, pad: float | None
) -> ValeurCalculee:
    """PAM estimée depuis la pression au brassard.

    Ce n'est pas une mesure : c'est l'estimation classique, qui suppose que la
    diastole occupe les deux tiers du cycle. Elle s'écarte du vrai quand la
    fréquence s'emballe (la diastole raccourcit) — ce qui est le cas de la
    moitié des patients d'un service de réanimation. Une PAM lue sur un
    cathéter artériel doit primer sur celle-ci : c'est pourquoi la valeur est
    calculée à l'affichage et jamais écrite en base, où elle finirait par se
    confondre avec une mesure invasive.

    Saisir la PAM à côté de la PAS et de la PAD était en outre une occasion
    d'incohérence : trois cases, dont une déductible des deux autres, et rien
    qui garantisse qu'elles s'accordent (demande du service, 8 septembre).
    """
    valeur = None
    if pas is not None and pad is not None:
        valeur = round((float(pas) + 2 * float(pad)) / 3)
    return ValeurCalculee(
        cle="pam",
        libelle="PAM",
        valeur=valeur,
        unite="mmHg",
        formule="(PAS + 2 × PAD) / 3",
        reference="Estimation usuelle au brassard ; une PAM invasive lui est "
                  "préférée quand elle existe",
    )


def trou_anionique(
    *, na: float | None, cl: float | None, hco3: float | None
) -> ValeurCalculee:
    """Trou anionique, sans le potassium (convention la plus répandue)."""
    valeur = None
    if na is not None and cl is not None and hco3 is not None:
        valeur = round(na - (cl + hco3), 1)
    return ValeurCalculee(
        cle="trou_anionique",
        libelle="Trou anionique",
        valeur=valeur,
        unite="mmol/L",
        formule="Na − (Cl + HCO₃⁻)",
        reference="Emmett M, Narins RG. Medicine 1977;56:38-54",
    )


def toutes_les_valeurs(
    *,
    resultats: dict[str, float | None],
    gaz: dict[str, float | None] | None = None,
    poids_kg: float | None = None,
    taille_cm: float | None = None,
    age_ans: int | None = None,
    sexe: str | None = None,
) -> list[ValeurCalculee]:
    """Toutes les valeurs dérivées possibles pour un bilan donné.

    Celles dont les ingrédients manquent sont rendues avec `valeur = None` :
    l'appelant décide de les masquer ou d'afficher pourquoi elles manquent.
    """
    gaz = gaz or {}
    return [
        poids_ideal_devine(taille_cm=taille_cm, sexe=sexe),
        clairance_cockcroft_gault(
            creatinine_umol_l=resultats.get("creat"),
            poids_kg=poids_kg, age_ans=age_ans, sexe=sexe,
        ),
        natremie_corrigee(
            natremie_mmol_l=resultats.get("na"), glycemie_mmol_l=resultats.get("glycemie")
        ),
        calcemie_corrigee(
            calcemie_mmol_l=resultats.get("ca"), albumine_g_l=resultats.get("albumine")
        ),
        trou_anionique(
            na=resultats.get("na"), cl=resultats.get("cl"), hco3=gaz.get("hco3")
        ),
        rapport_pao2_fio2(gaz.get("pao2"), gaz.get("fio2")),
    ]
