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

    Chaque ligne part **sans dose** (SPEC §3.1 — le logiciel ne calcule ni ne
    propose de posologie) : le protocole ne préremplit que voie, produit,
    rythme, et sa note. C'est une contrainte du projet, pas une limite
    technique : elle laisse la dose à celui qui signe la prescription.
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
                condition_texte=ligne.get("note") or None,
                protocole_code=protocole.code, protocole_version=protocole.version,
                utilisateur_id=utilisateur_id,
            )
            posees += 1
    return posees
