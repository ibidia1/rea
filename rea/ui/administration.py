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

import streamlit as st

import re
import unicodedata

from .. import aides, config, listes, protocoles, referentiels
from ..db import Base, inspecter_fichier_base
from ..domaine import regles as regles_dom
from ..domaine.dates import format_date_fr
from ..services import pancarte as pancarte_service
from . import comptes as comptes_ui
from . import theme
from . import utilisateur as utilisateur_ui


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

    # Chaque onglet ne s'affiche qu'à qui il sert : un senior n'a pas à voir
    # la gestion des comptes, un administrateur qui n'est pas médecin n'a pas
    # à signer des protocoles. Ce n'est pas une serrure (voir
    # `domaine/droits.py`), c'est un écran qui ne propose pas l'inutile.
    vues: dict[str, object] = {}
    if utilisateur_ui.peut("comptes"):
        vues["Comptes"] = lambda: comptes_ui.ecran(base, utilisateur_id)
    vues["Sauvegardes"] = lambda: _sauvegardes(base)
    vues["Journal"] = lambda: _journal(base)
    vues["Fiches imprimées"] = lambda: _fiches_imprimees(base)
    vues["Référentiels"] = _referentiels
    if utilisateur_ui.peut("protocoles"):
        vues["Protocoles"] = _protocoles
        vues["Règles d'aide"] = _regles

    noms = list(vues)
    choix = st.segmented_control(
        "Section", noms, default=st.session_state.get("vue_admin", noms[0]),
        key="segments_admin", label_visibility="collapsed",
    ) or st.session_state.get("vue_admin", noms[0])
    st.session_state["vue_admin"] = choix
    vues[choix]()


# --------------------------------------------------------------------------
# Sauvegardes et restauration
# --------------------------------------------------------------------------

def _sauvegardes(base: Base) -> None:
    """Quatre gestes, nommés par ce qu'ils font, chacun expliqué sous son
    bouton.

    L'écran présentait une liste de quinze fichiers `rea-20260909-143012.db`
    et une liste déroulante de toutes les sauvegardes existantes. Personne ne
    choisit une base sur un horodatage à la seconde : ce qu'on veut, c'est
    « emporter le service sur une clé » ou « remettre celle d'hier soir ». La
    liste complète descend donc sous un dépliant, et les quatre gestes
    montent : exporter, importer, sauvegarder, restaurer la dernière.
    """
    _exporter_importer(base)
    st.divider()
    _sauvegarder_restaurer(base)


def _exporter_importer(base: Base) -> None:
    gauche, droite = st.columns(2, gap="large")

    with gauche:
        st.markdown("##### Emporter la base")
        if st.button("Préparer le fichier à exporter", use_container_width=True,
                     type="primary"):
            # Jamais le fichier vivant : en mode WAL, les dernières écritures
            # sont encore dans un fichier annexe, et la copie brute serait en
            # retard sur ce qu'on voit à l'écran.
            chemin = base.sauvegarder(motif="export")
            st.session_state["export_base"] = (chemin.name, chemin.read_bytes())
        st.caption(
            "Écrit **une copie complète** du service — patients, prescriptions, "
            "bilans, tout — dans un seul fichier `.db`, à télécharger ensuite. "
            "C'est ce fichier qu'on met sur une clé USB, qu'on garde hors du "
            "poste, ou qu'on ouvre sur un autre ordinateur."
        )
        if "export_base" in st.session_state:
            nom, donnees = st.session_state["export_base"]
            st.download_button(
                f"Télécharger {nom}  ({_taille(len(donnees))})",
                data=donnees, file_name=nom, mime="application/x-sqlite3",
                use_container_width=True,
            )

    with droite:
        st.markdown("##### Installer une base venue d'ailleurs")
        # Le libellé interne du dépôt de fichier reste en anglais — il vient
        # de Streamlit. D'où la consigne en français juste au-dessus.
        fichier = st.file_uploader(
            "Déposer ici le fichier `.db` à installer", type=["db"],
            key="import_base",
        )
        st.caption(
            "Remplace la base actuelle par le fichier choisi — le contenu du "
            "poste est **entièrement** remplacé. L'état actuel est sauvegardé "
            "juste avant, donc l'opération reste réversible. Sert à reprendre "
            "un export fait sur un autre poste, ou à remonter une base "
            "conservée sur clé."
        )
        if fichier is not None:
            _importer(base, fichier)


def _importer(base: Base, fichier) -> None:
    """On regarde le fichier avant de l'installer, et on dit ce qu'il contient.

    Un fichier qui n'est pas une base REA — une photo renommée, une copie
    interrompue sur clé USB — laisserait le logiciel sans dossier au moment de
    le rouvrir. Et même valide, il faut que l'utilisateur voie *combien de
    patients* il s'apprête à installer : c'est ce chiffre qui l'arrête quand
    il s'est trompé de fichier.
    """
    depot = config.DOSSIER_SAUVEGARDES / f"importe-{fichier.name}"
    depot.parent.mkdir(parents=True, exist_ok=True)
    depot.write_bytes(fichier.getbuffer())

    etat = inspecter_fichier_base(depot)
    if not etat["lisible"]:
        st.error(f"Fichier refusé : {etat['erreur']}")
        depot.unlink(missing_ok=True)
        return

    actuelle = inspecter_fichier_base(base.chemin)
    st.info(
        f"Ce fichier contient **{etat['patients']} patients** et "
        f"{etat['sejours']} séjours (modifié le "
        f"{etat['date'].replace('T', ' à ')}).\n\n"
        f"La base actuelle en contient {actuelle['patients']} — "
        "elle sera remplacée."
    )
    confirme = st.checkbox(
        "Je confirme vouloir remplacer la base actuelle par ce fichier",
        key="confirme_import",
    )
    if st.button("Installer cette base", disabled=not confirme, type="primary"):
        filet = base.restaurer(depot)
        st.success(
            f"Base installée. L'état précédent reste disponible dans "
            f"{filet.name} — le bouton Restaurer ci-dessous permet d'y revenir."
        )
        st.session_state.pop("sejour_id", None)


def _sauvegarder_restaurer(base: Base) -> None:
    disponibles = base.sauvegardes_disponibles()
    gauche, droite = st.columns(2, gap="large")

    with gauche:
        st.markdown("##### Sauvegarder sur ce poste")
        if st.button("Sauvegarder maintenant", use_container_width=True):
            chemin = base.sauvegarder(motif="manuelle")
            st.success(f"Sauvegarde écrite : {chemin.name}")
        st.caption(
            f"Le logiciel sauvegarde déjà tout seul toutes les "
            f"{config.INTERVALLE_SAUVEGARDE_MINUTES} minutes, à l'ouverture et "
            f"à la fermeture. Ce bouton sert avant une manipulation qu'on "
            f"préfère pouvoir annuler. Les {config.SAUVEGARDES_CONSERVEES} "
            f"dernières sont conservées, sur ce poste uniquement — "
            f"une sauvegarde qui reste sur le disque du poste ne protège pas "
            f"d'un disque en panne : pour cela, il faut l'export ci-dessus."
        )

    with droite:
        st.markdown("##### Revenir en arrière")
        if not disponibles:
            st.info("Aucune sauvegarde pour l'instant.")
            return
        derniere = disponibles[0]
        st.caption(
            f"Dernière sauvegarde : **{derniere['date'].replace('T', ' à ')}** "
            f"({_taille(derniere['taille'])}). Restaurer remplace toute la base "
            "actuelle ; l'état d'avant est sauvegardé juste avant, donc on peut "
            "encore faire marche arrière."
        )
        if st.checkbox("Je confirme vouloir revenir à cette sauvegarde",
                       key="confirme_derniere"):
            if st.button("Restaurer la dernière sauvegarde", type="primary",
                         use_container_width=True):
                _restaurer(base, derniere)

    with st.expander(f"Choisir une sauvegarde plus ancienne "
                     f"({len(disponibles)} disponibles)"):
        noms = [f"{s['date'].replace('T', ' ')} — {_taille(s['taille'])}"
                for s in disponibles]
        choix = st.selectbox("Sauvegarde à restaurer", noms, index=None,
                             placeholder="Choisir une sauvegarde")
        confirme = st.checkbox("Je confirme vouloir remplacer la base actuelle",
                               key="confirme_ancienne")
        if st.button("Restaurer", disabled=not (choix and confirme)):
            _restaurer(base, disponibles[noms.index(choix)])


def _restaurer(base: Base, sauvegarde: dict) -> None:
    filet = base.restaurer(sauvegarde["chemin"])
    st.success(
        f"Base restaurée depuis la sauvegarde du "
        f"{sauvegarde['date'].replace('T', ' à ')}. "
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
    tables = base.tables_journalisees()
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

def _fiches_imprimees(base: Base) -> None:
    """Retrouver ce qui a été imprimé dans le service, jour par jour.

    Chaque fiche est un instantané figé : on revoit exactement ce qui est
    sorti sur papier ce jour-là, même si le dossier a changé depuis — la
    seule lecture fidèle pour une relecture médico-légale ou une visite qui
    veut comparer plusieurs jours.
    """
    st.caption(
        "Chaque impression est conservée telle quelle, quel que soit le "
        "patient ou le lit. Choisir un jour pour voir tout ce qui a été "
        "imprimé ce jour-là dans le service."
    )
    dates = pancarte_service.dates_avec_impression(base)
    if not dates:
        st.info("Aucune fiche n'a encore été imprimée.")
        return
    jour = st.selectbox(
        "Jour", dates, format_func=lambda d: format_date_fr(d),
    )
    fiches = pancarte_service.snapshots_par_date(base, jour)
    if not fiches:
        st.caption("Aucune fiche imprimée ce jour-là.")
        return
    for fiche in fiches:
        with st.expander(
            f"Lit {fiche['lit_admission']} — {fiche['nom_affichage']} "
            f"(v{fiche['version']})"
        ):
            st.caption(
                f"Imprimée à {fiche['imprime_le'][11:16]}"
                + (f" par {fiche['imprime_par_nom']}" if fiche.get("imprime_par_nom") else "")
            )
            complete = pancarte_service.snapshot(base, fiche["id"])
            if complete:
                st.download_button(
                    "Télécharger",
                    data=complete["html"],
                    file_name=f"feuille-lit{fiche['lit_admission']}-{jour}-v{fiche['version']}.html",
                    mime="text/html",
                    key=f"dl_admin_{fiche['id']}",
                )


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


def _slug(texte: str) -> str:
    """Un identifiant de fichier sûr : minuscules, chiffres, underscores."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9_]+", "_", sans_accents.lower()).strip("_")


def _valeur_typee(texte: str):
    """Une valeur de condition : nombre si possible, texte sinon — les
    barèmes comparent aussi bien des seuils (100) que des catégories
    ("aucune")."""
    texte = texte.strip()
    if not texte:
        return None
    try:
        return int(texte)
    except ValueError:
        pass
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return texte


_OPERATEURS_EDITEUR = ("<", "<=", ">", ">=", "=", "!=", "renseigne",
                       "non_renseigne", "vrai", "faux")
_SANS_VALEUR = ("renseigne", "non_renseigne", "vrai", "faux")
_NB_LIGNES_CONDITION = 4


def _reinitialiser_editeur_regle() -> None:
    for cle in list(st.session_state):
        if cle.startswith("ed_regle_"):
            del st.session_state[cle]


def _charger_regle_dans_editeur(regle: dict) -> None:
    _reinitialiser_editeur_regle()
    st.session_state["ed_regle_code_cible"] = regle["code"]
    st.session_state["ed_regle_code"] = regle["code"]
    st.session_state["ed_regle_libelle"] = regle.get("libelle", "")
    st.session_state["ed_regle_message"] = regle.get("message", "")
    st.session_state["ed_regle_gravite"] = regle.get("gravite", "attention")
    st.session_state["ed_regle_source"] = regle.get("source", "")
    st.session_state["ed_regle_combinaison"] = (
        "ou (au moins une)" if regle.get("combinaison") == "ou" else "et (toutes)"
    )
    for i, cond in enumerate(regle.get("conditions", [])[:_NB_LIGNES_CONDITION]):
        st.session_state[f"ed_regle_fait_{i}"] = cond.get("fait", "")
        st.session_state[f"ed_regle_op_{i}"] = cond.get("op", "")
        if "valeur" in cond:
            st.session_state[f"ed_regle_valeur_{i}"] = str(cond["valeur"])


def _protocoles() -> None:
    st.caption(
        "Un protocole n'est proposé à l'écran que s'il est **validé et signé** "
        "par le chef de service (SPEC §4.5). Les autres restent des brouillons : "
        "ils sont visibles ici, jamais proposés aux internes."
    )
    st.caption(
        "**Où apparaît un protocole**, selon son déclencheur : à l'admission "
        "pour un motif d'entrée ou une région traumatique ; dans l'écran "
        "Évolution, sous le rappel qui vient de le déclencher, pour une règle "
        "d'aide. Dans tous les cas il est *proposé* — les lignes ne sont "
        "posées qu'après un clic, sans dose, et restent modifiables."
    )
    tous = protocoles.tous_les_protocoles()
    if not tous:
        st.info("Aucun protocole installé.")
        return
    for p in tous:
        etat = (
            f"Validé — signé par {p.signe_par}" if p.valide and p.signe_par
            else "Brouillon — non proposé à l'écran"
        )
        declencheur = p.declencheur or {}
        quand = (
            f"{_LIBELLE_DECLENCHEUR.get(declencheur['type'], declencheur['type'])}"
            f" : {declencheur.get('valeur')}"
            if declencheur.get("type")
            else "Aucun déclencheur — jamais proposé automatiquement"
        )
        theme.bloc(
            p.titre,
            [
                f"Version {p.version} du {p.date_version}",
                etat,
                quand,
                f"{len(p.lignes_prescription)} lignes de prescription, "
                f"{len(p.explorations_proposees)} explorations, "
                f"{len(p.consignes)} consignes",
            ],
            theme.VERT if p.valide else theme.ORANGE,
        )

    _editeur_protocoles()


def _charger_protocole_dans_editeur(code: str | None) -> None:
    for cle in list(st.session_state):
        if cle.startswith("ed_proto_") and cle != "ed_proto_choix":
            del st.session_state[cle]
    if code is None:
        return
    p = protocoles.lire_fichier(code)
    st.session_state["ed_proto_code"] = code
    st.session_state["ed_proto_titre"] = p.get("titre", "")
    declencheur = p.get("declencheur") or {}
    if declencheur.get("type") == "region_traumatique":
        st.session_state["ed_proto_decl_type"] = "region_traumatique"
        st.session_state["ed_proto_decl_valeur_region"] = declencheur.get("valeur")
    elif declencheur.get("type") == "motif":
        st.session_state["ed_proto_decl_type"] = "motif"
        st.session_state["ed_proto_decl_valeur_motif"] = declencheur.get("valeur")
    elif declencheur.get("type") == "regle":
        st.session_state["ed_proto_decl_type"] = "regle"
        st.session_state["ed_proto_decl_valeur_regle"] = declencheur.get("valeur")
    else:
        st.session_state["ed_proto_decl_type"] = "aucun (jamais proposé automatiquement)"
    for i, ligne in enumerate(p.get("lignes_prescription", [])[:6]):
        st.session_state[f"ed_proto_ligne_voie_{i}"] = ligne.get("voie", "")
        st.session_state[f"ed_proto_ligne_produit_{i}"] = ligne.get("produit", "")
        st.session_state[f"ed_proto_ligne_dose_{i}"] = str(ligne.get("dose") or "")
        st.session_state[f"ed_proto_ligne_unite_{i}"] = ligne.get("unite", "")
        st.session_state[f"ed_proto_ligne_rythme_{i}"] = ligne.get("rythme", "")
        st.session_state[f"ed_proto_ligne_vitesse_{i}"] = str(ligne.get("vitesse") or "")
        st.session_state[f"ed_proto_ligne_note_{i}"] = ligne.get("note", "")
    for i, expl in enumerate(p.get("explorations_proposees", [])[:4]):
        st.session_state[f"ed_proto_expl_type_{i}"] = expl.get("type", "")
        st.session_state[f"ed_proto_expl_delai_{i}"] = expl.get("delai", "")
        st.session_state[f"ed_proto_expl_libelle_{i}"] = expl.get("libelle", "")
    st.session_state["ed_proto_consignes"] = "\n".join(p.get("consignes", []))
    st.session_state["ed_proto_valide"] = bool(p.get("valide"))
    st.session_state["ed_proto_signe_par"] = p.get("signe_par") or ""


_LIBELLE_DECLENCHEUR = {
    "region_traumatique": "À l'admission — région traumatique",
    "motif": "À l'admission — motif d'entrée",
    "regle": "Quand une règle d'aide se déclenche (hypokaliémie, fièvre…)",
    "aucun (jamais proposé automatiquement)": "Jamais proposé automatiquement",
}


def _codes_des_regles() -> list[str]:
    """Les codes de règles auxquels un protocole peut s'attacher.

    Ils viennent des fichiers `regles/*.json`, pas d'une liste écrite ici :
    ajouter une règle doit suffire à pouvoir lui accrocher un protocole.
    """
    return sorted({r.code for r in aides.toutes_les_regles()})


def _editeur_protocoles() -> None:
    st.divider()
    st.subheader("Ajouter ou modifier un protocole")
    st.caption(
        "Un protocole reste un brouillon — jamais proposé à l'admission — "
        "tant que « Validé » n'est pas coché et « Signé par » renseigné "
        "(règle de sécurité 1, SPEC §4.5)."
    )

    codes_existants = list(protocoles.codes())
    choix = st.selectbox(
        "Protocole", ["Nouveau protocole…"] + codes_existants, key="ed_proto_choix"
    )
    if choix != st.session_state.get("ed_proto_charge"):
        _charger_protocole_dans_editeur(None if choix == "Nouveau protocole…" else choix)
        st.session_state["ed_proto_charge"] = choix
    code_existant = None if choix == "Nouveau protocole…" else choix

    code = st.text_input(
        "Code (identifiant unique)", key="ed_proto_code", disabled=bool(code_existant)
    )
    titre = st.text_input("Titre affiché", key="ed_proto_titre")

    st.markdown("**Déclencheur** — quand ce protocole doit-il être proposé ?")
    c1, c2 = st.columns(2)
    type_declencheur = c1.selectbox(
        "Type",
        ["region_traumatique", "motif", "regle",
         "aucun (jamais proposé automatiquement)"],
        key="ed_proto_decl_type",
        format_func=_LIBELLE_DECLENCHEUR.get,
    )
    valeur_declencheur = None
    if type_declencheur == "region_traumatique":
        valeur_declencheur = c2.selectbox(
            "Région", listes.codes(listes.REGIONS_TRAUMATIQUES),
            format_func=lambda c: listes.libelle(listes.REGIONS_TRAUMATIQUES, c),
            key="ed_proto_decl_valeur_region",
        )
    elif type_declencheur == "motif":
        tous_motifs = listes.motifs_a_plat()
        codes_motifs = [c for c, _l, _g in tous_motifs]
        valeur_declencheur = c2.selectbox(
            "Motif", codes_motifs, format_func=listes.libelle_motif,
            key="ed_proto_decl_valeur_motif",
        )
    elif type_declencheur == "regle":
        codes_regles = _codes_des_regles()
        if codes_regles:
            valeur_declencheur = c2.selectbox(
                "Règle d'aide", codes_regles, key="ed_proto_decl_valeur_regle",
            )
        else:
            c2.warning("Aucune règle d'aide installée.")
    else:
        c2.caption("Jamais proposé automatiquement — un dossier à part.")

    st.markdown("**Lignes de prescription proposées**")
    st.caption(
        "La posologie écrite ici est reprise telle quelle dans la ligne posée. "
        "Elle vient de vous, pas d'un calcul du logiciel — c'est ce qui la "
        "distingue de ce qu'interdit le §3.1. Laisser vide ce que le "
        "prescripteur doit décider au lit du malade : un champ vide reste "
        "vide, il n'est jamais deviné."
    )
    lignes_prescription = []
    for i in range(6):
        cc1, cc2, cc3, cc4, cc5, cc6, cc7 = st.columns([1, 2, 1, 1, 1, 1, 2])
        voie = cc1.selectbox(
            "Voie", [""] + list(listes.ORDRE_VOIES), key=f"ed_proto_ligne_voie_{i}",
            format_func=lambda c: "—" if not c else listes.VOIES[c]["titre"],
            label_visibility="collapsed" if i else "visible",
        )
        produit = cc2.text_input(
            "Produit", key=f"ed_proto_ligne_produit_{i}",
            label_visibility="collapsed" if i else "visible",
        )
        dose = cc3.text_input(
            "Dose", key=f"ed_proto_ligne_dose_{i}", placeholder="1",
            label_visibility="collapsed" if i else "visible",
        )
        unite = cc4.selectbox(
            "Unité", [""] + list(listes.codes(listes.UNITES)),
            key=f"ed_proto_ligne_unite_{i}",
            format_func=lambda c: "—" if not c else listes.libelle(listes.UNITES, c),
            label_visibility="collapsed" if i else "visible",
        )
        rythme = cc5.selectbox(
            "Rythme", [""] + list(listes.codes(listes.RYTHMES)), key=f"ed_proto_ligne_rythme_{i}",
            format_func=lambda c: "—" if not c else listes.libelle(listes.RYTHMES, c),
            label_visibility="collapsed" if i else "visible",
        )
        vitesse = cc6.text_input(
            "Vitesse", key=f"ed_proto_ligne_vitesse_{i}", placeholder="cc/h",
            label_visibility="collapsed" if i else "visible",
        )
        note = cc7.text_input(
            "Note (optionnel)", key=f"ed_proto_ligne_note_{i}",
            label_visibility="collapsed" if i else "visible",
        )
        if voie and produit:
            ligne = {"voie": voie, "produit": produit}
            for cle, valeur in (("dose", dose), ("unite", unite),
                                ("rythme", rythme), ("vitesse", vitesse),
                                ("note", note)):
                if valeur:
                    ligne[cle] = valeur
            lignes_prescription.append(ligne)

    st.markdown("**Explorations proposées**")
    explorations_proposees = []
    types_expl = list(listes.TYPES_EXPLORATION.keys())
    for i in range(4):
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        type_expl = cc1.selectbox(
            "Type", [""] + types_expl, key=f"ed_proto_expl_type_{i}",
            format_func=lambda c: "—" if not c else listes.TYPES_EXPLORATION[c]["libelle"],
            label_visibility="collapsed" if i else "visible",
        )
        delai = cc2.text_input(
            "Délai (H48, quotidien…)", key=f"ed_proto_expl_delai_{i}",
            label_visibility="collapsed" if i else "visible",
        )
        libelle_expl = cc3.text_input(
            "Libellé affiché", key=f"ed_proto_expl_libelle_{i}",
            label_visibility="collapsed" if i else "visible",
        )
        if type_expl:
            explorations_proposees.append({
                "type": type_expl,
                "delai": delai,
                "libelle": libelle_expl or listes.TYPES_EXPLORATION[type_expl]["libelle"],
            })

    st.markdown("**Consignes** (une par ligne)")
    consignes_brutes = st.text_area(
        "Consignes", key="ed_proto_consignes", height=100, label_visibility="collapsed"
    )
    consignes = [l.strip() for l in consignes_brutes.splitlines() if l.strip()]

    st.markdown("**Validation**")
    c1, c2 = st.columns(2)
    valide_coche = c1.checkbox("Validé par le chef de service", key="ed_proto_valide")
    signe_par = c2.text_input("Signé par", key="ed_proto_signe_par")
    if valide_coche and not signe_par:
        st.warning("Indiquer qui valide, sinon le protocole reste un brouillon.")

    col_save, col_del = st.columns([3, 1])
    if col_save.button("Enregistrer le protocole", type="primary"):
        code_normalise = _slug(code)
        if not code_normalise:
            st.error("Le code est obligatoire.")
        elif not titre:
            st.error("Le titre est obligatoire.")
        elif not code_existant and code_normalise in codes_existants:
            st.error("Ce code existe déjà — en choisir un autre.")
        else:
            declencheur = (
                {} if valeur_declencheur is None
                else {"type": type_declencheur, "valeur": valeur_declencheur}
            )
            ancien = protocoles.lire_fichier(code_existant) if code_existant else {}
            contenu = {
                "titre": titre,
                "version": ancien.get("version", ""),
                "signe_par": signe_par or None,
                "valide": bool(valide_coche and signe_par),
                "declencheur": declencheur,
                "lignes_prescription": lignes_prescription,
                "explorations_proposees": explorations_proposees,
                "consignes": consignes,
                "note": ancien.get(
                    "note", "Créé ou modifié depuis l'éditeur de protocoles."
                ),
            }
            protocoles.enregistrer(code_normalise, contenu)
            st.success(f"Protocole « {code_normalise} » enregistré.")
            st.session_state.pop("ed_proto_charge", None)
            st.rerun()
    if code_existant and col_del.button("Supprimer"):
        protocoles.supprimer(code_existant)
        st.success("Protocole supprimé.")
        st.session_state.pop("ed_proto_charge", None)
        st.rerun()


def _regles() -> None:
    st.caption(
        "Les rappels et la check-list quotidienne sont déclaratifs : ils vivent "
        f"dans `{aides.DOSSIER}`, avec leurs seuils et leurs sources. Les modifier "
        "ne demande pas de reprogrammer le logiciel — c'est la règle R4 de la "
        "feuille de route. Aucun ne propose de posologie (SPEC §3.1)."
    )
    for jeu in aides.inventaire():
        etat = (
            f"Validé — signé par {jeu['signe_par']}" if jeu["valide"] and jeu["signe_par"]
            else "En service mais non signé — à valider par un senior"
        )
        lignes = [f"Version {jeu['version']} · {jeu['nb']} règles", etat]
        if jeu["source"]:
            lignes.append(jeu["source"])
        theme.bloc(jeu["titre"], lignes, theme.VERT if jeu["valide"] else theme.ORANGE)

    _editeur_regles()


# --------------------------------------------------------------------------
# Éditeur de règles — un formulaire, jamais de fichier à ouvrir
# --------------------------------------------------------------------------

def _editeur_regles() -> None:
    st.divider()
    st.subheader("Ajouter ou modifier une règle")
    st.caption(
        "Une règle enregistrée ici s'applique tout de suite, comme si elle "
        "avait été tapée à la main dans le fichier. Le badge « non signé » "
        "reste affiché tant qu'un senior n'a pas validé le fichier — ça ne "
        "bloque rien, ce n'est qu'un avertissement."
    )

    fichiers = list(aides.noms_fichiers())
    choix_fichier = st.selectbox(
        "Fichier de règles", fichiers + ["Nouveau fichier…"], key="ed_regle_choix_fichier"
    )

    if choix_fichier == "Nouveau fichier…":
        with st.form("nouveau_fichier_regles"):
            nom = st.text_input("Nom du fichier (ex. « rappels_cardio »)")
            titre = st.text_input("Titre affiché")
            if st.form_submit_button("Créer le fichier"):
                nom_normalise = _slug(nom)
                if not nom_normalise:
                    st.error("Le nom est obligatoire.")
                elif nom_normalise in fichiers:
                    st.error("Un fichier de ce nom existe déjà.")
                else:
                    aides.creer_fichier(nom_normalise, titre or nom_normalise)
                    st.success(f"Fichier « {nom_normalise} » créé — le choisir dans la liste.")
        return

    contenu = aides.lire_fichier(choix_fichier)
    regles_existantes = contenu.get("regles", [])

    if regles_existantes:
        st.caption(f"{len(regles_existantes)} règle(s) dans ce fichier :")
        for r in regles_existantes:
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.write(f"**{r.get('libelle', r['code'])}** · `{r['code']}`")
            if c2.button("Modifier", key=f"mod_{choix_fichier}_{r['code']}"):
                _charger_regle_dans_editeur(r)
                st.rerun()
            if c3.button("Supprimer", key=f"sup_{choix_fichier}_{r['code']}"):
                contenu["regles"] = [x for x in regles_existantes if x["code"] != r["code"]]
                aides.enregistrer_fichier(choix_fichier, contenu)
                st.success(f"Règle « {r['code']} » supprimée.")
                st.rerun()
        st.markdown("---")

    code_cible = st.session_state.get("ed_regle_code_cible")
    st.markdown(
        f"**Modifier « {code_cible} »**" if code_cible else "**Nouvelle règle**"
    )
    if code_cible and st.button("Annuler — créer une nouvelle règle à la place"):
        _reinitialiser_editeur_regle()
        st.rerun()

    code = st.text_input(
        "Code (identifiant unique)", key="ed_regle_code", disabled=bool(code_cible)
    )
    libelle = st.text_input("Libellé (titre affiché)", key="ed_regle_libelle")
    message = st.text_area(
        "Message — { un_fait} insère sa valeur, ex. « Plaquettes à {plaquettes} »",
        key="ed_regle_message", height=70,
    )
    trouve = regles_dom.contient_une_posologie(message) if message else None
    if trouve:
        st.error(
            f"Le mot « {trouve} » ressemble à une posologie — le logiciel ne "
            "calcule ni ne propose de dose (SPEC §3.1). Reformuler le message."
        )

    c1, c2 = st.columns(2)
    gravite = c1.selectbox("Gravité", ["alerte", "attention", "info"], key="ed_regle_gravite")
    source = c2.text_input("Source (optionnel)", key="ed_regle_source")

    combinaison = st.radio(
        "Condition à remplir", ["et (toutes)", "ou (au moins une)"],
        key="ed_regle_combinaison", horizontal=True,
    )

    st.caption("Conditions :")
    libelles_faits = dict(regles_dom.FAITS_CONNUS)
    noms_faits = [f for f, _l in regles_dom.FAITS_CONNUS]
    conditions = []
    for i in range(_NB_LIGNES_CONDITION):
        cc1, cc2, cc3 = st.columns([2, 1, 1])
        fait = cc1.selectbox(
            f"Fait {i + 1}", [""] + noms_faits, key=f"ed_regle_fait_{i}",
            format_func=lambda f: "—" if not f else libelles_faits.get(f, f),
        )
        op = cc2.selectbox("Opérateur", [""] + list(_OPERATEURS_EDITEUR), key=f"ed_regle_op_{i}")
        valeur_brute = cc3.text_input(
            "Valeur", key=f"ed_regle_valeur_{i}", disabled=op in _SANS_VALEUR or not op,
        )
        if fait and op:
            cond = {"fait": fait, "op": op}
            if op not in _SANS_VALEUR:
                valeur = _valeur_typee(valeur_brute)
                if valeur is None:
                    continue
                cond["valeur"] = valeur
            conditions.append(cond)

    if conditions:
        with st.expander("Tester avec des valeurs d'exemple"):
            faits_test = {}
            for cond in conditions:
                brut = st.text_input(
                    f"Valeur de test — {libelles_faits.get(cond['fait'], cond['fait'])}",
                    key=f"ed_regle_test_{cond['fait']}",
                )
                if brut.strip():
                    minuscule = brut.strip().lower()
                    faits_test[cond["fait"]] = (
                        True if minuscule in ("vrai", "oui", "true") else
                        False if minuscule in ("faux", "non", "false") else
                        _valeur_typee(brut)
                    )
            if st.button("Tester"):
                regle_test = regles_dom.Regle.depuis_dict({
                    "code": "test", "libelle": "test", "message": "",
                    "conditions": conditions,
                    "combinaison": "ou" if combinaison.startswith("ou") else "et",
                })
                if regles_dom.declenchee(regle_test, faits_test):
                    st.success("Cette règle se déclencherait avec ces valeurs.")
                else:
                    st.info("Cette règle ne se déclencherait pas avec ces valeurs.")

    if st.button("Enregistrer la règle", type="primary"):
        code_normalise = _slug(code)
        if not code_normalise:
            st.error("Le code est obligatoire.")
        elif not libelle:
            st.error("Le libellé est obligatoire.")
        elif not message:
            st.error("Le message est obligatoire.")
        elif trouve:
            st.error("Corriger le message avant d'enregistrer.")
        elif not conditions:
            st.error("Au moins une condition complète est nécessaire.")
        elif not code_cible and any(r["code"] == code_normalise for r in regles_existantes):
            st.error("Ce code existe déjà dans ce fichier — en choisir un autre.")
        else:
            nouvelle_regle = {
                "code": code_normalise,
                "libelle": libelle,
                "message": message,
                "gravite": gravite,
                "source": source,
                "combinaison": "ou" if combinaison.startswith("ou") else "et",
                "conditions": conditions,
            }
            autres = [r for r in regles_existantes
                     if r["code"] != (code_cible or code_normalise)]
            contenu["regles"] = autres + [nouvelle_regle]
            aides.enregistrer_fichier(choix_fichier, contenu)
            st.success(f"Règle « {code_normalise} » enregistrée.")
            _reinitialiser_editeur_regle()
            st.rerun()
