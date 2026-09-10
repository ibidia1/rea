"""L'ouverture : qui est devant l'écran (SPEC §1.2 et §2.5).

Le sélecteur est obligatoire — sans lui, aucune écriture ne porterait de nom
et le journal d'audit ne servirait à rien.

Ce qu'il faut savoir sur le code d'accès, parce que c'est le point où l'on se
raconte facilement des histoires : **il est demandé quand le compte en a un**.
Un service qui démarre n'en met nulle part et le logiciel s'ouvre comme avant ;
le jour où l'administrateur en pose un, ce compte devient inaccessible sans
lui. C'est ce qui permet de protéger d'abord les comptes qui comptent — celui
qui gère les comptes, ceux qui signent les protocoles — sans bloquer le
service un matin de garde.

Tant qu'un compte n'a pas de code, son rôle organise l'écran mais ne protège
rien : n'importe qui peut choisir son nom. L'écran des comptes le dit, et
celui-ci ne prétend pas le contraire.
"""

from __future__ import annotations

import streamlit as st

from .. import config
from ..db import Base
from ..domaine import droits as dom_droits
from ..services import utilisateurs as utilisateurs_service


def utilisateurs_actifs(base: Base) -> list[dict]:
    return utilisateurs_service.actifs(base)


def selecteur(base: Base) -> str | None:
    """Affiche l'ouverture. Retourne l'id de l'utilisateur courant, ou None
    tant qu'aucun n'est entré — l'appelant doit alors bloquer la suite."""
    if "utilisateur_id" in st.session_state:
        return st.session_state["utilisateur_id"]

    st.title("Réanimation polyvalente")
    utilisateurs = utilisateurs_actifs(base)

    if not utilisateurs:
        return _premier_compte(base)

    sans_code = utilisateurs_service.comptes_sans_code(base)
    if config.AUTH_EXIGEE and sans_code:
        # L'application est joignable depuis un téléphone du service : un
        # compte sans code n'est plus une commodité, c'est une porte ouverte
        # sur le dossier. On le dit ici, où quelqu'un le lira.
        st.error(
            f"**{len(sans_code)} compte(s) sans code d'accès**, alors que "
            "l'application est joignable depuis le réseau. Tant que ces "
            "comptes n'ont pas de code, n'importe quel téléphone du service "
            "peut entrer sous leur nom. À corriger dans "
            "Administration → Comptes.",
            icon="⚠️",
        )
    st.caption("Sélection obligatoire avant toute saisie (SPEC §1.2)")
    noms = [u["nom"] for u in utilisateurs]
    with st.form("selecteur_utilisateur"):
        choix = st.selectbox("Qui êtes-vous ?", noms, index=None,
                             placeholder="Choisir son nom")
        code = st.text_input(
            "Code d'accès", type="password",
            help="À laisser vide si aucun code n'a été posé sur ce compte.",
        )
        valide = st.form_submit_button("Entrer", type="primary")

    if valide:
        if not choix:
            st.error("Choisir un nom.")
            return None
        compte = next(u for u in utilisateurs if u["nom"] == choix)

        reste = utilisateurs_service.blocage_restant(choix)
        if reste:
            st.error(
                f"Trop d'essais ratés sur ce compte. Réessayer dans "
                f"{reste} minute(s)."
            )
            return None

        if config.AUTH_EXIGEE and not compte["pin"]:
            st.error(
                "Ce compte n'a pas de code d'accès et l'application est "
                "joignable depuis le réseau : l'entrée est refusée. Un "
                "administrateur doit lui poser un code."
            )
            return None

        if compte["pin"] and not utilisateurs_service.code_correct(code, compte["pin"]):
            utilisateurs_service.noter_echec(choix)
            # Un message qui ne dit pas *ce qui* est faux : « code incorrect »
            # confirmerait au passage que ce compte a bien un code.
            st.error("Nom ou code d'accès incorrect.")
            return None

        utilisateurs_service.oublier_echecs(choix)
        _entrer(compte)

    st.caption(
        "Un compte oublié ou un code perdu se règle dans "
        "Administration → Comptes, depuis un compte administrateur."
    )
    return None


def _premier_compte(base: Base) -> str | None:
    """La toute première ouverture : il faut bien un administrateur.

    Sans ce cas particulier, une base neuve n'a aucun compte, donc personne
    pour en créer — et le seul recours serait d'ouvrir la base à la main.
    """
    st.info(
        "**Première ouverture.** Créons le compte administrateur : c'est lui "
        "qui créera ensuite les comptes du service. Le code d'accès est "
        "facultatif, mais fortement conseillé pour ce compte-là."
    )
    with st.form("premier_compte"):
        nom = st.text_input("Nom", placeholder="ex. Dr Karaa")
        code = st.text_input("Code d'accès", type="password")
        if st.form_submit_button("Créer et entrer", type="primary"):
            if config.AUTH_EXIGEE:
                refus = utilisateurs_service.code_acceptable(code)
                if refus:
                    st.error(refus)
                    return None
            try:
                uid = utilisateurs_service.creer(base, nom, "admin", code=code or None)
            except ValueError as erreur:
                st.error(str(erreur))
                return None
            _entrer(utilisateurs_service.par_id(base, uid))
    return None


def _entrer(compte: dict) -> None:
    st.session_state["utilisateur_id"] = compte["id"]
    st.session_state["utilisateur_nom"] = compte["nom"]
    st.session_state["utilisateur_role"] = compte["role"]
    st.rerun()


def nom_utilisateur_courant() -> str:
    return st.session_state.get("utilisateur_nom", "")


#: Le rôle réellement porté par le compte connecté — jamais celui d'un essai.
def role_reel() -> str | None:
    return st.session_state.get("utilisateur_role")


def role_courant() -> str | None:
    """Le rôle dont l'écran doit tenir compte, essai compris.

    Un administrateur peut demander à voir l'application **comme** un
    infirmier ou un surveillant, pour vérifier ce que chacun trouve à son
    écran sans avoir à connaître le code de quelqu'un d'autre.

    Ce que cet essai change : les écrans proposés et les droits qu'ils
    consultent. Ce qu'il ne change **jamais** : l'identité qui signe. Tout ce
    qui s'écrit pendant l'essai reste signé par l'administrateur, parce
    qu'une observation signée du nom d'un infirmier qui ne l'a pas écrite est
    un faux dans un dossier médical.

    Et l'essai ne peut que **retirer** des droits : seul un administrateur
    peut l'ouvrir, et il les a tous. Aucun rôle d'essai ne donne accès à ce
    que le compte n'aurait pas déjà.
    """
    return st.session_state.get("role_essai") or role_reel()


def role_essaye() -> str | None:
    """Le rôle qu'on est en train d'essayer, ou None hors essai."""
    return st.session_state.get("role_essai")


def essayer_role(role: str | None) -> None:
    from ..domaine import droits as _droits

    if not dom_droits.peut(role_reel(), "comptes"):
        raise PermissionError("Seul un administrateur peut essayer un rôle.")
    if role and role not in _droits.roles():
        raise ValueError(f"Rôle inconnu : {role}")
    if role:
        st.session_state["role_essai"] = role
    else:
        st.session_state.pop("role_essai", None)
    # L'écran courant appartenait au rôle précédent : le garder afficherait
    # une page à laquelle le nouveau rôle n'a pas droit. On pose donc
    # directement l'accueil du rôle visé — plutôt que d'effacer le drapeau
    # « accueil posé », ce qui laisserait le point d'entrée reposer cet
    # accueil au rerun suivant, par-dessus une destination demandée entre-temps.
    from . import contexte

    contexte.poser_accueil(role_courant())


def peut(droit: str) -> bool:
    """Le droit du compte connecté, tel que l'écran doit le voir.

    Lu depuis la session et non de la base : c'est un appel par bouton
    affiché, et le rôle ne change pas au milieu d'une session. Les services,
    eux, relisent la base — c'est là que la vérification compte.
    """
    return dom_droits.peut(role_courant(), droit)


def changer_utilisateur() -> None:
    for cle in ("utilisateur_id", "utilisateur_nom", "utilisateur_role",
                "role_essai", "accueil_pose", "ecran", "sejour_id"):
        st.session_state.pop(cle, None)
    st.rerun()
