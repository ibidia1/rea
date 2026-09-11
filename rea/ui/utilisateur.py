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


def _entete_accueil(base: Base) -> None:
    """Le titre, et l'accès administrateur en haut à droite.

    Là, sur l'écran d'ouverture, et non une fois entré : l'administrateur qui
    vient débloquer un collègue ou créer un compte n'a pas de raison de
    traverser l'application d'abord. Il cherche le bouton où on cherche un
    bouton — dans le coin (demande du service, 11 septembre).

    Le bouton ne donne rien de plus qu'un raccourci : il présélectionne les
    comptes administrateurs dans la liste, et le code reste exigé. Une porte
    qui s'ouvrirait d'un clic ne serait pas une porte.
    """
    gauche, droite = st.columns([5, 1])
    with gauche:
        st.title("Réanimation polyvalente")
    with droite:
        if not utilisateurs_service.administrateurs(base):
            return
        st.write("")
        if st.button("Accès admin", use_container_width=True,
                     help="Entrer avec un compte administrateur"):
            st.session_state["accueil_admin"] = not st.session_state.get(
                "accueil_admin", False
            )
            st.rerun()


def selecteur(base: Base) -> str | None:
    """Affiche l'ouverture. Retourne l'id de l'utilisateur courant, ou None
    tant qu'aucun n'est entré — l'appelant doit alors bloquer la suite."""
    if "utilisateur_id" in st.session_state:
        courant = utilisateurs_service.par_id(base, st.session_state["utilisateur_id"])
        if courant and courant["code_provisoire"]:
            # Le code de `config.py` est public : tant qu'il sert, ce compte
            # n'est pas protégé. On ne laisse donc pas passer vers un dossier
            # — la demande de code n'est pas un rappel qu'on peut remettre à
            # plus tard, c'est la porte elle-même.
            st.title("Réanimation polyvalente")
            _remplacer_le_code_provisoire(base, courant)
            return None
        return st.session_state["utilisateur_id"]

    _entete_accueil(base)
    utilisateurs = utilisateurs_actifs(base)

    if not utilisateurs:
        return _premier_compte(base)

    provisoires = utilisateurs_service.comptes_a_code_provisoire(base)
    if provisoires:
        noms_provisoires = ", ".join(f"« {u['nom']} »" for u in provisoires)
        st.error(
            f"**Code de départ encore en place** sur {noms_provisoires}. Ce "
            f"code (`{config.CODE_INITIAL}`) est écrit dans le logiciel : "
            "tout le monde peut le lire. Entrer avec ce compte demandera d'en "
            "choisir un autre, et c'est seulement à ce moment-là que le "
            "compte protège quelque chose.",
            icon="🔓",
        )

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
    # « Accès admin » ne fait que filtrer la liste : le code reste exigé, et
    # une porte qui s'ouvrirait d'un clic ne serait pas une porte.
    if st.session_state.get("accueil_admin"):
        administrateurs = utilisateurs_service.administrateurs(base)
        if administrateurs:
            utilisateurs = administrateurs
            st.info(
                "**Accès administrateur** — seuls les comptes qui gèrent les "
                "comptes sont proposés. Le code reste demandé.",
                icon="🔑",
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

    _code_oublie(base, utilisateurs)
    if utilisateurs_service.sans_administrateur(base):
        _designer_un_administrateur(base, utilisateurs)
    return None


def _code_oublie(base: Base, utilisateurs: list[dict]) -> None:
    """« J'ai oublié mon code » — une demande, pas une remise à zéro.

    La personne ne peut pas remettre son code elle-même : ce serait une porte
    ouverte à qui saurait un nom. Elle dépose une demande que l'administrateur
    voit dans Administration → Comptes, et à laquelle il répond en
    connaissance de cause — c'est lui qui sait si la personne devant lui est
    bien celle du compte (demande du service, 11 septembre).

    Ce qu'on lui dit ici est exactement ce qui va se passer, et rien de plus :
    promettre un déblocage immédiat à quelqu'un qui attend l'administrateur
    lui ferait réessayer dix fois.
    """
    with st.expander("J'ai oublié mon code d'accès"):
        st.write(
            "Votre code ne peut pas être retrouvé — le logiciel n'en garde "
            "qu'une empreinte, jamais le code lui-même. Un administrateur "
            "peut le **remettre à zéro** : il vous donnera alors un code "
            "provisoire, et vous en choisirez un nouveau en entrant."
        )
        noms = [u["nom"] for u in utilisateurs]
        nom = st.selectbox("Quel compte ?", noms, index=None,
                           placeholder="Choisir son nom", key="oubli_nom")
        if not nom:
            return
        compte = next(u for u in utilisateurs if u["nom"] == nom)

        deja = [
            d for d in utilisateurs_service.demandes_de_code(base)
            if d["utilisateur_id"] == compte["id"]
        ]
        if deja:
            st.success(
                f"Une demande est déjà déposée pour « {nom} ». Prévenir un "
                "administrateur : il la traitera depuis Administration → "
                "Comptes.",
                icon="✅",
            )
            return

        if st.button("Demander la remise à zéro de mon code",
                     key="oubli_demander", type="primary"):
            try:
                utilisateurs_service.demander_un_code(base, compte["id"])
            except ValueError as erreur:
                st.error(str(erreur))
            else:
                st.rerun()


def _designer_un_administrateur(base: Base, utilisateurs: list[dict]) -> None:
    """La base a des comptes, mais aucun administrateur.

    C'est l'état d'un service qui tournait avant que les rôles n'existent :
    personne n'a le droit « comptes », donc le bouton Admin ne s'affiche pour
    personne, et le seul recours serait la ligne de commande — c'est-à-dire,
    en pratique, personne. Cette porte-ci ne s'ouvre que dans ce cas précis,
    et se referme dès qu'un administrateur existe.

    Elle ne donne rien à qui n'avait rien : il faut le code du compte que
    l'on promeut, et un compte sans code doit en recevoir un au passage.
    """
    st.divider()
    with st.expander("Aucun compte administrateur — en désigner un", expanded=True):
        st.warning(
            "Cette base n'a aucun compte capable de gérer les comptes : "
            "personne ne peut donc créer un compte, poser un code, ni ouvrir "
            "le bouton **Admin**. Désigner ci-dessous un compte existant — "
            "son code d'accès est demandé, et un compte qui n'en a pas doit "
            "en recevoir un ici."
        )
        if utilisateurs_service.rien_n_est_protege(base):
            # Aucun compte n'a de code : il n'y a pas de serrure à forcer, et
            # créer l'administrateur de départ ne retire donc rien à personne.
            # Le raccourci disparaît dès qu'un seul compte est protégé.
            st.caption(
                f"Aucun compte de cette base n'a de code d'accès. Le compte "
                f"**{config.COMPTE_INITIAL_NOM}** peut donc être créé "
                "administrateur directement — il demandera un vrai code dès "
                "la première entrée."
            )
            if st.button(f"Créer le compte {config.COMPTE_INITIAL_NOM}",
                         key="creer_admin_initial"):
                try:
                    identifiant = utilisateurs_service.creer_compte_initial(base)
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    _entrer(utilisateurs_service.par_id(base, identifiant))
            st.divider()
        noms = [u["nom"] for u in utilisateurs]
        with st.form("designer_administrateur"):
            nom = st.selectbox("Quel compte devient administrateur ?", noms,
                               index=None, placeholder="Choisir un compte")
            code = st.text_input(
                "Son code d'accès actuel", type="password",
                help="À laisser vide si ce compte n'a pas encore de code.",
            )
            nouveau = st.text_input(
                "Code d'accès à poser sur ce compte", type="password",
                help="Obligatoire si le compte n'a pas encore de code ; "
                     "sinon, à laisser vide pour garder l'actuel.",
            )
            if st.form_submit_button("Désigner et entrer", type="primary"):
                if not nom:
                    st.error("Choisir un compte.")
                    return
                compte = next(u for u in utilisateurs if u["nom"] == nom)
                try:
                    utilisateurs_service.designer_administrateur(
                        base, compte["id"], code=code, nouveau_code=nouveau or None
                    )
                except ValueError as erreur:
                    st.error(str(erreur))
                    return
                _entrer(utilisateurs_service.par_id(base, compte["id"]))


def _premier_compte(base: Base) -> str | None:
    """La toute première ouverture : il faut bien un administrateur.

    Sans ce cas particulier, une base neuve n'a aucun compte, donc personne
    pour en créer — et le seul recours serait d'ouvrir la base à la main.
    """
    st.info(
        "**Première ouverture.** Il faut un compte administrateur : c'est lui "
        "qui créera ensuite les comptes du service — médecins, infirmiers, "
        "surveillants — et qui leur donnera leur rôle."
    )
    st.markdown(
        f"Le plus simple : le compte **{config.COMPTE_INITIAL_NOM}**, avec le "
        f"code de départ `{config.CODE_INITIAL}`. Ce code est écrit dans le "
        "logiciel, donc connu de tous : le compte demandera d'en choisir un "
        "vrai dès la première entrée, et n'ouvrira rien avant."
    )
    if st.button(f"Créer le compte {config.COMPTE_INITIAL_NOM} et entrer",
                 type="primary", key="premier_compte_initial"):
        try:
            identifiant = utilisateurs_service.creer_compte_initial(base)
        except ValueError as erreur:
            st.error(str(erreur))
            return None
        _entrer(utilisateurs_service.par_id(base, identifiant))

    with st.expander("Ou choisir un autre nom et son code tout de suite"):
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
                    uid = utilisateurs_service.creer(base, nom, "admin",
                                                     code=code or None)
                except ValueError as erreur:
                    st.error(str(erreur))
                    return None
                _entrer(utilisateurs_service.par_id(base, uid))
    return None


def _remplacer_le_code_provisoire(base: Base, compte: dict) -> None:
    """La porte du compte créé avec le code public : en choisir un vrai.

    Elle n'est pas contournable et ne se remet pas à plus tard — c'est tout
    l'intérêt d'un code de départ dont on assume qu'il ne protège rien. Rien
    d'autre ne s'affiche tant qu'il n'est pas remplacé.
    """
    st.warning(
        f"Bonjour **{compte['nom']}**. Ce compte porte encore le code de "
        f"départ `{config.CODE_INITIAL}`, qui est écrit dans le logiciel et "
        "que tout le monde peut lire. Choisir un vrai code avant d'ouvrir un "
        "dossier — c'est la seule chose qui protège ce compte, et il "
        "administre tous les autres.",
        icon="🔓",
    )
    with st.form("remplacer_code_provisoire"):
        code = st.text_input("Nouveau code d'accès", type="password")
        confirmation = st.text_input("Le retaper", type="password")
        if st.form_submit_button("Enregistrer et continuer", type="primary"):
            refus = utilisateurs_service.code_acceptable(code)
            if refus:
                st.error(refus)
                return
            if code == config.CODE_INITIAL:
                st.error("C'est le code de départ : en choisir un autre.")
                return
            if code != confirmation:
                st.error("Les deux codes saisis sont différents.")
                return
            utilisateurs_service.definir_code(
                base, compte["id"], code, utilisateur_id=compte["id"]
            )
            st.rerun()

    if st.button("Sortir sans changer le code"):
        st.session_state.pop("utilisateur_id", None)
        st.session_state.pop("utilisateur_nom", None)
        st.session_state.pop("utilisateur_role", None)
        st.rerun()


def mon_code(base: Base) -> None:
    """Chacun pose et change son propre code, sans passer par personne.

    Un administrateur peut poser un code pour quelqu'un — il le lui dit alors
    de vive voix, et le connaît. Un code que son propriétaire choisit lui-même
    n'est connu que de lui : c'est la différence entre un rôle qui organise
    l'écran et une identité qui signe. Un infirmier qui prend son poste à 7 h
    n'a pas non plus à chercher un administrateur pour entrer.
    """
    identifiant = st.session_state.get("utilisateur_id")
    compte = utilisateurs_service.par_id(base, identifiant)
    if not compte:
        return
    etiquette = "Mon code d'accès" if compte["pin"] else "⚠️ Poser mon code d'accès"
    with st.popover(etiquette, use_container_width=True):
        if compte["pin"]:
            actuel = st.text_input("Code actuel", type="password", key="mc_actuel")
        else:
            st.caption(
                "Ce compte n'a pas encore de code : n'importe qui peut choisir "
                "votre nom à l'ouverture, et signer à votre place."
            )
            actuel = ""
        nouveau = st.text_input("Nouveau code", type="password", key="mc_nouveau")
        confirmation = st.text_input("Le retaper", type="password", key="mc_bis")
        if st.button("Enregistrer mon code", key="mc_ok", type="primary"):
            if compte["pin"] and not utilisateurs_service.code_correct(
                actuel, compte["pin"]
            ):
                st.error("Code actuel incorrect.")
                return
            refus = utilisateurs_service.code_acceptable(nouveau)
            if refus:
                st.error(refus)
                return
            if nouveau != confirmation:
                st.error("Les deux codes saisis sont différents.")
                return
            utilisateurs_service.definir_code(
                base, compte["id"], nouveau, utilisateur_id=compte["id"]
            )
            st.success("Code enregistré.")
            st.rerun()


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
                "role_essai", "accueil_pose", "ecran", "sejour_id",
                "accueil_admin"):
        st.session_state.pop(cle, None)
    st.rerun()
