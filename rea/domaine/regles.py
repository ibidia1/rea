"""Moteur de règles d'aide — déclaratif (feuille de route, règle R4).

« Les règles d'aide sont déclaratives » : le moteur ne connaît aucune règle.
Il sait lire des conditions et les évaluer sur des faits ; les règles elles-
mêmes vivent dans `regles/*.json`, avec leur source et leur version. Ajouter
un rappel, en changer le seuil ou en retirer un ne demande pas de toucher au
code — donc ne demande pas d'informaticien.

Ce que ces règles ne font jamais (SPEC §3.1) :
* elles ne calculent aucune dose et n'en proposent aucune ;
* elles ne bloquent rien : ce sont des questions posées au médecin, pas des
  décisions prises à sa place.

Couche C5, fonctions pures : des faits entrent, des rappels sortent.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ConditionInvalide(ValueError):
    """Une règle mal écrite doit se voir tout de suite, pas se taire.

    Une condition silencieusement fausse ferait disparaître un rappel sans
    que personne ne s'en aperçoive — le pire des deux mondes.
    """


@dataclass(frozen=True)
class Regle:
    code: str
    libelle: str
    message: str
    gravite: str = "info"          # info · attention · alerte
    source: str = ""               # d'où vient la règle (référence publiée)
    valide: bool = False           # signée par un senior du service ?
    signe_par: str | None = None
    conditions: tuple = ()
    combinaison: str = "et"        # 'et' | 'ou'
    faits_utilises: tuple = field(default_factory=tuple)

    @classmethod
    def depuis_dict(cls, donnees: dict) -> "Regle":
        conditions = tuple(donnees.get("conditions", ()))
        return cls(
            code=donnees["code"],
            libelle=donnees["libelle"],
            message=donnees["message"],
            gravite=donnees.get("gravite", "info"),
            source=donnees.get("source", ""),
            valide=bool(donnees.get("valide", False)),
            signe_par=donnees.get("signe_par"),
            conditions=conditions,
            combinaison=donnees.get("combinaison", "et"),
            faits_utilises=tuple(
                c["fait"] for c in conditions if isinstance(c, dict) and "fait" in c
            ),
        )


# --------------------------------------------------------------------------
# Évaluation d'une condition
# --------------------------------------------------------------------------
# Un vocabulaire volontairement court : tout ce qui ne s'exprime pas ici n'a
# rien à faire dans un fichier de règles, mais dans le code du domaine, testé.
_OPERATEURS = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "contient": lambda a, b: b in (a or ()),
    "ne_contient_pas": lambda a, b: b not in (a or ()),
}
# Ces deux-là ne comparent rien : ils interrogent la présence du fait.
_UNAIRES = ("renseigne", "non_renseigne", "vrai", "faux")


def evaluer_condition(condition: dict, faits: dict) -> bool:
    if "fait" not in condition or "op" not in condition:
        raise ConditionInvalide(f"Condition sans « fait » ou « op » : {condition}")
    nom, operateur = condition["fait"], condition["op"]
    valeur = faits.get(nom)

    if operateur in _UNAIRES:
        if operateur == "renseigne":
            return valeur is not None
        if operateur == "non_renseigne":
            return valeur is None
        return bool(valeur) if operateur == "vrai" else not bool(valeur)

    if operateur not in _OPERATEURS:
        raise ConditionInvalide(f"Opérateur inconnu : {operateur}")
    if "valeur" not in condition:
        raise ConditionInvalide(f"Condition sans « valeur » : {condition}")
    if valeur is None:
        # Un fait non renseigné ne déclenche rien : « on ne sait pas » n'est
        # pas « anormal » (règle de conception 7). Le rappel qui doit se
        # déclencher justement parce qu'une donnée manque s'écrit avec
        # l'opérateur « non_renseigne ».
        return False
    try:
        return _OPERATEURS[operateur](valeur, condition["valeur"])
    except TypeError as erreur:
        raise ConditionInvalide(
            f"Comparaison impossible sur « {nom} » : {valeur!r} {operateur} "
            f"{condition['valeur']!r}"
        ) from erreur


def declenchee(regle: Regle, faits: dict) -> bool:
    if not regle.conditions:
        return False
    resultats = [evaluer_condition(c, faits) for c in regle.conditions]
    return any(resultats) if regle.combinaison == "ou" else all(resultats)


_ORDRE_GRAVITE = {"alerte": 0, "attention": 1, "info": 2}


def declenchees(regles, faits: dict) -> list[Regle]:
    """Les règles qui s'appliquent, les plus graves d'abord."""
    retenues = [r for r in regles if declenchee(r, faits)]
    return sorted(retenues, key=lambda r: (_ORDRE_GRAVITE.get(r.gravite, 9), r.code))


# --------------------------------------------------------------------------
# Check-list quotidienne (FAST HUG)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ItemChecklist:
    code: str
    lettre: str
    libelle: str
    question: str
    etat: str          # 'ok' · 'a_verifier' · 'non_renseigne'
    detail: str = ""


def evaluer_checklist(items, faits: dict) -> list[ItemChecklist]:
    """Chaque item déclare la condition qui le rend satisfait.

    Trois états, jamais deux : « fait », « à vérifier », et « on ne sait
    pas » — parce qu'un item qu'on n'a pas renseigné n'est pas un item raté
    (règle de conception 7).
    """
    resultats = []
    for item in items:
        conditions = item.get("satisfait_si", ())
        faits_requis = [c["fait"] for c in conditions if "fait" in c]
        if faits_requis and all(faits.get(f) is None for f in faits_requis):
            etat = "non_renseigne"
        else:
            regle = Regle.depuis_dict(
                {
                    "code": item["code"],
                    "libelle": item["libelle"],
                    "message": "",
                    "conditions": list(conditions),
                    "combinaison": item.get("combinaison", "et"),
                }
            )
            etat = "ok" if declenchee(regle, faits) else "a_verifier"
        resultats.append(
            ItemChecklist(
                code=item["code"],
                lettre=item.get("lettre", ""),
                libelle=item["libelle"],
                question=item.get("question", ""),
                etat=etat,
                detail=item.get("detail", ""),
            )
        )
    return resultats
