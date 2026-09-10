"""L'écran de l'infirmier : mon poste, mes malades, ce que je donne
(SPEC §5.8).

Trois différences avec le reste du logiciel, et elles décident de tout :

* **on ne prescrit pas ici.** Aucun bouton ne modifie le prescrit. C'est le
  droit `dossier_ecrire` qui manque au rôle, mais c'est aussi une question de
  dessin : un bouton d'arrêt de traitement à portée de manche est un
  traitement arrêté par erreur.
* **on ne voit pas la journée, on voit son poste.** L'équipe du matin prépare
  ce qu'elle va donner entre 7 h et 13 h. Lui montrer les vingt-quatre heures
  reviendrait à lui demander de retrouver ses prises dans une liste dont les
  trois quarts ne le concernent pas.
* **on choisit son malade en arrivant.** C'est ce choix qui fait exister
  l'affectation que le surveillant lira pour savoir qui appeler.

Et une contrainte de forme qui décide du reste : **cet écran s'ouvre sur un
téléphone**, au lit du malade, parfois avec des gants. Trois conséquences.

Une prise tient sur **une seule ligne** — un bouton pleine largeur qu'on
touche. La version en trois colonnes (case, produit, bouton) se dépliait en
trois lignes séparées sous 640 px : une pancarte de trente prises devenait
quatre-vingt-dix lignes à faire défiler au pouce, avec des cases de seize
pixels qu'on rate une fois sur trois.

Le cas rare — non donné, refusé — passe par un volet replié sous chaque
heure, au lieu d'occuper une place fixe sur toutes les lignes.

Enfin **traitements et surveillance ne s'affichent pas ensemble** : côte à
côte sur un grand écran, ils s'empilent sur un téléphone, et il faudrait
faire défiler trente traitements pour atteindre la case de la température.
Un sélecteur en tête, et une seule chose à l'écran à la fois.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from ..domaine import vacations as dom_vacations
from ..domaine.dates import format_date_fr
from ..services import administrations as adm_service
from ..services import affectations as affectations_service
from ..services import constantes as constantes_service
from ..services import prescriptions as prescriptions_service
from ..services import supervision as supervision_service
from . import theme

def ecran(base, utilisateur_id: str | None = None) -> None:
    vacation, jour = affectations_service.poste_courant()
    st.title("Mon poste")
    st.caption(
        f"{dom_vacations.libelle(vacation)} · {dom_vacations.horaire(vacation)} · "
        f"prise de poste le {format_date_fr(jour)}"
    )

    mes_patients = affectations_service.du_soignant(base, utilisateur_id, jour, vacation)
    _choix_des_malades(base, utilisateur_id, jour, vacation, mes_patients)
    if not mes_patients:
        return

    st.divider()
    noms = {f"Lit {p['lit_admission']} — {p['nom_affichage']}": p for p in mes_patients}
    choix = st.segmented_control(
        "Patient", list(noms), default=list(noms)[0], key="infirmier_patient",
        label_visibility="collapsed",
    ) or list(noms)[0]
    patient = noms[choix]

    vues = {
        "À donner": lambda: _traitements(base, patient, jour, vacation, utilisateur_id),
        "Surveillance": lambda: _constantes(base, patient, jour, vacation, utilisateur_id),
    }
    cle_vue = f"vue_poste_{patient['sejour_id']}"
    vue = st.segmented_control(
        "Vue", list(vues), default=st.session_state.get(cle_vue, "À donner"),
        key=f"segments_{cle_vue}", label_visibility="collapsed",
    ) or st.session_state.get(cle_vue, "À donner")
    st.session_state[cle_vue] = vue
    vues[vue]()


# --------------------------------------------------------------------------
# Choisir ses malades
# --------------------------------------------------------------------------

def _choix_des_malades(base, utilisateur_id, jour, vacation, mes_patients) -> None:
    """Le choix se refait à chaque prise de poste, et c'est voulu : les
    malades changent de main trois fois par jour."""
    deja = {p["sejour_id"] for p in mes_patients}
    with st.expander(
        f"Mes malades de cette vacation ({len(mes_patients)})",
        expanded=not mes_patients,
    ):
        st.caption(
            "À choisir en prenant le poste. C'est ce choix qui permet au "
            "surveillant de savoir qui appeler pour ce lit."
        )
        for sejour in supervision_service.sejours_ouverts(base):
            c1, c2 = st.columns([5, 1])
            c1.markdown(
                f"**Lit {sejour['lit_admission']}** — {sejour['nom_affichage']} "
                f"<span style='color:#94a3b8'>({sejour['matricule']})</span>",
                unsafe_allow_html=True,
            )
            if sejour["id"] in deja:
                if c2.button("Retirer", key=f"retirer_{sejour['id']}",
                             use_container_width=True):
                    ligne = next(p for p in mes_patients if p["sejour_id"] == sejour["id"])
                    affectations_service.retirer(base, ligne["id"],
                                                 utilisateur_id=utilisateur_id)
                    st.rerun()
            elif c2.button("Prendre", key=f"prendre_{sejour['id']}",
                           use_container_width=True, type="primary"):
                affectations_service.affecter(
                    base, sejour_id=sejour["id"], soignant_id=utilisateur_id,
                    date_jour=jour, vacation=vacation, utilisateur_id=utilisateur_id,
                )
                st.rerun()
    if not mes_patients:
        st.info("Choisir au moins un malade pour commencer la vacation.")


# --------------------------------------------------------------------------
# Ce que je donne
# --------------------------------------------------------------------------

def _traitements(base, patient, jour, vacation, utilisateur_id) -> None:
    lignes = prescriptions_service.lignes_actives_le(base, patient["sejour_id"], jour)
    prises = dom_vacations.prises_de_la_vacation(lignes, vacation)
    notees = adm_service.du_jour(base, patient["sejour_id"], jour)

    restantes = sum(
        1 for heure, ligne in prises if (ligne["id"], heure) not in notees
    )
    st.caption(
        f"{len(prises)} prise(s) sur ce poste · "
        + ("tout est noté" if not restantes else f"{restantes} pas encore notée(s)")
    )

    if not prises:
        st.info("Rien à donner sur cette vacation.")

    par_heure: dict[int, list] = {}
    for heure, ligne in prises:
        par_heure.setdefault(heure, []).append(ligne)

    for heure, lignes_heure in par_heure.items():
        st.markdown(
            f"<div style='margin:.7rem 0 .1rem;font-weight:700;color:{theme.BLEU}'>"
            f"{heure:02d} h</div>",
            unsafe_allow_html=True,
        )
        for ligne in lignes_heure:
            _bouton_de_prise(base, patient, jour, heure, ligne,
                             notees.get((ligne["id"], heure)), utilisateur_id)
        _volet_exceptions(base, patient, jour, heure, lignes_heure, notees,
                          utilisateur_id)

    conditionnels = dom_vacations.prises_conditionnelles(lignes)
    if conditionnels:
        with st.expander(f"Si besoin ({len(conditionnels)})"):
            for ligne in conditionnels:
                st.markdown(
                    f"- **{ligne['produit']}** — "
                    f"{ligne.get('condition_texte') or 'si besoin'}"
                )


def _bouton_de_prise(base, patient, jour, heure, ligne, notee, utilisateur_id) -> None:
    """Une prise, un bouton pleine largeur, un doigt.

    L'état est **écrit dans le libellé**, pas seulement porté par la couleur :
    « Donné — Tienam 1 g » se lit d'un coup d'œil, en plein soleil, et par
    quelqu'un qui distingue mal le rouge du gris.
    """
    from ..domaine import prescription as dom

    # Les prises sont groupées par heure juste au-dessus : répéter
    # « (8h-20h) » derrière chaque produit allongerait la ligne pour rien.
    texte = " ".join(
        m for m in (dom.libelle_court(ligne), dom.dose_affichee(ligne)) if m
    )
    statut = (notee or {}).get("statut")
    prefixe = {
        adm_service.DONNE: "Donné — ",
        adm_service.NON_DONNE: "Non donné — ",
        adm_service.REFUSE: "Refusé — ",
    }.get(statut, "")

    if st.button(
        prefixe + texte,
        key=f"prise_{ligne['id']}_{heure}",
        type="primary" if statut == adm_service.DONNE else "secondary",
        use_container_width=True,
    ):
        # Un seul geste, deux sens : ce qui n'est pas noté devient donné, ce
        # qui est noté redevient « pas encore ». Corriger doit coûter le même
        # nombre de gestes que noter, sinon on corrige sur le papier.
        if statut is None:
            adm_service.noter(
                base, sejour_id=patient["sejour_id"], ligne_id=ligne["id"],
                date_jour=jour, heure_prevue=heure, statut=adm_service.DONNE,
                utilisateur_id=utilisateur_id,
            )
        else:
            adm_service.effacer(base, ligne_id=ligne["id"], date_jour=jour,
                                heure_prevue=heure, utilisateur_id=utilisateur_id)
        st.rerun()

    if notee:
        detail = adm_service.STATUTS[notee["statut"]]
        if notee.get("motif"):
            detail += f" — {notee['motif']}"
        if notee.get("soignant"):
            detail += f" · {notee['soignant']}"
        if notee.get("date_heure_reelle"):
            detail += f" · {notee['date_heure_reelle'][11:16]}"
        st.markdown(
            f"<div style='font-size:.75rem;color:#94a3b8;margin:-.3rem 0 .35rem .2rem'>"
            f"{detail}</div>",
            unsafe_allow_html=True,
        )


def _volet_exceptions(base, patient, jour, heure, lignes_heure, notees,
                      utilisateur_id) -> None:
    """Non donné, refusé : le cas rare, replié.

    Lui donner une place fixe sur chaque ligne coûtait un bouton par prise —
    trente boutons pour une situation qui arrive deux fois par garde. Replié,
    il ne coûte rien et reste à un geste.
    """
    with st.expander(f"Noter un non-donné de {heure:02d} h"):
        for ligne in lignes_heure:
            st.markdown(f"**{ligne['produit']}**")
            motif = st.text_input(
                "Pourquoi ?", key=f"motif_{ligne['id']}_{heure}",
                placeholder="ex. patient au bloc", label_visibility="collapsed",
            )
            c1, c2 = st.columns(2)
            for colonne, statut, libelle in (
                (c1, adm_service.NON_DONNE, "Non donné"),
                (c2, adm_service.REFUSE, "Refusé"),
            ):
                if colonne.button(libelle, key=f"{statut}_{ligne['id']}_{heure}",
                                  use_container_width=True):
                    adm_service.noter(
                        base, sejour_id=patient["sejour_id"], ligne_id=ligne["id"],
                        date_jour=jour, heure_prevue=heure, statut=statut,
                        motif=motif, utilisateur_id=utilisateur_id,
                    )
                    st.rerun()
            st.divider()


# --------------------------------------------------------------------------
# La surveillance horaire
# --------------------------------------------------------------------------

def _constantes(base, patient, jour, vacation, utilisateur_id) -> None:
    st.markdown("#### Surveillance horaire")
    st.caption(
        "Ce que la feuille porte au verso, heure par heure. L'heure en cours "
        "est proposée d'abord ; les autres heures du poste restent "
        "accessibles pour rattraper un relevé."
    )
    heures = dom_vacations.heures(vacation)
    maintenant = datetime.now().hour
    defaut = maintenant if maintenant in heures else heures[0]
    heure = st.selectbox(
        "Heure du relevé", heures, index=heures.index(defaut),
        format_func=lambda h: f"{h:02d} h",
        key=f"heure_{patient['sejour_id']}",
    )

    grille = constantes_service.du_jour(base, patient["sejour_id"], jour)
    saisies = grille.get(heure, {})

    with st.form(f"constantes_{patient['sejour_id']}_{heure}"):
        valeurs = {}
        # Deux colonnes, remplies **ligne par ligne** et non colonne par
        # colonne. Sous 640 px, Streamlit empile les colonnes : un remplissage
        # vertical y devient « FC, PA diast., FR, Glasgow, Dextro, PA syst. »
        # — les deux pressions séparées par quatre champs, et l'ordre de la
        # feuille perdu. Deux par rangée gardent le même ordre dans les deux
        # dispositions.
        champs_constantes = list(constantes_service.CLES)
        for i in range(0, len(champs_constantes), 2):
            for colonne, (cle, libelle, unite) in zip(
                st.columns(2), champs_constantes[i:i + 2]
            ):
                with colonne:
                    brut = st.text_input(
                        f"{libelle} ({unite})" if unite else libelle,
                        value="" if saisies.get(cle) is None else _nombre(saisies[cle]),
                        key=f"cst_{patient['sejour_id']}_{heure}_{cle}",
                    )
                valeurs[cle] = _lire(brut)
        if st.form_submit_button(f"Enregistrer le relevé de {heure:02d} h",
                                 type="primary", use_container_width=True):
            constantes_service.enregistrer(
                base, patient["sejour_id"], jour, heure, valeurs,
                utilisateur_id=utilisateur_id,
            )
            st.success(f"Relevé de {heure:02d} h enregistré.")
            st.rerun()

    _grille_du_jour(grille, heures)


def _grille_du_jour(grille: dict, heures) -> None:
    """Le relevé du poste en tableau : c'est la courbe qu'on lit d'un coup
    d'œil pour voir si quelque chose se dégrade."""
    if not grille:
        return
    entetes = "".join(f"<th style='padding:.2rem .35rem'>{h:02d}</th>" for h in heures)
    lignes = ""
    for cle, libelle, _unite in constantes_service.CLES:
        if not any(cle in grille.get(h, {}) for h in heures):
            continue
        cases = "".join(
            f"<td style='text-align:center;padding:.2rem .35rem'>"
            f"{_nombre(grille.get(h, {}).get(cle))}</td>"
            for h in heures
        )
        lignes += (
            f"<tr><td style='padding:.2rem .4rem;white-space:nowrap'>"
            f"{libelle}</td>{cases}</tr>"
        )
    if not lignes:
        return
    theme.bloc_html(
        "Relevé de la vacation",
        "<div style='overflow-x:auto'><table style='font-size:.8rem'>"
        f"<tr style='color:#64748b'><th></th>{entetes}</tr>{lignes}</table></div>",
        theme.BLEU,
    )


def _nombre(valeur) -> str:
    if valeur is None:
        return ""
    return str(int(valeur)) if float(valeur).is_integer() else f"{valeur:.1f}"


def _lire(texte: str) -> float | None:
    """Une case vide efface la mesure ; un texte illisible ne l'écrase pas.

    Rendre 0 sur une saisie ratée écrirait une fréquence cardiaque à zéro —
    c'est-à-dire un arrêt cardiaque dans le dossier.
    """
    texte = (texte or "").strip().replace(",", ".")
    if not texte:
        return None
    try:
        return float(texte)
    except ValueError:
        return None
