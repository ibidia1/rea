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

from .. import listes
from ..domaine import vacations as dom_vacations
from ..domaine.dates import format_date_fr
from ..services import administrations as adm_service
from ..services import affectations as affectations_service
from ..services import constantes as constantes_service
from ..services import prelevements as prelevements_service
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
        "À prélever": lambda: _prelevements(base, patient, jour, vacation, utilisateur_id),
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
        if notee.get("motif_code"):
            detail += f" — {adm_service.libelle_motif(notee['motif_code'])}"
        if notee.get("motif"):
            detail += f" ({notee['motif']})"
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
    """Pourquoi une prise n'a pas été donnée — dans une liste, pas en texte
    libre.

    Un « non donné » n'est pas qu'une case. Selon le motif, quelqu'un doit
    agir : commander ce qui manque, poser la sonde absente, revoir une
    contre-indication. « Rupture » tapé à la main ne se compte pas et ne
    remonte à personne ; un motif choisi dans la liste arrive chez le
    surveillant et sur le prescrit du médecin le jour même (demande du
    service, 10 septembre).

    Le texte libre reste, **à côté** et non à la place : il précise quelle
    voie était obstruée, il ne remplace pas le motif.
    """
    codes = listes.codes(listes.MOTIFS_NON_ADMINISTRATION)
    with st.expander(f"Noter un non-donné de {heure:02d} h"):
        produits = {ligne["produit"]: ligne for ligne in lignes_heure}
        choix = st.selectbox(
            "Quel traitement ?", list(produits), index=None,
            placeholder="Choisir", key=f"nd_produit_{heure}_{patient['sejour_id']}",
        )
        motif_code = st.selectbox(
            "Pourquoi ?", codes, index=None, placeholder="Choisir un motif",
            format_func=lambda c: listes.libelle(
                listes.MOTIFS_NON_ADMINISTRATION, c),
            key=f"nd_motif_{heure}_{patient['sejour_id']}",
        )
        if motif_code:
            action = adm_service.action_du_motif(motif_code)
            if action:
                st.caption(
                    f"Ce motif remonte au surveillant et au médecin : "
                    f"{adm_service.ACTIONS[action].lower()}."
                )
        precision = st.text_input(
            "Précision (facultatif)",
            key=f"nd_precision_{heure}_{patient['sejour_id']}",
            placeholder="ex. voie jugulaire obstruée depuis 14 h",
        )
        if st.button("Enregistrer le non-donné", type="primary",
                     use_container_width=True,
                     disabled=not (choix and motif_code),
                     key=f"nd_ok_{heure}_{patient['sejour_id']}"):
            adm_service.noter(
                base, sejour_id=patient["sejour_id"],
                ligne_id=produits[choix]["id"], date_jour=jour,
                heure_prevue=heure, statut=adm_service.NON_DONNE,
                motif_code=motif_code, motif=precision,
                utilisateur_id=utilisateur_id,
            )
            st.rerun()


# --------------------------------------------------------------------------
# Ce que je prélève
# --------------------------------------------------------------------------

def _prelevements(base, patient, jour, vacation, utilisateur_id) -> None:
    """Les bilans et les examens de ce poste-là, dans l'ordre des heures.

    L'équipe du matin prépare les tubes du matin. Lui montrer les examens des
    vingt-quatre heures reviendrait à lui demander de retrouver les siens dans
    une liste dont les deux tiers ne la concernent pas — le même raisonnement
    que pour les prises de traitement.

    **Les radios sont dedans**, avec l'ECG et l'échographie : ils sont demandés
    dans la même liste et portent la même heure, et une radio de 8 h oubliée
    coûte la même visite qu'une NFS oubliée. Rien ne justifierait de les
    ranger ailleurs sous prétexte qu'il n'y a pas de tube à remplir.
    """
    demandes = prelevements_service.de_la_vacation(
        base, patient["sejour_id"], jour, vacation)
    notes = prelevements_service.du_jour(base, patient["sejour_id"], jour)

    restants = sum(
        1 for d in demandes if (d["examen_code"], d["heure"]) not in notes)
    st.caption(
        f"{len(demandes)} examen(s) sur ce poste · "
        + ("tout est noté" if not restants else f"{restants} pas encore noté(s)")
    )
    if not demandes:
        st.info(
            "Rien à prélever sur cette vacation. Les examens se demandent "
            "dans l'écran Prescrit du médecin, avec leur heure."
        )
        return

    par_heure: dict[int, list] = {}
    for demande in demandes:
        par_heure.setdefault(demande["heure"], []).append(demande)

    for heure, examens in par_heure.items():
        st.markdown(
            f"<div style='margin:.7rem 0 .1rem;font-weight:700;color:{theme.BLEU}'>"
            f"{heure:02d} h</div>",
            unsafe_allow_html=True,
        )
        for examen in examens:
            _bouton_de_prelevement(base, patient, jour, examen,
                                   notes.get((examen["examen_code"], heure)),
                                   utilisateur_id)
        _volet_non_preleve(base, patient, jour, heure, examens, utilisateur_id)


def _bouton_de_prelevement(base, patient, jour, examen, note, utilisateur_id) -> None:
    """Un examen, un bouton pleine largeur — comme une prise.

    L'état est écrit dans le libellé et pas seulement porté par la couleur :
    « Prélevé — NFS » se lit en plein soleil et par quelqu'un qui distingue
    mal le rouge du gris.
    """
    statut = (note or {}).get("statut")
    prefixe = {
        prelevements_service.FAIT: "Prélevé — ",
        prelevements_service.NON_FAIT: "Non prélevé — ",
    }.get(statut, "")
    cle = f"prel_{examen['examen_code']}_{examen['heure']}_{patient['sejour_id']}"
    if st.button(
        prefixe + examen["libelle"], key=cle,
        type="primary" if statut == prelevements_service.FAIT else "secondary",
        use_container_width=True,
    ):
        # Un seul geste, deux sens : ce qui n'est pas noté devient prélevé, ce
        # qui est noté redevient « pas encore ».
        if statut is None:
            prelevements_service.noter(
                base, sejour_id=patient["sejour_id"], date_jour=jour,
                examen_code=examen["examen_code"], heure_prevue=examen["heure"],
                statut=prelevements_service.FAIT, utilisateur_id=utilisateur_id,
            )
        else:
            prelevements_service.effacer(
                base, sejour_id=patient["sejour_id"], date_jour=jour,
                examen_code=examen["examen_code"], heure_prevue=examen["heure"],
                utilisateur_id=utilisateur_id,
            )
        st.rerun()

    if note:
        detail = prelevements_service.STATUTS[note["statut"]]
        if note.get("motif_code"):
            detail += f" — {prelevements_service.libelle_motif(note['motif_code'])}"
        if note.get("motif"):
            detail += f" ({note['motif']})"
        if note.get("soignant"):
            detail += f" · {note['soignant']}"
        if note.get("date_heure_reelle"):
            detail += f" · {note['date_heure_reelle'][11:16]}"
        st.markdown(
            f"<div style='font-size:.75rem;color:#94a3b8;margin:-.3rem 0 .35rem .2rem'>"
            f"{detail}</div>",
            unsafe_allow_html=True,
        )


def _volet_non_preleve(base, patient, jour, heure, examens, utilisateur_id) -> None:
    """Pourquoi un examen n'a pas été prélevé — dans une liste, pas en texte
    libre.

    Un bilan ne se rate pas pour les mêmes raisons qu'un médicament : il ne
    manque pas en pharmacie, il se rate parce que le patient était au bloc ou
    parce qu'il n'y avait pas de voie. D'où une liste de motifs à part
    (`referentiels/motifs_non_prelevement.json`).
    """
    codes = listes.codes(listes.MOTIFS_NON_PRELEVEMENT)
    with st.expander(f"Noter un non-prélevé de {heure:02d} h"):
        par_libelle = {e["libelle"]: e for e in examens}
        choix = st.selectbox(
            "Quel examen ?", list(par_libelle), index=None, placeholder="Choisir",
            key=f"np_ex_{heure}_{patient['sejour_id']}",
        )
        motif_code = st.selectbox(
            "Pourquoi ?", codes, index=None, placeholder="Choisir un motif",
            format_func=lambda c: listes.libelle(listes.MOTIFS_NON_PRELEVEMENT, c),
            key=f"np_motif_{heure}_{patient['sejour_id']}",
        )
        if motif_code:
            action = prelevements_service.action_du_motif(motif_code)
            if action:
                st.caption(
                    "Ce motif remonte au médecin : "
                    f"{prelevements_service.ACTIONS[action]}."
                )
        precision = st.text_input(
            "Précision (facultatif)",
            key=f"np_prec_{heure}_{patient['sejour_id']}",
            placeholder="ex. patient au scanner de 7 h 30 à 9 h",
        )
        if st.button("Enregistrer le non-prélevé", type="primary",
                     use_container_width=True,
                     disabled=not (choix and motif_code),
                     key=f"np_ok_{heure}_{patient['sejour_id']}"):
            prelevements_service.noter(
                base, sejour_id=patient["sejour_id"], date_jour=jour,
                examen_code=par_libelle[choix]["examen_code"],
                heure_prevue=heure, statut=prelevements_service.NON_FAIT,
                motif_code=motif_code, motif=precision,
                utilisateur_id=utilisateur_id,
            )
            st.rerun()


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
    jetes = constantes_service.sacs_jetes_du_jour(base, patient["sejour_id"], jour)

    with st.form(f"constantes_{patient['sejour_id']}_{heure}"):
        valeurs = {}
        _rangees(constantes_service.VITALES, patient, heure, saisies, valeurs)
        sacs = _recueils(patient, heure, saisies, valeurs, jetes)
        if st.form_submit_button(f"Enregistrer le relevé de {heure:02d} h",
                                 type="primary", use_container_width=True):
            constantes_service.enregistrer(
                base, patient["sejour_id"], jour, heure, valeurs,
                sacs_jetes=sacs, utilisateur_id=utilisateur_id,
            )
            st.success(f"Relevé de {heure:02d} h enregistré.")
            st.rerun()

    _grille_du_jour(base, patient, jour, grille, heures, jetes)


def _recueils(patient, heure, saisies, valeurs, jetes) -> set[str]:
    """Le niveau lu sur le sac, et le geste « je viens de le jeter ».

    L'infirmier n'a **rien à soustraire**. Il écrit ce qu'il lit sur la
    graduation — 120, puis 210, puis 300 — et le logiciel en déduit ce qui est
    sorti. Lui demander le calcul au lit du malade, de nuit, avec des gants,
    ce serait lui demander de se tromper une fois par garde.

    La case à cocher n'est pas un détail : sans elle, un sac changé fait
    retomber le niveau de 900 à 40, et la journée perdrait tout ce que le sac
    contenait. Cochée, elle dit « ce niveau-là est le dernier de ce sac » — et
    le relevé suivant repart de zéro.
    """
    st.markdown(
        f"<div style='margin:.9rem 0 .2rem;font-weight:700;"
        f"color:{theme.BLEU}'>Recueils — niveau lu sur le sac</div>",
        unsafe_allow_html=True,
    )
    sacs: set[str] = set()
    for cle, libelle, unite in constantes_service.SORTIES:
        valeurs[cle] = _lire(st.text_input(
            f"{libelle} — niveau du sac ({unite})",
            value="" if saisies.get(cle) is None else _nombre(saisies[cle]),
            key=f"cst_{patient['sejour_id']}_{heure}_{cle}",
            placeholder="ce qui est écrit sur la graduation",
        ))
        if st.checkbox(
            f"J'ai jeté le sac après ce relevé ({libelle.lower()})",
            value=(heure, cle) in jetes,
            key=f"jete_{patient['sejour_id']}_{heure}_{cle}",
        ):
            sacs.add(cle)
    st.caption(
        "Écrire le niveau, pas ce qui est sorti : le logiciel fait la "
        "soustraction. En cochant « j'ai jeté », le prochain relevé repart "
        "de zéro et rien n'est perdu du compte."
    )
    return sacs


def _rangees(champs_constantes, patient, heure, saisies, valeurs) -> None:
    """Deux colonnes, remplies **ligne par ligne** et non colonne par colonne.

    Sous 640 px, Streamlit empile les colonnes : un remplissage vertical y
    devient « FC, PA diast., FR, Glasgow, Dextro, PA syst. » — les deux
    pressions séparées par quatre champs, et l'ordre de la feuille perdu.
    Deux par rangée gardent le même ordre dans les deux dispositions.
    """
    champs_constantes = list(champs_constantes)
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


def _grille_du_jour(base, patient, jour, grille: dict, heures, jetes) -> None:
    """Le relevé du poste en tableau — et, pour les recueils, **deux lignes**.

    Celle des niveaux, telle qu'elle a été écrite, pour se relire. Et celle
    des volumes que ces niveaux impliquent, calculée : c'est elle qui compte,
    et l'infirmier doit pouvoir la vérifier d'un coup d'œil avant la relève.
    Une seule ligne de niveaux laisserait croire que 900 à 13 h est une
    diurèse de 900 pour cette heure-là.

    Les sacs jetés portent un ↺ : un niveau qui retombe à 40 après 900 doit
    s'expliquer de lui-même, sinon c'est le relevé qu'on soupçonne.
    """
    if not grille:
        return
    entetes = "".join(f"<th style='padding:.2rem .35rem'>{h:02d}</th>" for h in heures)
    entetes += "<th style='padding:.2rem .5rem;border-left:1px solid #e2e8f0'>Total</th>"
    lignes = ""
    for cle, libelle, _unite in constantes_service.VITALES:
        valeurs = [grille.get(h, {}).get(cle) for h in heures]
        if not any(v is not None for v in valeurs):
            continue
        lignes += _rangee(libelle, [_nombre(v) for v in valeurs], "")

    for cle, libelle, unite in constantes_service.SORTIES:
        niveaux = [grille.get(h, {}).get(cle) for h in heures]
        if not any(v is not None for v in niveaux):
            continue
        marques = [
            _nombre(v) + (" ↺" if (h, cle) in jetes else "")
            for h, v in zip(heures, niveaux)
        ]
        lignes += _rangee(f"{libelle} — niveau", marques, "",
                          couleur="#94a3b8")
        sorties = constantes_service.sorties_du_jour(
            base, patient["sejour_id"], jour, cle
        )
        volumes = [sorties[h].volume_ml if h in sorties else None for h in heures]
        total = sum(v for v in volumes if v is not None)
        lignes += _rangee(
            f"{libelle} sortie ({unite})",
            [_nombre(v) for v in volumes],
            f"<b>{_nombre(total)}</b>",
        )
    if not lignes:
        return
    theme.bloc_html(
        "Relevé de la vacation",
        "<div style='overflow-x:auto'><table style='font-size:.8rem'>"
        f"<tr style='color:#64748b'><th></th>{entetes}</tr>{lignes}</table></div>",
        theme.BLEU,
    )


def _rangee(libelle: str, cases: list[str], total: str, couleur: str = "") -> str:
    style = f";color:{couleur}" if couleur else ""
    corps = "".join(
        f"<td style='text-align:center;padding:.2rem .35rem{style}'>{c}</td>"
        for c in cases
    )
    return (
        f"<tr><td style='padding:.2rem .4rem;white-space:nowrap{style}'>"
        f"{libelle}</td>{corps}"
        f"<td style='text-align:center;padding:.2rem .5rem;"
        f"border-left:1px solid #e2e8f0'>{total}</td></tr>"
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
