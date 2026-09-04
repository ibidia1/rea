"""Écran Administration — sauvegardes, restauration, journal, référentiels.

Trois choses que la feuille de route exige avant tout le reste (bloc 0), et
qui n'existaient jusqu'ici que dans le code :

* une sauvegarde qu'on peut **restaurer** — sinon elle n'existe pas ;
* un journal d'audit **lisible** — sinon « qui a modifié quoi » n'est pas
  reconstituable ;
* la **version des référentiels et des protocoles** affichée — sinon deux
  statistiques produites à six mois d'écart sont comparées à tort.
"""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from .. import aides, config, protocoles, referentiels
from ..db import Base
from . import theme


def _taille(octets: int) -> str:
    if octets < 1024 * 1024:
        return f"{octets / 1024:.0f} Ko"
    return f"{octets / (1024 * 1024):.1f} Mo"


def ecran(base: Base, utilisateur_id: str | None = None) -> None:
    st.title("Administration")
    st.caption(
        f"Base : `{base.chemin}` · sauvegardes : `{config.DOSSIER_SAUVEGARDES}` · "
        f"une sauvegarde automatique toutes les {config.INTERVALLE_SAUVEGARDE_MINUTES} min"
    )

    onglets = st.tabs(
        ["Sauvegardes", "Journal", "Référentiels", "Protocoles", "Règles d'aide"]
    )
    with onglets[0]:
        _sauvegardes(base)
    with onglets[1]:
        _journal(base)
    with onglets[2]:
        _referentiels()
    with onglets[3]:
        _protocoles()
    with onglets[4]:
        _regles()


# --------------------------------------------------------------------------
# Sauvegardes et restauration
# --------------------------------------------------------------------------

def _sauvegardes(base: Base) -> None:
    gauche, droite = st.columns([1, 2], gap="large")

    with gauche:
        if st.button("💾 Sauvegarder maintenant", use_container_width=True,
                     type="primary"):
            chemin = base.sauvegarder(motif="manuelle")
            st.success(f"Sauvegarde écrite : {chemin.name}")
        st.caption(
            f"{config.SAUVEGARDES_CONSERVEES} sauvegardes conservées, "
            "les plus anciennes sont effacées automatiquement."
        )

    disponibles = base.sauvegardes_disponibles()
    with droite:
        if not disponibles:
            st.info("Aucune sauvegarde pour l'instant.")
            return
        lignes = [
            f"<tr><td>{s['date'].replace('T', ' ')}</td>"
            f"<td>{s['nom']}</td><td style='text-align:right'>{_taille(s['taille'])}</td></tr>"
            for s in disponibles[:15]
        ]
        theme.bloc_html(
            f"{len(disponibles)} sauvegardes",
            "<table style='width:100%;font-size:0.85rem'>"
            + "".join(lignes)
            + "</table>",
            theme.BLEU,
        )

    st.divider()
    st.subheader("Restaurer")
    st.warning(
        "Restaurer remplace **toute** la base actuelle par la sauvegarde choisie. "
        "L'état actuel est sauvegardé juste avant : l'opération reste réversible.",
        icon="⚠️",
    )
    noms = [f"{s['date'].replace('T', ' ')} — {s['nom']}" for s in disponibles]
    choix = st.selectbox("Sauvegarde à restaurer", noms, index=None,
                         placeholder="Choisir une sauvegarde")
    confirme = st.checkbox("Je confirme vouloir remplacer la base actuelle")
    if st.button("↺ Restaurer", disabled=not (choix and confirme)):
        selection = disponibles[noms.index(choix)]
        filet = base.restaurer(selection["chemin"])
        st.success(
            f"Base restaurée depuis {selection['nom']}. "
            f"L'état précédent reste disponible dans {filet.name}."
        )
        st.session_state.pop("sejour_id", None)


# --------------------------------------------------------------------------
# Journal d'audit
# --------------------------------------------------------------------------

_ACTIONS = {
    "creation": ("Création", theme.VERT),
    "modification": ("Modification", theme.BLEU),
    "suppression": ("Suppression", theme.ROUGE),
    "restauration": ("Restauration", theme.VIOLET),
}


def _journal(base: Base) -> None:
    tables = [
        ligne["table_cible"]
        for ligne in base.requete(
            "SELECT DISTINCT table_cible FROM journal ORDER BY table_cible"
        )
    ]
    gauche, droite = st.columns([1, 3])
    with gauche:
        table = st.selectbox("Table", ["(toutes)"] + tables)
        limite = st.number_input("Lignes", 20, 2000, 200, step=20)
    lignes = base.journal(limite=int(limite),
                          table=None if table == "(toutes)" else table)
    with droite:
        st.caption(
            "Chaque écriture est tracée : date, utilisateur, table, action et "
            "détail. Aucune ligne n'est jamais effacée de la base — une "
            "suppression est un marquage (règle de conception 2)."
        )
    if not lignes:
        st.info("Journal vide.")
        return

    corps = []
    for ligne in lignes:
        libelle, couleur = _ACTIONS.get(ligne["action"], (ligne["action"], theme.GRIS))
        details = ligne["details"] or ""
        try:
            details = ", ".join(
                f"{k} = {v}" for k, v in json.loads(details).items() if v not in (None, "")
            )
        except (ValueError, AttributeError):
            pass
        corps.append(
            "<tr>"
            f"<td style='white-space:nowrap'>{(ligne['date_heure'] or '').replace('T', ' ')}</td>"
            f"<td>{ligne.get('utilisateur_nom') or '—'}</td>"
            f"<td><b>{ligne['table_cible']}</b></td>"
            f"<td style='color:{couleur}'>{libelle}</td>"
            f"<td style='color:#64748b'>{details[:160]}</td>"
            "</tr>"
        )
    st.markdown(
        "<div style='max-height:520px;overflow:auto'>"
        "<table style='width:100%;font-size:0.82rem;border-collapse:collapse'>"
        "<thead><tr style='text-align:left;color:#64748b'>"
        "<th>Date</th><th>Utilisateur</th><th>Table</th><th>Action</th><th>Détail</th>"
        "</tr></thead><tbody>" + "".join(corps) + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Référentiels et protocoles — quelle liste, dans quelle version
# --------------------------------------------------------------------------

def _referentiels() -> None:
    st.caption(
        "Les listes codées sont des fichiers, pas du code : les modifier ne "
        f"demande pas de reprogrammer le logiciel. Dossier : `{referentiels.DOSSIER}`. "
        "Après modification d'un fichier, redémarrer l'application."
    )
    inventaire = referentiels.inventaire()
    if not inventaire:
        st.error("Aucun référentiel trouvé — l'installation est incomplète.")
        return
    versions = {ligne["version"] for ligne in inventaire}
    if len(versions) > 1:
        st.warning(
            "Plusieurs versions cohabitent : " + ", ".join(sorted(versions))
            + ". C'est permis, mais il faut le savoir avant de comparer deux "
            "extractions.",
            icon="⚠️",
        )
    corps = "".join(
        f"<tr><td><b>{l['libelle']}</b><br>"
        f"<span style='color:#94a3b8;font-size:0.78rem'>{l['nom']}.json</span></td>"
        f"<td style='text-align:right'>{l['nb_valeurs']}</td>"
        f"<td style='white-space:nowrap'>{l['version']}</td></tr>"
        for l in inventaire
    )
    st.markdown(
        "<table style='width:100%;font-size:0.85rem;border-collapse:collapse'>"
        "<thead><tr style='text-align:left;color:#64748b'>"
        "<th>Référentiel</th><th style='text-align:right'>Valeurs</th><th>Version</th>"
        "</tr></thead><tbody>" + corps + "</tbody></table>",
        unsafe_allow_html=True,
    )


def _protocoles() -> None:
    st.caption(
        "Un protocole n'est proposé à l'écran que s'il est **validé et signé** "
        "par le chef de service (SPEC §4.5). Les autres restent des brouillons."
    )
    tous = protocoles.tous_les_protocoles()
    if not tous:
        st.info("Aucun protocole installé.")
        return
    for p in tous:
        etat = (
            f"✅ validé — signé par {p.signe_par}" if p.valide and p.signe_par
            else "🚧 brouillon — non proposé à l'écran"
        )
        theme.bloc(
            p.titre,
            [
                f"Version {p.version} du {p.date_version}",
                etat,
                f"{len(p.lignes_prescription)} lignes de prescription, "
                f"{len(p.explorations_proposees)} explorations, "
                f"{len(p.consignes)} consignes",
            ],
            theme.VERT if p.valide else theme.ORANGE,
        )


def _regles() -> None:
    st.caption(
        "Les rappels et la check-list quotidienne sont déclaratifs : ils vivent "
        f"dans `{aides.DOSSIER}`, avec leurs seuils et leurs sources. Les modifier "
        "ne demande pas de reprogrammer le logiciel — c'est la règle R4 de la "
        "feuille de route. Aucun ne propose de posologie (SPEC §3.1)."
    )
    for jeu in aides.inventaire():
        etat = (
            f"✅ validé — signé par {jeu['signe_par']}" if jeu["valide"] and jeu["signe_par"]
            else "🚧 en service mais non signé — à valider par un senior"
        )
        lignes = [f"Version {jeu['version']} · {jeu['nb']} règles", etat]
        if jeu["source"]:
            lignes.append(jeu["source"])
        theme.bloc(jeu["titre"], lignes, theme.VERT if jeu["valide"] else theme.ORANGE)
