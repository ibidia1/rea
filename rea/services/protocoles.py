"""Poser au dossier les lignes d'un protocole signé (SPEC §4.5).

Ce module existe parce que deux écrans en ont besoin, pas un : l'admission,
où un protocole se déclenche sur le motif d'entrée, et l'évolution, où il se
déclenche sur une règle d'aide — une kaliémie effondrée ne s'annonce pas le
jour de l'admission. Le geste étant le même, il n'a pas à être écrit deux fois
ni à voyager d'un écran à l'autre.

Les quatre règles de sécurité du §4.5 tiennent ici :

1. Seul un protocole **validé et signé** arrive jusqu'ici — le filtre est en
   amont, dans `protocoles.protocoles_valides()`.
2. Le pré-remplissage est **proposé**, jamais appliqué : cette fonction n'est
   appelée que sur un clic explicite.
3. Chaque ligne posée est une ligne de prescription **ordinaire**, modifiable
   et supprimable comme les autres.
4. Elle porte le code et la version du protocole : six mois plus tard, on sait
   de quelle version du protocole vient ce qui a été prescrit.

**Un protocole signé a le droit de porter une dose** (décision du service,
9 septembre). Le §3.1 dit que *le logiciel* ne calcule ni ne propose de
posologie, et cela ne change pas : ce qui arrive dans la ligne n'est pas un
calcul, c'est le texte qu'un senior a écrit et signé. Un protocole de
correction de kaliémie sans dose ne sert à rien — c'est la dose qui est le
protocole. La ligne posée reste modifiable, et c'est le prescripteur qui
signe.
"""

from __future__ import annotations

from ..db import Base
from . import prescriptions as prescriptions_service


def appliquer(
    base: Base,
    sejour_id: str,
    protocoles_choisis: list,
    *,
    date_debut: str,
    utilisateur_id: str | None = None,
) -> int:
    """Pose les lignes des protocoles choisis. Rend le nombre de lignes posées.

    La posologie écrite dans le protocole est reprise telle quelle — dose,
    unité, rythme, vitesse. Elle vient du senior qui a signé le fichier, pas
    d'un calcul du logiciel : c'est ce qui la distingue de ce que le §3.1
    interdit. Un champ absent du protocole reste vide dans la ligne, il n'est
    pas deviné.
    """
    posees = 0
    for protocole in protocoles_choisis:
        for ligne in protocole.lignes_prescription:
            if not ligne.get("voie") or not ligne.get("produit"):
                continue
            prescriptions_service.ajouter_ligne(
                base, sejour_id=sejour_id, voie=ligne["voie"],
                produit=ligne["produit"], date_debut=date_debut,
                rythme=ligne.get("rythme") or None,
                dose=_nombre(ligne.get("dose")),
                unite=ligne.get("unite") or None,
                vitesse=_nombre(ligne.get("vitesse")),
                dilution=ligne.get("dilution") or None,
                condition_texte=ligne.get("note") or None,
                protocole_code=protocole.code, protocole_version=protocole.version,
                utilisateur_id=utilisateur_id,
            )
            posees += 1
    return posees


def _nombre(valeur) -> float | None:
    """Une dose écrite « 1,5 » dans un fichier relu à la main doit passer.

    Ce qui n'est pas un nombre ne devient pas zéro : il devient absent. Une
    dose à zéro dans une prescription se lit comme une décision.
    """
    if valeur is None or valeur == "":
        return None
    try:
        return float(str(valeur).replace(",", "."))
    except (TypeError, ValueError):
        return None
