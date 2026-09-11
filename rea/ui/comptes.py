"""Gérer les comptes — réservé aux rôles qui portent le droit « comptes »
(SPEC §2.5).

Un mot sur ce que cet écran promet et ne promet pas, parce que c'est le genre
de malentendu qui coûte cher : **les rôles organisent l'application, le code
d'accès la protège**. Tant qu'un compte n'a pas de code, son nom reste
sélectionnable par n'importe qui à l'ouverture, et son rôle avec. L'écran le
dit en toutes lettres plutôt que de laisser croire à une serrure.

Un compte ne se supprime pas : il se désactive. Effacer un compte rendrait
anonymes toutes les prescriptions qu'il a signées, et le journal d'audit
n'aurait plus de sens (règle de conception 2).
"""

from __future__ import annotations

import streamlit as st

from .. import config
from ..domaine import droits as dom_droits
from ..services import utilisateurs as utilisateurs_service
from . import theme


def ecran(base, utilisateur_id: str | None = None) -> None:
    st.subheader("Comptes du service")
    comptes = utilisateurs_service.tous(base)
    sans_code = [u for u in comptes if u["actif"] and not u["pin"]]
    if sans_code:
        st.warning(
            f"**{len(sans_code)} compte(s) sans code d'accès.** Leur nom peut "
            "être choisi par n'importe qui à l'ouverture : leur rôle organise "
            "l'écran, il ne protège pas le dossier. Poser un code ci-dessous "
            "ferme cette porte, compte par compte.",
            icon="⚠️",
        )

    _demandes_de_code(base, utilisateur_id)
    _creer(base, utilisateur_id)
    st.divider()
    _liste(base, comptes, utilisateur_id)


def _demandes_de_code(base, utilisateur_id) -> None:
    """Les codes oubliés qui attendent une réponse — tout en haut de l'écran.

    En haut parce que c'est la seule chose ici qui bloque quelqu'un : tant
    qu'elle n'est pas traitée, une infirmière ne peut pas prendre son poste.
    Le reste de cet écran peut attendre le lendemain.

    L'administrateur confirme avant que quoi que ce soit ne bouge. C'est lui
    qui sait si la personne devant lui est bien celle du compte — le logiciel,
    lui, ne voit qu'un nom dans une liste (demande du service, 11 septembre).
    """
    demandes = utilisateurs_service.demandes_de_code(base)
    if not demandes:
        return

    st.warning(
        f"**{len(demandes)} demande(s) de code oublié.** Tant qu'elles ne "
        "sont pas traitées, ces personnes ne peuvent pas entrer.",
        icon="🔑",
    )
    for demande in demandes:
        c1, c2, c3 = st.columns([4, 2, 2])
        c1.markdown(
            f"**{demande['nom']}** — {dom_droits.libelle(demande['role'])}<br>"
            f"<span style='font-size:.78rem;color:#94a3b8'>"
            f"demandé le {demande['demande_le'].replace('T', ' à ')}</span>",
            unsafe_allow_html=True,
        )
        cle = f"remise_{demande['id']}"
        if c2.button("Remettre à zéro", key=f"rz_{demande['id']}",
                     use_container_width=True, type="primary"):
            st.session_state[cle] = True
        if c3.button("Ignorer", key=f"ig_{demande['id']}",
                     use_container_width=True):
            utilisateurs_service.refuser_la_demande(
                base, demande["id"], utilisateur_id=utilisateur_id
            )
            st.rerun()

        if st.session_state.get(cle):
            # Une confirmation, parce que le geste donne un code connu de
            # tous à un compte qui peut valoir un accès au dossier. Deux
            # clics, et le second dit ce qui va se passer.
            st.error(
                f"**Confirmer la remise à zéro du code de « {demande['nom']} » ?**\n\n"
                f"Son code deviendra **`{config.CODE_INITIAL}`**, à lui dire de "
                "vive voix. Ce code est écrit dans le logiciel : il ne protège "
                "rien, et le compte réclamera un vrai code dès la première "
                "entrée. Le blocage des essais ratés sera également levé.",
                icon="⚠️",
            )
            oui, non = st.columns(2)
            if oui.button("Oui, remettre le code à zéro",
                          key=f"oui_{demande['id']}", type="primary",
                          use_container_width=True):
                try:
                    nom = utilisateurs_service.reinitialiser_le_code(
                        base, demande["id"], utilisateur_id=utilisateur_id
                    )
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    st.session_state.pop(cle, None)
                    st.success(
                        f"Code de « {nom} » remis à `{config.CODE_INITIAL}`. "
                        "Le lui dire de vive voix."
                    )
                    st.rerun()
            if non.button("Annuler", key=f"non_{demande['id']}",
                          use_container_width=True):
                st.session_state.pop(cle, None)
                st.rerun()
    st.divider()


def _creer(base, utilisateur_id) -> None:
    with st.expander("Créer un compte", expanded=not utilisateurs_service.tous(base)):
        with st.form("creer_compte"):
            c1, c2 = st.columns(2)
            nom = c1.text_input("Nom", placeholder="ex. Dr Ben Salah")
            role = c2.selectbox(
                "Rôle", dom_droits.roles(), format_func=dom_droits.libelle,
            )
            c3, c4 = st.columns(2)
            code = c3.text_input("Code d'accès", type="password",
                                 placeholder="6 chiffres conseillés")
            telephone = c4.text_input(
                "Téléphone", placeholder="ex. 55 123 456",
                help="Affiché au médecin dans le Prescrit, pour appeler "
                     "directement la personne qui s'occupe du patient.",
            )
            # Un code qu'on choisit pour quelqu'un d'autre, on le lui dit :
            # deux personnes le connaissent, et ce n'est donc pas encore le
            # sien. C'est aussi le seul moyen d'ouvrir un compte quand
            # l'application est sur le réseau — un compte sans code y est
            # refusé à l'entrée, il ne pourrait jamais entrer poser le sien.
            provisoire = st.checkbox(
                "Code provisoire — la personne en choisira un à sa première "
                "entrée",
                value=True,
                help="À laisser coché : le code tapé ici, vous le lui direz. "
                     "Le sien, personne d'autre ne le connaîtra.",
            )
            st.caption(_description_du_role(role))
            if st.form_submit_button("Créer le compte", type="primary"):
                try:
                    utilisateurs_service.creer(
                        base, nom, role, code=code or None,
                        code_provisoire=provisoire,
                        telephone=telephone or None,
                        utilisateur_id=utilisateur_id,
                    )
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    st.success(f"Compte « {nom.strip()} » créé.")
                    st.rerun()


def _description_du_role(role: str) -> str:
    droits = sorted(dom_droits.droits_du_role(role))
    lisibles = {
        "dossier_lire": "voir les dossiers",
        "dossier_ecrire": "modifier les dossiers (prescrit, bilans, évolution)",
        "protocoles": "écrire et signer les protocoles",
        "comptes": "gérer les comptes",
        "administrations": "cocher les traitements donnés",
        "constantes": "saisir la surveillance horaire",
        "supervision": "voir l'écran du surveillant",
        "recherche": "cohortes et indicateurs",
    }
    return "Peut : " + ", ".join(lisibles.get(d, d) for d in droits) + "."


def _liste(base, comptes, utilisateur_id) -> None:
    for compte in comptes:
        etat = "actif" if compte["actif"] else "désactivé"
        if not compte["pin"]:
            code = "**sans code d'accès**"
        elif compte["code_provisoire"]:
            code = "**code provisoire** — pas encore changé"
        else:
            code = "code d'accès posé"
        tel = compte["telephone"] or "pas de numéro"
        c1, c2, c3, c4 = st.columns([3, 2, 1.6, 1.4])
        c1.markdown(
            f"**{compte['nom']}**<br>"
            f"<span style='font-size:.78rem;color:#94a3b8'>"
            f"{etat} · {code} · {tel}</span>",
            unsafe_allow_html=True,
        )
        roles = list(dom_droits.roles())
        nouveau = c2.selectbox(
            "Rôle", roles,
            index=roles.index(compte["role"]) if compte["role"] in roles else 0,
            format_func=dom_droits.libelle, key=f"role_{compte['id']}",
            label_visibility="collapsed",
        )
        if nouveau != compte["role"]:
            try:
                utilisateurs_service.modifier_role(
                    base, compte["id"], nouveau, utilisateur_id=utilisateur_id
                )
            except ValueError as erreur:
                st.error(str(erreur))
            else:
                st.rerun()

        with c3.popover("Modifier", use_container_width=True):
            saisi = st.text_input("Nouveau code", type="password",
                                  key=f"code_{compte['id']}")
            provisoire = st.checkbox(
                "Provisoire — à changer à la prochaine entrée",
                value=True, key=f"prov_{compte['id']}",
                help="Un code réinitialisé se dit à voix haute : deux "
                     "personnes le connaissent tant qu'il n'est pas changé.",
            )
            if st.button("Enregistrer le code", key=f"code_ok_{compte['id']}"):
                utilisateurs_service.definir_code(
                    base, compte["id"], saisi or None, provisoire=provisoire,
                    utilisateur_id=utilisateur_id,
                )
                st.rerun()
            numero = st.text_input("Téléphone", value=compte["telephone"] or "",
                                   key=f"tel_{compte['id']}")
            if st.button("Enregistrer le numéro", key=f"tel_ok_{compte['id']}"):
                utilisateurs_service.definir_telephone(
                    base, compte["id"], numero, utilisateur_id=utilisateur_id
                )
                st.rerun()
            if compte["pin"] and st.button("Retirer le code",
                                           key=f"code_non_{compte['id']}"):
                utilisateurs_service.definir_code(
                    base, compte["id"], None, utilisateur_id=utilisateur_id
                )
                st.rerun()

        if compte["actif"]:
            if c4.button("Désactiver", key=f"off_{compte['id']}",
                         use_container_width=True):
                try:
                    utilisateurs_service.desactiver(base, compte["id"],
                                                    utilisateur_id=utilisateur_id)
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    st.rerun()
        elif c4.button("Réactiver", key=f"on_{compte['id']}",
                       use_container_width=True):
            utilisateurs_service.reactiver(base, compte["id"],
                                           utilisateur_id=utilisateur_id)
            st.rerun()

    theme.bloc_html(
        "Pourquoi désactiver et non supprimer",
        "Un compte effacé rendrait anonymes toutes les prescriptions qu'il a "
        "signées, et le journal d'audit n'aurait plus de sens. Un compte "
        "désactivé ne peut plus entrer ; ce qu'il a écrit garde son nom.",
        theme.GRIS,
    )
