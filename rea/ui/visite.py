"""Onglet « Visite » — la pancarte à l'écran, sans papier.

Le reste de l'application est fait pour être lu assis, à cinquante
centimètres, en train de saisir. La visite, c'est l'inverse : on ne tape rien,
on lit un portable posé sur le chariot, debout, et ce qu'on cherche est
toujours la même chose — quel traitement, à quel jour, à quelle dose, et
comment la biologie a bougé depuis hier (demande du service, 9 septembre).

Cet écran n'écrit rien. C'est délibéré : à la visite on lit et on discute,
on ne prescrit pas d'une main en tenant un chariot de l'autre. Un bouton
d'arrêt de traitement à portée de manche est un traitement arrêté par erreur.
Ce qui doit changer se change ensuite, dans les onglets qui servent à ça.
"""

from __future__ import annotations

import html
from datetime import date

import streamlit as st

from .. import analytes, listes
from ..domaine import dispositifs as dom_dispositifs
from ..domaine import prescription as dom
from ..domaine import temperature as temp_dom
from ..domaine.dates import format_date_fr, jour_hospitalisation
from ..services import avis as avis_service
from ..services import bilans as bilans_service
from ..services import constantes as constantes_service
from ..services import dispositifs as dispositifs_service
from ..services import evolution as evolution_service
from ..services import explorations as explorations_service
from ..services import medicaments as medicaments_service
from ..services import microbiologie as micro_service
from ..services import prescriptions as prescriptions_service
from ..services import vitesses as vitesses_service
from . import contexte, prescrit, surveillance, theme

#: Ce qu'on regarde à la visite, dans cet ordre. Pas tout le catalogue : une
#: page de trente valeurs ne se lit pas debout, et ces huit-là décident de la
#: conduite du jour.
ANALYTES_VISITE = ("hb", "plq", "gb", "crp", "pct", "na", "k", "creat", "uree")


def onglet_visite(sejour: dict) -> None:
    date_jour = st.date_input(
        "Jour", value=date.today(), key="visite_jour", format="DD/MM/YYYY",
    )
    date_jour_str = str(date_jour)
    if date_jour_str != date.today().isoformat():
        st.caption(
            f"Vous regardez le {format_date_fr(date_jour_str)} — "
            "les traitements et les valeurs sont ceux de ce jour-là."
        )

    gauche, droite = st.columns([1.15, 1], gap="medium")
    with gauche:
        _traitements(sejour, date_jour_str)
        _bilan_entrees_sorties(sejour, date_jour_str)
    with droite:
        _etat_du_jour(sejour, date_jour_str)
        _biologie(sejour, date_jour_str)
        # Le bilan infectieux est de la biologie : une CRP et une hémoculture
        # se lisent l'une contre l'autre, et les séparer obligeait à monter
        # et descendre l'écran pour les rapprocher. Les avis, eux, n'ont rien
        # d'infectieux — un avis de chirurgie ou de néphrologie se perdait
        # sous un titre qui parlait de germes (demande du service,
        # 10 septembre).
        _infectieux(sejour, date_jour_str)
        _explorations(sejour, date_jour_str)
        _avis(sejour, date_jour_str)
        _plans(sejour, date_jour_str)

    st.divider()
    _surveillance(sejour, date_jour_str)


def _surveillance(sejour: dict, date_jour_str: str) -> None:
    """Le relevé horaire, en bas et sur toute la largeur — avec **sa propre
    date**.

    En bas parce qu'il ne tient pas dans une demi-largeur : vingt-quatre
    colonnes serrées dans la colonne de droite obligeaient à faire défiler le
    tableau pour lire la nuit. Sur toute la largeur, la journée se lit d'un
    seul regard.

    Et daté à part parce que les deux questions ne tombent pas le même jour.
    On regarde le prescrit d'aujourd'hui en se demandant comment s'est passée
    la nuit d'avant-hier — changer de jour en haut de l'écran changerait aussi
    les traitements affichés, et on perdrait ce qu'on était en train de lire
    (demande du service, 10 septembre). La date proposée est celle de la
    veille, la journée close dont on parle à la visite.
    """
    st.markdown("#### Constantes horaires relevées par les infirmiers")
    gauche, droite = st.columns([1, 3])
    with gauche:
        jour = st.date_input(
            "Jour du relevé", value=dom.dernier_jour_clos(),
            key=f"visite_jour_constantes_{sejour['id']}", format="DD/MM/YYYY",
        )
    with droite:
        st.caption(
            "Ce sélecteur est **indépendant** de la date du haut de l'écran : "
            "on peut relire la nuit d'avant-hier sans perdre le prescrit "
            "qu'on est en train de lire."
        )
    surveillance.bloc_du_jour(
        contexte.base(), sejour["id"], str(jour),
        titre=f"Surveillance horaire du {format_date_fr(str(jour))}",
    )


# --------------------------------------------------------------------------
# Colonne de gauche — ce qui est prescrit
# --------------------------------------------------------------------------

def _traitements(sejour: dict, date_jour_str: str) -> None:
    pancarte = prescriptions_service.pancarte_du_jour(
        contexte.base(), sejour["id"], date_jour_str
    )
    vitesses_jour = _vitesses_du_jour(sejour, pancarte, date_jour_str)
    par_voie = pancarte["lignes_par_voie"]
    # La sédation est posée comme dispositif et non prescrite en ligne : sans
    # cette reprise, la seule vitesse qu'un infirmier règle sur une pompe
    # n'apparaissait pas sur la pancarte à l'écran — elle était sur le
    # prescrit et sur la feuille imprimée, mais pas là où le médecin visite
    # (demande du service, 10 septembre).
    sedation = prescrit.ligne_sedation(sejour, date_jour_str)

    for code_voie in listes.ORDRE_VOIES:
        lignes = par_voie.get(code_voie, [])
        synthetique = sedation if code_voie == "PSE" else None
        if not lignes and not synthetique:
            continue
        couleur = theme.COULEUR_VOIE.get(code_voie, theme.GRIS)
        corps = ""
        if synthetique:
            corps += f'<div class="rea-v-texte">{synthetique}</div>'
        corps += "".join(
            _ligne_traitement(ligne, date_jour_str, vitesses_jour) for ligne in lignes
        )
        _bloc(listes.VOIES[code_voie]["titre"], corps, couleur)

    if not any(par_voie.values()) and not sedation:
        st.info("Aucun traitement prescrit ce jour-là.")


def _ligne_traitement(ligne: dict, date_jour_str: str, vitesses_jour: dict) -> str:
    """Une ligne : le compteur, le produit, la dose. Trois colonnes fixes.

    L'œil descend la colonne des compteurs pour trouver le dernier jour d'un
    antibiotique ; il descend celle des doses pour vérifier une posologie. Une
    phrase d'un seul tenant l'oblige à relire chaque ligne en entier.
    """
    # « Imipénème (Tienam) » : la DCI, et la marque pour la reconnaître. Le
    # mode Visite est la pancarte à l'écran — c'est là qu'on lit le
    # traitement à voix haute au lit du malade, et le nom qui vient en tête
    # est celui de la boîte. La marque est ajoutée **avant** le découpage du
    # domaine : `parties_ligne` colle déjà les horaires derrière le nom, et
    # chercher ce texte-là au catalogue ne trouverait rien. Ce qui est
    # enregistré reste la seule DCI ; la parenthèse n'existe qu'à l'écran.
    etiquette, libelle, dose = dom.parties_ligne(
        {**ligne, "produit": medicaments_service.nom_affiche(
            contexte.base(), ligne.get("produit") or "")},
        date_jour_str,
    )
    arretee = ligne["statut"] != "active"
    classe_j = "rea-v-j fin" if etiquette.dernier_jour else "rea-v-j"
    jour = "" if etiquette.introduction else etiquette.texte
    produit = html.escape(libelle)

    details = []
    if etiquette.introduction:
        details.append("introduit ce jour")
    if arretee:
        details.append("arrêté")
    suffixe = (f' <span class="rea-v-detail">{html.escape(" — ".join(details))}</span>'
               if details else "")
    # Une seringue réglée plusieurs fois dans la journée : la suite des
    # vitesses sous la ligne, sans répéter l'unité à chaque heure — elle est
    # déjà dans la colonne des doses, et quatre « cc/h » de plus font déborder
    # la ligne sans rien apprendre.
    par_heure = (vitesses_jour or {}).get(ligne["id"]) or {}
    sous_ligne = ""
    if len(par_heure) > 1:
        suite = " · ".join(f"{h} h : {_nombre(v)}" for h, v in sorted(par_heure.items()))
        sous_ligne = (
            f'<div class="rea-v-texte" style="padding:0 12px 6px 4.4rem;'
            f'font-size:.8rem;color:{theme.GRIS}">{html.escape(suite)}</div>'
        )
    dose = html.escape(dose or "")
    return (
        f'<div class="rea-v-ligne{" arretee" if arretee else ""}">'
        f'<span class="{classe_j}">{html.escape(jour)}</span>'
        f'<span class="rea-v-produit">{produit}{suffixe}</span>'
        f'<span class="rea-v-dose">{dose}</span>'
        "</div>" + sous_ligne
    )


def _vitesses_du_jour(sejour: dict, pancarte: dict, date_jour_str: str) -> dict:
    """La vitesse heure par heure de ce qui coule, comme sur la feuille."""
    par_ligne = {}
    for ligne in pancarte["lignes"]:
        if ligne.get("vitesse") is None or ligne["statut"] != "active":
            continue
        par_heure = vitesses_service.par_heure(
            contexte.base(), vitesses_service.LIGNE, ligne["id"],
            ligne["vitesse"], date_jour_str,
        )
        if par_heure:
            par_ligne[ligne["id"]] = par_heure
    return par_ligne


# --------------------------------------------------------------------------
# Colonne de droite — ce qu'on a mesuré
# --------------------------------------------------------------------------

def _etat_du_jour(sejour: dict, date_jour_str: str) -> None:
    """Ce qui répond en trois lignes à « comment va-t-il ce matin ? »."""
    elements = evolution_service.elements_du_jour(
        contexte.base(), sejour["id"], date_jour_str
    )
    mesures = []
    for cle, libelle, unite in (
        ("fc", "FC", "/min"), ("pas", "PA", " mmHg"), ("temperature", "T°", " °C"),
        ("spo2_clinique", "SpO₂", " %"), ("glasgow", "Glasgow", "/15"),
        ("rass", "RASS", ""), ("diurese_24h", "Diurèse", " mL"),
    ):
        valeur = elements.get(cle)
        if valeur is None:
            continue
        texte = dom.dose_affichee({"dose": valeur}) or str(valeur)
        if cle == "pas" and elements.get("pad") is not None:
            texte = f"{_nombre(valeur)}/{_nombre(elements['pad'])}"
        else:
            texte = _nombre(valeur)
        if cle == "temperature":
            # « 38,4 °C » demande un instant de conversion ; « fébrile » se lit
            # d'un coup d'œil, et c'est ce mot-là qui déclenche une conduite.
            texte += unite + f" · {temp_dom.libelle(temp_dom.categorie(valeur)).lower()}"
            mesures.append(_mesure(libelle, texte, None))
            continue
        mesures.append(_mesure(libelle, texte + unite, None))
    hydrique = evolution_service.texte_bilan_hydrique(
        contexte.base(), sejour["id"], date_jour_str
    )
    if hydrique:
        mesures.append(f'<div class="rea-v-texte">{html.escape(hydrique)}</div>')

    jour_hosp = jour_hospitalisation(sejour["date_admission"], date_jour_str)
    _bloc(f"État du jour — J{jour_hosp}",
          "".join(mesures) or '<div class="rea-v-vide">Rien de relevé ce jour-là.</div>',
          theme.BLEU)
    _gaz_du_sang(sejour, date_jour_str)

    etats = dispositifs_service.etats(contexte.base(), sejour["id"], date_jour_str)
    en_place = [e for e in etats if e.en_place]
    if en_place:
        # Deux redons dans le même abdomen donnaient deux lignes rigoureusement
        # identiques — « Redon J1 (abdomen) » deux fois — alors que ce sont
        # deux drains, deux volumes et parfois deux conduites.
        numeros = dom_dispositifs.numeros_distincts(en_place)
        _bloc("Abords et dispositifs",
              "".join(f'<div class="rea-v-ligne"><span class="rea-v-produit">'
                      f"{html.escape(_avec_numero(e, numeros))}</span></div>"
                      for e in en_place),
              theme.VIOLET)


def _avec_numero(etat, numeros: dict) -> str:
    """« Redon J1 (abdomen) » devient « Redon J1 (abdomen) 2 » — et ne change
    pas quand il n'y en a qu'un : le 1 donnerait à chercher le 2."""
    numero = numeros.get(etat.id)
    return etat.texte if numero is None else f"{etat.texte} {numero}"


def _gaz_du_sang(sejour: dict, date_jour_str: str) -> None:
    """Les trois derniers jours, un gaz par jour, le plus récent à droite.

    Un gaz seul ne dit pas si le poumon s'améliore. Un P/F à 176 après 140 est
    une bonne nouvelle ; après 220, c'en est une mauvaise, et la conduite du
    jour n'est pas la même (demande du service, 10 septembre).

    Un gaz **par jour** et non les trois derniers gaz : un patient qui en a
    quatre dans la journée remplirait la colonne de sa seule matinée, et on
    perdrait justement ce qu'on vient chercher. L'heure accompagne donc chaque
    colonne — un gaz de 6 h et un gaz de 22 h ne se comparent pas.
    """
    gaz = bilans_service.derniers_gaz_du_sang(
        contexte.base(), sejour["id"], date_jour_str
    )
    if not gaz:
        return
    entetes = "".join(
        f'<th style="padding:.15rem .4rem;text-align:right;font-weight:600">'
        f'{html.escape(format_date_fr(g["date_heure"])[:5])}'
        f'<span class="rea-v-detail"> {html.escape(g["date_heure"][11:16])}</span>'
        "</th>"
        for g in gaz
    )
    lignes = ""
    for libelle, lire in (
        ("Mode", lambda g: listes.libelle_mode_court(g.get("mode_ventilatoire"))),
        ("pH", lambda g: _nombre(g.get("ph"))),
        ("PaO₂", lambda g: _nombre(g.get("pao2"))),
        ("PaCO₂", lambda g: _nombre(g.get("paco2"))),
        ("P/F", lambda g: _nombre(bilans_service.rapport_pao2_fio2(
            g.get("pao2"), g.get("fio2")))),
        ("HCO₃⁻", lambda g: _nombre(g.get("hco3"))),
        ("Lactates", lambda g: _nombre(g.get("lactate"))),
    ):
        valeurs = [lire(g) or "" for g in gaz]
        if not any(valeurs):
            continue
        cases = "".join(
            f'<td style="padding:.15rem .4rem;text-align:right'
            f'{";font-weight:700" if rang == len(gaz) - 1 else ";color:#64748b"}">'
            f'{html.escape(v) if v else "—"}</td>'
            for rang, v in enumerate(valeurs)
        )
        lignes += (
            f'<tr><td style="padding:.15rem .4rem;white-space:nowrap">'
            f"{html.escape(libelle)}</td>{cases}</tr>"
        )
    _bloc(
        "Gaz du sang",
        '<div style="overflow-x:auto"><table style="width:100%;font-size:.82rem">'
        f'<tr><th></th>{entetes}</tr>{lignes}</table></div>',
        theme.BLEU,
    )


def _biologie(sejour: dict, date_jour_str: str) -> None:
    """Trois jours côte à côte, la valeur du jour en dernier.

    Une valeur seule ne dit pas si le rein décroche ; deux ne disent pas s'il
    décroche ou s'il remonte. Une créatinine à 152 après 196 rassure — après
    196 puis 120, elle inquiète. C'est la troisième colonne qui fait la
    différence entre une amélioration et un rebond (demande du service,
    10 septembre).

    Les trois jours sont ceux **qui portent un prélèvement**, pas les trois
    derniers du calendrier : on ne prélève pas tous les jours, et deux
    colonnes vides n'apprendraient rien. Chaque colonne porte donc sa date —
    deux colonnes voisines séparées de quatre jours ne se lisent pas comme
    une cinétique.
    """
    jours, matrice = bilans_service.tableau_derniers_jours(
        contexte.base(), sejour["id"], list(ANALYTES_VISITE), date_jour_str
    )
    if not jours:
        _bloc("Biologie",
              '<div class="rea-v-vide">Aucun bilan enregistré.</div>', theme.VERT)
        return

    alertes = {
        v.analyte: v.alerte
        for v in bilans_service.dernieres_variations(
            contexte.base(), sejour["id"], list(ANALYTES_VISITE)
        )
    }
    entetes = "".join(
        f'<th style="padding:.15rem .4rem;text-align:right;font-weight:600">'
        f"{html.escape(format_date_fr(j)[:5])}</th>"
        for j in jours
    )
    lignes = ""
    for id_analyte in ANALYTES_VISITE:
        valeurs = matrice.get(id_analyte)
        if not valeurs:
            continue
        a = analytes.analyte(id_analyte)
        libelle, unite = a.libelle, a.unite
        cases = ""
        for rang, jour in enumerate(jours):
            valeur = valeurs.get(jour)
            dernier = rang == len(jours) - 1
            # Seule la valeur la plus récente porte l'alerte : colorer les
            # trois ferait lire trois anomalies là où il n'y en a qu'une, et
            # la colonne d'avant-hier n'appelle plus aucune conduite.
            couleur = (
                f";color:{theme.ROUGE};font-weight:700"
                if dernier and alertes.get(id_analyte) else
                (";font-weight:700" if dernier else ";color:#64748b")
            )
            cases += (
                f'<td style="padding:.15rem .4rem;text-align:right{couleur}">'
                f"{html.escape(_nombre(valeur)) if valeur is not None else '—'}</td>"
            )
        lignes += (
            f'<tr><td style="padding:.15rem .4rem;white-space:nowrap">'
            f"{html.escape(libelle)}"
            f'<span class="rea-v-detail"> {html.escape(unite or "")}</span></td>'
            f"{cases}</tr>"
        )
    _bloc(
        "Biologie",
        '<div style="overflow-x:auto"><table style="width:100%;font-size:.82rem">'
        f'<tr><th></th>{entetes}</tr>{lignes}</table></div>',
        theme.VERT,
    )


def _infectieux(sejour: dict, date_jour_str: str) -> None:
    """Les prélèvements et leurs germes, juste sous la biologie.

    Une CRP et une hémoculture se lisent l'une contre l'autre : les séparer
    obligeait à monter et descendre l'écran pour les rapprocher (demande du
    service, 10 septembre).
    """
    lignes = []
    for m in micro_service.du_sejour(contexte.base(), sejour["id"])[:6]:
        resultat = listes.libelle(listes.RESULTATS_MICROBIO, m["resultat"])
        if m["resultat"] == "positif" and m.get("germe"):
            resultat = m["germe"]
        prelevement = listes.libelle(listes.PRELEVEMENTS, m["type_prelevement"])
        lignes.append(
            '<div class="rea-v-ligne">'
            f'<span class="rea-v-produit">{html.escape(prelevement)} '
            f'<span class="rea-v-detail">'
            f'{html.escape(format_date_fr(m["date_prelevement"])[:5])}</span></span>'
            f'<span class="rea-v-dose">{html.escape(resultat)}</span>'
            "</div>"
        )
    if lignes:
        _bloc("Bilan infectieux", "".join(lignes), theme.ORANGE)


def _avis(sejour: dict, date_jour_str: str) -> None:
    """Les avis spécialisés, sous leur propre titre.

    Ils étaient rangés avec l'infectieux : un avis de chirurgie ou de
    néphrologie se lisait alors sous un titre qui parlait de germes, et se
    cherchait là où personne n'aurait l'idée de le chercher (demande du
    service, 10 septembre).
    """
    lignes = [
        f'<div class="rea-v-texte">{html.escape(a)}</div>'
        for a in avis_service.lignes_imprimees(contexte.base(), sejour["id"])
    ]
    if lignes:
        _bloc("Avis spécialisés", "".join(lignes), theme.VIOLET)


def _explorations(sejour: dict, date_jour_str: str) -> None:
    """Ce qui a été fait — imageries, échographies, dopplers — et ce qu'on y a vu.

    À la visite, la question « la TDM a-t-elle été faite ? » se pose avant
    « qu'a-t-elle montré ? ». Les deux se répondaient jusqu'ici en changeant
    d'onglet (demande du service, 10 septembre).
    """
    faites = explorations_service.du_sejour(contexte.base(), sejour["id"])
    if not faites:
        return
    lignes = []
    for exploration in faites[:8]:
        titre = listes.TYPES_EXPLORATION.get(
            exploration["type"], {}
        ).get("libelle", exploration["type"])
        jour = format_date_fr(exploration["date_heure"][:10])[:5]
        # La conclusion en entier : l'écran n'est pas la feuille imprimée, il
        # n'a pas à couper à 60 caractères. C'est justement pour lire la visite
        # à l'écran plutôt que sur le papier qu'on ne tronque pas (demande du
        # service, 12 septembre).
        conclusion = (exploration["conclusion"] or "").strip()
        lignes.append(
            '<div class="rea-v-ligne">'
            f'<span class="rea-v-produit">{html.escape(titre)} '
            f'<span class="rea-v-detail">{html.escape(jour)}</span></span>'
            f'<span class="rea-v-dose" style="white-space:normal;'
            f'text-align:right">{html.escape(conclusion)}</span>'
            "</div>"
        )
    _bloc(f"Explorations faites ({len(faites)})", "".join(lignes), theme.BLEU)


def _derniers_etats_de_drain(sejour: dict, date_jour_str: str) -> dict[str, str]:
    """Nom du drain -> son dernier etat releve ce jour-la, en clair.

    Le dernier et non le premier : a la visite, la question est « dans quoi
    est-il branche maintenant », pas « dans quoi l'a-t-on branche a 7 h ».
    """
    base = contexte.base()
    etats = constantes_service.etats_du_jour(base, sejour["id"], date_jour_str)
    dernier: dict[str, str] = {}
    for heure in sorted(etats):
        for cle, texte in etats[heure].items():
            if cle.startswith(constantes_service.PREFIXE_ETAT_DRAIN):
                dernier[cle] = texte

    lisible: dict[str, str] = {}
    for drain in evolution_service.drains_du_jour(base, sejour["id"], date_jour_str):
        cle = constantes_service.cle_etat_drain(drain["dispositif_id"])
        mode, bullage = constantes_service.lire_etat_drain(dernier.get(cle))
        if not mode and not bullage:
            continue
        morceaux = []
        if mode:
            morceaux.append(listes.libelle(listes.ETATS_DRAIN_THORACIQUE, mode))
        if bullage:
            morceaux.append("bullage")
        lisible[drain["libelle"]] = ", ".join(morceaux).lower()
    return lisible


def _bilan_entrees_sorties(sejour: dict, date_jour_str: str) -> None:
    """Ce qui est entré, ce qui est sorti, ce qui reste — sous les traitements.

    Sous les traitements et non ailleurs : les entrées viennent d'eux, et le
    médecin qui vient de lire « Ringer 60 cc/h » veut savoir ce que ça donne
    sur la journée. Chaque drain a sa ligne : deux redons qui donnent 90 et
    410 ne se lisent pas comme deux qui donnent 250 chacun, et c'est le genre
    de chiffre qui fait rappeler le chirurgien.

    Ce qui manque manque : sans diurèse ni poids, le bilan le dit au lieu
    d'afficher un chiffre faux.
    """
    bilan = evolution_service.bilan_hydrique(
        contexte.base(), sejour["id"], date_jour_str
    )
    lignes = [_mesure("Entrées", f"{bilan.entrees_ml:.0f} mL", None)]
    for libelle_entree, volume in bilan.detail_entrees:
        lignes.append(
            f'<div class="rea-v-texte" style="color:{theme.GRIS}">'
            f"{html.escape(libelle_entree)} — {volume:.0f} mL</div>"
        )
    lignes.append(_mesure(
        "Diurèse",
        f"{bilan.diurese_ml:.0f} mL" if bilan.diurese_ml is not None else "—",
        None,
    ))
    # L'etat du drain thoracique se lit AVEC son volume, jamais sans : un drain
    # qui n'a rien donne de la journee ne se lit pas pareil selon qu'il etait
    # clampe — c'est attendu — ou en siphonnage, ou c'est peut-etre un drain
    # bouche (demande du service, 11 septembre).
    etats = _derniers_etats_de_drain(sejour, date_jour_str)
    for libelle_drain, volume in bilan.detail_drains:
        lignes.append(_mesure(libelle_drain, f"{volume:.0f} mL", None,
                              detail=etats.get(libelle_drain)))
    if bilan.pertes_insensibles_ml is not None:
        lignes.append(_mesure(
            "Pertes insensibles", f"{bilan.pertes_insensibles_ml:.0f} mL", None
        ))
    if bilan.net_ml is not None:
        signe = "+" if bilan.net_ml >= 0 else ""
        lignes.append(_mesure(
            "Bilan", f"{signe}{bilan.net_ml:.0f} mL", None,
            alerte="haut" if abs(bilan.net_ml) > 2000 else None,
        ))
    elif bilan.motif_indisponible:
        lignes.append(
            f'<div class="rea-v-texte" style="color:{theme.GRIS}">'
            f"{html.escape(bilan.motif_indisponible)}</div>"
        )
    _bloc("Bilan entrées / sorties", "".join(lignes), theme.BLEU)


def _plans(sejour: dict, date_jour_str: str) -> None:
    entree = evolution_service.journee(
        contexte.base(), sejour["id"], date_jour_str
    )
    if not entree:
        return
    lignes = []
    for cle in evolution_service.PLANS + ("conduite",):
        texte = (entree.get(cle) or "").strip()
        if not texte:
            continue
        titre = evolution_service.LIBELLES_PLANS.get(cle, "Conduite à tenir")
        lignes.append(
            f'<div class="rea-v-texte"><b>{html.escape(titre)}</b> — '
            f"{html.escape(texte)}</div>"
        )
    if lignes:
        _bloc("Évolution du jour", "".join(lignes), theme.GRIS)


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------

def _bloc(titre: str, corps: str, couleur: str) -> None:
    st.markdown(
        f'<div class="rea-v-bloc" style="border-left-color:{couleur}">'
        f'<div class="rea-v-titre" style="color:{couleur}">{html.escape(titre)}</div>'
        f"{corps}</div>",
        unsafe_allow_html=True,
    )


def _mesure(nom: str, valeur: str, avant: str | None, *, alerte: str | None = None,
            detail: str | None = None) -> str:
    """`detail` et non du HTML dans `valeur` : tout ce qui arrive ici est
    échappé, et une balise passée dans la valeur s'affichait telle quelle —
    « 220 mL <span class='rea-v-detail'>· clampé</span> » se lisait ainsi, en
    toutes lettres, sur l'écran de visite. L'échappement reste dans le helper ;
    aucun appelant ne lui passe de balise."""
    classe = f"rea-v-val {alerte}" if alerte else "rea-v-val"
    incise = (f' <span class="rea-v-detail">· {html.escape(detail)}</span>'
              if detail else "")
    return (
        '<div class="rea-v-mesure">'
        f'<span class="rea-v-nom">{html.escape(nom)}</span>'
        f'<span class="{classe}">{html.escape(valeur)}{incise}</span>'
        + (f'<span class="rea-v-avant">{html.escape(avant)}</span>' if avant else "")
        + "</div>"
    )


def _nombre(valeur) -> str:
    """38.6 s'écrit 38,6 ; 92.0 s'écrit 92."""
    if valeur is None:
        return ""
    if isinstance(valeur, (int, float)):
        if float(valeur) == int(valeur):
            return str(int(valeur))
        return f"{valeur}".replace(".", ",")
    return str(valeur)
