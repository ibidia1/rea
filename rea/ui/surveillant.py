"""L'écran du surveillant (SPEC §5.9).

Il répond à trois questions, et il est fait pour qu'aucune ne demande de
chercher :

1. **Qui s'occupe de qui**, vacation par vacation — pour appeler la bonne
   personne sans faire le tour des chambres.
2. **Ce qu'il faut commander**, patient par patient — la liste à présenter à
   la pharmacie.
3. **Ce qui a changé** dans les prescriptions. C'est le point qui justifie
   l'écran : aujourd'hui le surveillant relit chaque pancarte pour repérer les
   nouveautés de la garde. Il en manque, et un antibiotique commencé à 4 h du
   matin n'est commandé qu'à midi. Ici, les changements viennent à lui.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from ..domaine import vacations as dom_vacations
from ..domaine.dates import format_date_fr
from ..services import administrations as adm_service
from ..services import affectations as affectations_service
from ..services import supervision as supervision_service
from ..services import utilisateurs as utilisateurs_service
from . import theme


def ecran(base, utilisateur_id: str | None = None) -> None:
    st.title("Surveillance du service")
    vacation_courante, jour_courant = affectations_service.poste_courant()
    st.caption(
        f"Vacation en cours : {dom_vacations.libelle(vacation_courante)} "
        f"({dom_vacations.horaire(vacation_courante)}) — "
        f"prise de poste le {format_date_fr(jour_courant)}"
    )

    vues = {
        "Non donnés à traiter": lambda: _a_traiter(base),
        "Nouveautés du prescrit": lambda: _nouveautes(base),
        "Qui s'occupe de qui": lambda: _affectations(base, utilisateur_id),
        "Médicaments à demander": lambda: _medicaments(base),
    }
    noms = list(vues)
    choix = st.segmented_control(
        "Vue", noms, default=st.session_state.get("vue_surveillant", noms[0]),
        key="segments_surveillant", label_visibility="collapsed",
    ) or st.session_state.get("vue_surveillant", noms[0])
    st.session_state["vue_surveillant"] = choix
    vues[choix]()


# --------------------------------------------------------------------------
# Ce qui n'a pas été donné, et pourquoi
# --------------------------------------------------------------------------

def _a_traiter(base) -> None:
    """Les traitements sautés qui demandent une action, groupés par action.

    C'est la vue qui ouvre l'écran, parce que c'est celle qui a une heure de
    validité : un antibiotique qui manque à 8 h manquera à 16 h si personne ne
    le commande. Le reste — nouveautés, affectations — peut attendre midi.
    """
    jour = st.date_input("Journée", value=date.today(), key="surv_jour_traiter")
    lignes = adm_service.a_traiter(base, str(jour))
    if not lignes:
        st.success(
            "Rien à traiter : aucun traitement n'a été noté « non donné » "
            "pour un motif qui demande une action."
        )
        st.caption(
            "Les motifs sans action — patient au bloc, à jeun, suspendu par "
            "le médecin — ne figurent pas ici : une liste qui contient tout "
            "ne se lit plus."
        )
        return

    par_action: dict[str, list] = {}
    for ligne in lignes:
        par_action.setdefault(ligne["action"], []).append(ligne)

    for action, groupe in par_action.items():
        contenu = "".join(
            f"<div style='padding:.25rem 0;font-size:.88rem'>"
            f"<b>{l['produit']}</b> ({l['voie']}) à {l['heure_prevue']:02d} h — "
            f"{l['nom_affichage']}, matricule {l['matricule']}, "
            f"lit {l['lit_admission']}"
            f"<br><span style='color:#64748b'>{l['libelle_motif']}"
            + (f" — {l['motif']}" if l.get("motif") else "")
            + (f" · noté par {l['soignant']}" if l.get("soignant") else "")
            + "</span></div>"
            for l in groupe
        )
        theme.bloc_html(
            f"{adm_service.ACTIONS[action]} ({len(groupe)})", contenu,
            theme.ROUGE if action == "pharmacie" else theme.ORANGE,
        )


# --------------------------------------------------------------------------
# Ce qui a changé
# --------------------------------------------------------------------------

def _nouveautes(base) -> None:
    st.caption(
        "Ce qui a été ajouté ou arrêté dans les prescriptions, du plus récent "
        "au plus ancien. Le matricule est là parce que c'est lui qu'on donne à "
        "la pharmacie."
    )
    jours = st.slider("Depuis combien de jours", 1, 14, 2, key="nouveautes_jours")
    evenements = supervision_service.nouveautes(base, depuis_jours=jours)
    if not evenements:
        st.info(f"Aucun changement de prescription depuis {jours} jour(s).")
        return

    st.caption(f"{len(evenements)} changement(s)")
    for e in evenements:
        couleur = theme.VERT if e["genre"] == "ajout" else theme.ORANGE
        st.markdown(
            f"<div style='border-left:3px solid {couleur};padding:.25rem .6rem;"
            f"margin-bottom:.35rem'>"
            f"<div style='font-size:.92rem'>{e['texte']}</div>"
            f"<div style='font-size:.75rem;color:#94a3b8'>"
            f"{e['quand_lisible']}"
            + (f" · {e['auteur']}" if e["auteur"] else "")
            + "</div></div>",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# Qui s'occupe de qui
# --------------------------------------------------------------------------

def _affectations(base, utilisateur_id) -> None:
    """Le jour proposé est celui de la **prise de poste en cours**, pas la
    date du jour.

    À 2 h du matin le 10, l'équipe de nuit est celle entrée à 19 h le 9 :
    ouvrir sur le 10 montrerait trois postes vides pendant que le service
    tourne, et le surveillant conclurait que personne n'a pris ses malades.
    """
    _vacation, jour_du_poste = affectations_service.poste_courant()
    jour = st.date_input(
        "Jour de prise de poste", value=supervision_service.parse_jour(jour_du_poste),
        key="surv_jour",
    )
    jour_str = str(jour)
    toutes = affectations_service.du_jour(base, jour_str)
    par_vacation: dict[str, list] = {}
    for a in toutes:
        par_vacation.setdefault(a["vacation"], []).append(a)

    colonnes = st.columns(len(dom_vacations.codes()))
    for colonne, code in zip(colonnes, dom_vacations.codes()):
        with colonne:
            lignes = par_vacation.get(code, [])
            contenu = "".join(
                f"<div style='padding:.2rem 0;font-size:.86rem'>"
                f"<b>Lit {a['lit_admission']}</b> — {a['nom_affichage']}"
                f"<br><span style='color:#64748b'>{a['soignant']}</span></div>"
                for a in lignes
            ) or "<span style='color:#94a3b8'>Personne n'a encore pris ce poste.</span>"
            theme.bloc_html(
                f"{dom_vacations.libelle(code)} · {dom_vacations.horaire(code)}",
                contenu, theme.BLEU if lignes else theme.GRIS,
            )

    with st.expander("Affecter un soignant à un patient"):
        st.caption(
            "Normalement l'infirmier se choisit ses malades en prenant son "
            "poste. Ce panneau sert à rattraper un oubli, ou à réaffecter "
            "quand quelqu'un est appelé ailleurs."
        )
        soignants = [
            u for u in utilisateurs_service.actifs(base)
            if u["role"] in ("infirmier", "surveillant")
        ]
        if not soignants:
            st.warning("Aucun compte infirmier n'existe encore.")
            return
        sejours = supervision_service.sejours_ouverts(base)
        c1, c2, c3 = st.columns(3)
        soignant = c1.selectbox(
            "Soignant", soignants, format_func=lambda u: u["nom"],
            index=None, placeholder="Choisir",
        )
        sejour = c2.selectbox(
            "Patient", sejours,
            format_func=lambda s: f"Lit {s['lit_admission']} — {s['nom_affichage']}",
            index=None, placeholder="Choisir",
        )
        vacation = c3.selectbox(
            "Vacation", dom_vacations.codes(),
            format_func=lambda c: f"{dom_vacations.libelle(c)} ({dom_vacations.horaire(c)})",
        )
        if st.button("Affecter", type="primary",
                     disabled=not (soignant and sejour)):
            affectations_service.affecter(
                base, sejour_id=sejour["id"], soignant_id=soignant["id"],
                date_jour=jour_str, vacation=vacation,
                utilisateur_id=utilisateur_id,
            )
            st.rerun()


# --------------------------------------------------------------------------
# Ce qu'il faut commander
# --------------------------------------------------------------------------

def _medicaments(base) -> None:
    jour = st.date_input("Pour la journée du", value=date.today(),
                         key="surv_jour_medicaments")
    st.caption(
        "Les traitements en cours ce jour-là, patient par patient. Les soins, "
        "la kiné et la surveillance n'y figurent pas : ils ne se commandent "
        "pas, et les mettre ici noierait ce qu'il faut aller chercher."
    )
    patients = supervision_service.medicaments_par_patient(base, str(jour))
    if not patients:
        st.info("Aucun traitement à commander pour cette journée.")
        return

    for p in patients:
        lignes = "".join(
            f"<tr><td style='padding:.15rem .5rem;color:#64748b;white-space:nowrap'>"
            f"{l['voie']}</td>"
            f"<td style='padding:.15rem .5rem'>{l['detail']}</td>"
            f"<td style='padding:.15rem .5rem;color:#94a3b8;white-space:nowrap'>"
            f"{l['jour']}</td></tr>"
            for l in p["lignes"]
        )
        theme.bloc_html(
            f"Lit {p['lit']} — {p['patient']} · matricule {p['matricule']}",
            f"<table style='width:100%;font-size:.85rem'>{lignes}</table>",
            theme.BLEU,
        )
