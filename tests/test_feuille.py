"""La feuille de réanimation du service, remplie (maquette Kairouan).

Ce qui est vérifié ici, ce n'est pas la beauté de la page — c'est que le
logiciel remplit ce qu'il doit remplir et **laisse vide ce que le service
écrit à la main**. Les deux erreurs symétriques coûtent cher : une feuille qui
n'aide pas, ou une feuille qui affirme quelque chose que personne n'a mesuré.
"""

import re
from datetime import date, timedelta

import pytest

from rea.rendu import feuille
from rea.services import feuille_dossier
from rea.rendu.gabarit import Brut, VariableInconnue, rendre, variables_attendues
from rea.services import bilans, dispositifs, microbiologie, prescriptions, sejours


def _dossier(base, sejour_id, date_jour):
    """Le rendu ne lit plus la base lui-même (règle R3) : il reçoit ce dossier,
    rassemblé par la couche service."""
    return feuille_dossier.rassembler(base, sejour_id, date_jour)

AUJ = "2026-09-05"
J1 = "2026-09-04"
J2 = "2026-09-03"


def _colonne(heure: int) -> int:
    """La colonne d'une heure dans la grille imprimée, qui commence à 8 h."""
    return feuille.ORDRE_HEURES.index(heure)


@pytest.fixture()
def dossier(base):
    pid = sejours.creer_patient(
        base, matricule="2026-04187", nom_affichage="K. Abdelaziz",
        date_naissance="1972-03-14", sexe="M",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission=J2, lit_admission=3,
        poids_kg=78, taille_cm=176,
    )
    return pid, sid


# -- moteur de gabarit -------------------------------------------------------

def test_le_moteur_echappe_par_defaut():
    assert rendre("{{ x }}", {"x": "<script>"}) == "&lt;script&gt;"
    assert rendre("{{ x }}", {"x": Brut("<b>ok</b>")}) == "<b>ok</b>"


def test_les_boucles_imbriquees_sont_correctement_appariees():
    """Les créneaux sont imbriqués dans les jours : un appariement naïf
    refermerait la boucle des jours sur la fermeture des créneaux, et la
    moitié du tableau disparaîtrait sans la moindre erreur."""
    gabarit = ('<sc-for list="{{ jours }}" as="d">[{{ d.nom }}'
               '<sc-for list="{{ d.slots }}" as="s">({{ s }})</sc-for>]</sc-for>')
    rendu = rendre(gabarit, {"jours": [{"nom": "J1", "slots": [1, 2]},
                                       {"nom": "J2", "slots": [3]}]})
    assert rendu == "[J1(1)(2)][J2(3)]"


def test_une_variable_oubliee_est_signalee():
    """Mieux vaut une erreur qu'un « {{ nom }} » imprimé et donné à
    l'infirmier."""
    with pytest.raises(VariableInconnue):
        rendre("{{ inconnue }}", {})


def test_les_commentaires_du_gabarit_sont_laisses_tranquilles():
    gabarit = "<!-- exemple : {{ liste }} --><p>{{ x }}</p>"
    assert rendre(gabarit, {"x": "ok"}) == "<!-- exemple : {{ liste }} --><p>ok</p>"


def test_le_contexte_couvre_tout_le_gabarit(base, dossier):
    """Si le service retouche sa maquette et ajoute un champ, ce test le dit
    au lieu de laisser un trou sur la feuille imprimée."""
    _pid, sid = dossier
    attendues = variables_attendues(feuille.MODELE.read_text(encoding="utf-8"))
    fournies = set(feuille.contexte(_dossier(base, sid, AUJ)))
    assert not (attendues - fournies), f"non fournies : {attendues - fournies}"


# -- ce que le logiciel remplit ---------------------------------------------

def test_les_bilans_des_jours_precedents_sont_reportes(base, dossier):
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00",
                                 valeurs={"hb": 9.8, "k": 3.4})
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"hb": 9.2, "k": 3.1})
    html = feuille.generer(_dossier(base, sid, AUJ))
    for valeur in ("9,8", "9,2", "3,4", "3,1"):
        assert valeur in html


def test_la_colonne_du_jour_reste_vide_pour_la_garde(base, dossier):
    """Les bilans de la nuit s'écrivent à la main et sont ressaisis le
    lendemain matin : le logiciel ne doit pas occuper leur place."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{AUJ}T02:00",
                                 valeurs={"hb": 7.1})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne_hb = next(l for l in contexte["bioHemato"] if l["libelle"] == "Hb")
    cellules = re.findall(r">([^<>]*)</div>", ligne_hb["valeurs"].html)
    creneaux_du_jour = cellules[-feuille.NB_CRENEAUX_PAR_JOUR:]
    assert creneaux_du_jour == [""] * feuille.NB_CRENEAUX_PAR_JOUR
    assert "7,1" not in ligne_hb["valeurs"].html


def test_un_rond_par_prise_a_la_bonne_heure(base, dossier):
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Paracétamol 1 g", dose=1, unite="g",
                                rythme="x4/j", date_debut=J2)
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = contexte["ivRows"][0]
    cases = re.findall(r'<div style="display:flex;align-items:center;'
                       r'justify-content:center">(.*?)</div>', ligne["grille"].html)
    heures_avec_rond = {i for i, c in enumerate(cases) if "○" in c}
    # La grille imprimée commence à 8 h : 0, 6, 12, 18 h occupent d'autres
    # colonnes que leur propre numéro (voir feuille.ORDRE_HEURES).
    assert heures_avec_rond == {_colonne(0), _colonne(6), _colonne(12), _colonne(18)}


def test_la_prise_de_minuit_n_est_pas_perdue(base, dossier):
    """Le service note « 24 h » pour minuit, la grille imprimée s'arrête à 23 :
    sans repli, la prise de minuit disparaissait de la feuille."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                dose=1, unite="g", rythme="x3/j", date_debut=J2)
    grille = feuille.contexte(_dossier(base, sid, AUJ))["ivRows"][0]["grille"].html
    cases = re.findall(r'justify-content:center">(.*?)</div>', grille)
    assert {i for i, c in enumerate(cases) if "○" in c} == {
        _colonne(0), _colonne(8), _colonne(16)
    }


def test_une_perfusion_continue_n_a_pas_de_rond(base, dossier):
    """Un débit continu se note en ml/h dans les cases, il ne se coche pas."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PSE",
                                produit="Noradrénaline", vitesse=12,
                                rythme="continu", date_debut=J2)
    grille = feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]["grille"].html
    assert "○" not in grille


def test_les_examens_demandes_la_veille_sont_a_leur_ligne(base, dossier):
    _pid, sid = dossier
    prescriptions.definir_bilans_demandes(
        base, sid, AUJ, [("nfs", "06:00"), ("ionogramme", "06:00")]
    )
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    libelles = [l["libelle"] for l in contexte["bilanPrescRows"]]
    assert "NFS" in libelles and "Ionogramme" in libelles
    ligne = next(l for l in contexte["bilanPrescRows"] if l["libelle"] == "NFS")
    cases = re.findall(r'justify-content:center">(.*?)</div>', ligne["grille"].html)
    assert {i for i, c in enumerate(cases) if "◻" in c} == {_colonne(6)}


def test_les_cases_a_demander_demain_sont_cochees(base, dossier):
    _pid, sid = dossier
    demain = (date.fromisoformat(AUJ) + timedelta(days=1)).isoformat()
    prescriptions.definir_bilans_demandes(
        base, sid, demain, [("nfs", "06:00"), ("procalcitonine", "06:00")]
    )
    cases = {c["libelle"]: c["case"] for c in feuille.contexte(_dossier(base, sid, AUJ))["examensDemain"]}
    assert cases["NFS"] == "☑"
    # « CRP/PCT » est une case pour deux examens : la PCT suffit à la cocher.
    assert cases["CRP/PCT"] == "☑"
    assert cases["Rx thorax"] == "☐"


def test_les_dispositifs_sont_coches_avec_leur_compteur(base, dossier):
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose=J2,
                      details={"reperage_cm": 22})
    abords = feuille.contexte(_dossier(base, sid, AUJ))["abords"]
    intubation = next(a for a in abords if "Intubé" in a["texte"])
    assert intubation["texte"].startswith("☑")
    assert "J3" in intubation["texte"]          # J1 = jour de pose


def test_la_microbiologie_est_reportee(base, dossier):
    _pid, sid = dossier
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                              type_prelevement="hemoculture", resultat="positif",
                              germe="E. coli BLSE")
    html = feuille.generer(_dossier(base, sid, AUJ))
    assert "E. coli BLSE" in html


# -- ce que le logiciel laisse vide -----------------------------------------

def test_les_constantes_horaires_restent_manuscrites(base, dossier):
    """Elles se relèvent au lit du malade, sur le papier. Le logiciel étiquette
    les lignes, il ne les remplit pas."""
    _pid, sid = dossier
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    for bloc in ("survRowsA", "survRowsB", "survRowsC", "bilanRows"):
        for ligne in contexte[bloc]:
            assert ligne["valeurs"].html == ""


def test_les_bonnes_constantes_vitales_sont_etiquetees(base, dossier):
    """Remarque du service, 6 septembre : l'ancienne liste (FC/SpO2/T°/FR/
    Glasgow/Diurèse/Drain) manquait EVA-BPS, RASS et Dextro, et rangeait
    diurèse/drains sous « Constantes vitales » au lieu de « Sorties &
    drains »."""
    _pid, sid = dossier
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    libelles_vitales = (
        [l["libelle"] for l in contexte["survRowsA"]]
        + [l["libelle"] for l in contexte["survRowsB"]]
        + [l["libelle"] for l in contexte["survRowsC"]]
    )
    for attendu in ("T° (°C)", "FC (bpm)", "FR (cpm)", "SpO₂ (%)", "Glasgow",
                    "EVA — BPS", "RASS", "Dextro (g/l)"):
        assert attendu in libelles_vitales
    assert not any("Diurèse" in l or "Drain" in l for l in libelles_vitales)

    libelles_sorties = [l["libelle"] for l in contexte["bilanRows"]]
    assert libelles_sorties == [
        "Diurèse (ml/h)", "Bandelette urinaire",
        "Redon 1 (ml)", "Redon 2 (ml)", "Redon 3 (ml)",
    ]


def test_aucun_trou_de_gabarit_sur_la_feuille_imprimee(base, dossier):
    _pid, sid = dossier
    html = feuille.generer(_dossier(base, sid, AUJ))
    corps = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert "{{" not in corps


def test_la_feuille_s_imprime_sans_dependance_externe(base, dossier):
    """Le poste du service peut être hors ligne : ni police téléchargée, ni
    script, ni image distante."""
    _pid, sid = dossier
    html = feuille.generer(_dossier(base, sid, AUJ))
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html


def test_deux_pages_a3_paysage(base, dossier):
    _pid, sid = dossier
    html = feuille.generer(_dossier(base, sid, AUJ))
    assert html.count('<section class="page"') == 2
    assert "size: A3 landscape" in html


def test_un_debordement_de_lignes_est_signale(base, dossier):
    """La feuille a un nombre de lignes fixe. Si la prescription déborde, il
    faut le dire — sinon une ligne prescrite n'est simplement pas imprimée."""
    _pid, sid = dossier
    for i in range(4):
        prescriptions.ajouter_ligne(base, sejour_id=sid, voie="SC",
                                    produit=f"Produit {i}", dose=1, unite="mg",
                                    rythme="x1/j", date_debut=J2)
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert "⚠" in contexte["pied"]
    assert "2 ligne(s) de plus" in contexte["pied"]


# -- valeurs calculées et identité -------------------------------------------

def test_le_rapport_pao2_fio2_est_calcule(base, dossier):
    """La seule ligne de la feuille qui n'est ni saisie ni recopiée."""
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T07:00", pao2=90, fio2=50)
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert "180" in contexte["pfRow"].html      # 90 / 0,50


def test_le_rapport_reste_vide_sans_gaz_du_sang(base, dossier):
    """Une case vide dit « pas de gaz du sang », jamais « rapport normal »."""
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T07:00", pao2=90)  # pas de FiO₂
    cellules = re.findall(r">([^<>]*)</div>",
                          feuille.contexte(_dossier(base, sid, AUJ))["pfRow"].html)
    assert set(cellules) == {""}


def test_le_rapport_du_jour_reste_a_la_garde(base, dossier):
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{AUJ}T03:00", pao2=90, fio2=50)
    assert "180" not in feuille.contexte(_dossier(base, sid, AUJ))["pfRow"].html


def test_le_groupe_sanguin_est_imprime(base):
    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="X", date_naissance="1980-01-01",
        groupe_sanguin="O+",
    )
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission=J2,
                               lit_admission=1)
    assert feuille.contexte(_dossier(base, sid, AUJ))["groupe_sanguin"] == "O+"


def test_un_groupe_non_renseigne_ne_devient_pas_une_valeur(base):
    """Un groupe inconnu ne doit jamais être deviné ni affiché comme connu."""
    pid = sejours.creer_patient(
        base, matricule="M2", nom_affichage="Y", date_naissance=None,
        groupe_sanguin="non_renseigne",
    )
    ligne = base.une_ligne("SELECT groupe_sanguin FROM patient WHERE id = ?", (pid,))
    assert ligne["groupe_sanguin"] is None
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission=J2,
                               lit_admission=2)
    assert feuille.contexte(_dossier(base, sid, AUJ))["groupe_sanguin"] == ""


# -- remarques du service, 5 septembre ---------------------------------------

def test_la_grille_commence_a_8h(base, dossier):
    """La relève du matin ouvre la feuille ; minuit en tête n'aidait personne."""
    _pid, sid = dossier
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert contexte["hours"][0] == "8"
    assert contexte["hours"][-1] == "7"


def test_dose_affiche_le_nombre_de_comprimes_en_po(base, dossier):
    _pid, sid = dossier
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PO", produit="Oméprazole", dose=40, unite="mg",
        nb_ampoules=1, rythme="x1/j", date_debut=J2,
    )
    dose = feuille.contexte(_dossier(base, sid, AUJ))["poRows"][0]["dose"]
    assert "1 cp" in dose
    assert "40 mg" in dose


def test_dose_affiche_le_nombre_d_ampoules_ailleurs_qu_en_po(base, dossier):
    _pid, sid = dossier
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="SC", produit="Énoxaparine", dose=4000, unite="UI",
        nb_ampoules=1, rythme="x1/j", date_debut=J2,
    )
    dose = feuille.contexte(_dossier(base, sid, AUJ))["scRows"][0]["dose"]
    assert "1 amp" in dose


def test_dose_privilegie_la_vitesse_sur_le_reste(base, dossier):
    """Sur une seringue électrique, la vitesse est le seul nombre qu'un
    infirmier règle : elle doit passer avant tout le reste."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        dilution="8 mg/50 cc", vitesse=12, rythme="continu", date_debut=J2,
    )
    dose = feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]["dose"]
    assert "12 cc/h" in dose


def test_abords_abrege_le_kt_central_avec_son_site(base, dossier):
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="kt_central", date_pose=J2,
                      site="Sous-clavière gauche")
    texte = next(a["texte"] for a in feuille.contexte(_dossier(base, sid, AUJ))["abords"]
                if "KTVC" in a["texte"])
    assert "sous-C G" in texte
    assert "Cathéter veineux central" not in texte      # la forme longue a disparu ici


def test_abords_abrege_la_sonde_urinaire_sans_calibre(base, dossier):
    """« Sondé » devient SV, sans préciser le numéro — ça ne change pas
    grand-chose et ça prend de la place."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="sonde_urinaire", date_pose=J2,
                      details={"taille_sonde": 16})
    texte = next(a["texte"] for a in feuille.contexte(_dossier(base, sid, AUJ))["abords"]
                if "SV" in a["texte"])
    assert "16" not in texte


def test_abords_abrege_la_sng_avec_narine_et_fixation(base, dossier):
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="sng", date_pose=J2,
                      site="Narine droite", details={"fixation_cm": 55})
    texte = next(a["texte"] for a in feuille.contexte(_dossier(base, sid, AUJ))["abords"]
                if "SNG" in a["texte"])
    assert "ND" in texte and "55cm" in texte


def test_sedation_posee_apparait_aussi_en_pse_avec_sa_vitesse(base, dossier):
    """Elle reste dans les abords (lecture neurologique) mais doit aussi
    apparaître en P.S.E. : c'est une consigne infirmière au même titre
    qu'une autre seringue électrique."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="sedation", date_pose=J2,
                      details={"molecules": "Midazolam", "vitesse": 5})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne_pse = contexte["pseRows"][0]
    assert "Midazolam" in ligne_pse["produit"].html
    assert "5 cc/h" in ligne_pse["dose"]
    # toujours visible dans les abords, avec son compteur de jours
    assert any("Sédation" in a["texte"] for a in contexte["abords"])


def test_sedation_partage_le_quota_de_lignes_pse(base, dossier):
    """La ligne de sédation compte dans les six lignes prévues du bloc P.S.E ;
    elle ne s'ajoute pas par-dessus."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="sedation", date_pose=J2,
                      details={"molecules": "Propofol", "vitesse": 8})
    for i in range(6):
        prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="PSE", produit=f"Produit {i}",
            vitesse=1, rythme="continu", date_debut=J2,
        )
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert len(contexte["pseRows"]) == 6
    assert "⚠" in contexte["pied"]


def test_bloc_peu_rempli_recoit_un_texte_plus_grand(base, dossier):
    """La moitié des cases vides ou plus : le texte grandit, la place ne
    manquant pas."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Ceftriaxone", dose=2, unite="g",
        rythme="x1/j", date_debut=J2,
    )
    style = feuille.contexte(_dossier(base, sid, AUJ))["styleDynamique"].html
    assert "txt-produit-iv" in style
    assert "13.5px" in style


def test_bloc_presque_plein_garde_la_taille_normale(base, dossier):
    _pid, sid = dossier
    for i in range(7):
        prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="IV", produit=f"Produit {i}", dose=1,
            unite="mg", rythme="x1/j", date_debut=J2,
        )
    style = feuille.contexte(_dossier(base, sid, AUJ))["styleDynamique"].html
    assert "txt-produit-iv" not in style


# -- motif / transport / ATCD auto-générés (5 septembre) ---------------------

def test_le_motif_traumatique_reprend_la_region_et_sa_precision(base, dossier):
    """L'interne ne doit plus retranscrire à la main ce qu'il a déjà saisi à
    l'admission sur l'onglet Identité."""
    _pid, sid = dossier
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien"],
        precisions={"cranien": "Hématome extra-dural droit avec engagement temporal"},
    )
    base.mettre_a_jour("sejour", sid, {"traumatique": 1, "mecanisme": "avp_deux_roues"})
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "Traumatisme crânien" in html
    assert "Hématome extra-dural droit avec engagement temporal" in html


def test_le_motif_non_traumatique_reprend_le_principal_et_les_associes(base, dossier):
    _pid, sid = dossier
    sejours.definir_motifs(
        base, sid, motif_principal="choc_septique", motifs_associes=["acidocetose"],
    )
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "choc septique" in html.lower() or "Choc septique" in html
    assert "acidocétose" in html.lower()


def test_le_transport_reprend_la_provenance(base):
    pid = sejours.creer_patient(base, matricule="M3", nom_affichage="Z", date_naissance=None)
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission=J2, lit_admission=4,
        provenance_type="urgences", provenance_detail="SAMU",
    )
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "SAMU" in html


def test_les_antecedents_sont_repris_sans_les_allergies(base, dossier):
    """Les allergies restent dans leur propre encart rouge — les dupliquer
    ici referait deux fois la même alerte, à deux endroits différents."""
    _pid, sid = dossier
    sejour = base.une_ligne("SELECT patient_id FROM sejour WHERE id = ?", (sid,))
    sejours.ajouter_antecedent(base, patient_id=sejour["patient_id"], categorie="personnel", libelle="Diabète type 2")
    sejours.ajouter_antecedent(base, patient_id=sejour["patient_id"], categorie="allergie", libelle="Pénicilline")
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "Diabète type 2" in html
    assert "Pénicilline" not in html


def test_sans_antecedent_reste_distingue_de_non_renseigne(base, dossier):
    _pid, sid = dossier
    sejour = base.une_ligne("SELECT patient_id FROM sejour WHERE id = ?", (sid,))
    assert "Non renseignés" in feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    sejours.definir_etat_antecedents(base, sejour["patient_id"], "absent")
    assert "Aucun connu" in feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html


def test_chaque_antecedent_est_sur_sa_propre_ligne(base, dossier):
    """Remarque du service, 6 septembre : une phrase à virgules se relit
    mal au pied du lit — un antécédent par ligne."""
    _pid, sid = dossier
    sejour = base.une_ligne("SELECT patient_id FROM sejour WHERE id = ?", (sid,))
    sejours.ajouter_antecedent(base, patient_id=sejour["patient_id"], categorie="personnel", libelle="HTA")
    sejours.ajouter_antecedent(base, patient_id=sejour["patient_id"], categorie="personnel", libelle="Diabète type 2")
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "<div>HTA</div>" in html
    assert "<div>Diabète type 2</div>" in html


def test_les_circonstances_reprennent_le_mecanisme_et_son_detail(base, dossier):
    """Exemple du service : « Circonstances : AVP deux-roues — heurté par
    une voiture », sur sa propre ligne, séparée du motif."""
    _pid, sid = dossier
    base.mettre_a_jour("sejour", sid, {
        "traumatique": 1, "mecanisme": "avp_deux_roues",
        "mecanisme_detail": "heurté par une voiture",
    })
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "<b>Circonstances :</b> AVP deux-roues — heurté par une voiture</div>" in html


def test_pas_de_circonstances_si_non_traumatique(base, dossier):
    _pid, sid = dossier
    sejours.definir_motifs(base, sid, motif_principal="choc_septique")
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "Circonstances" not in html


def test_traitement_habituel_absent_n_est_pas_ecrit(base, dossier):
    """« Si pas de traitement habituel, ne pas l'écrire » — pas de ligne
    vide, pas de « Ttt habituel — » sans valeur."""
    _pid, sid = dossier
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "Ttt habituel" not in html


def test_traitement_habituel_present_est_ecrit(base, dossier):
    _pid, sid = dossier
    pid = base.une_ligne("SELECT patient_id FROM sejour WHERE id = ?", (sid,))["patient_id"]
    base.mettre_a_jour("patient", pid, {"traitement_habituel": "Metformine 1000 x2/j"})
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "<b>Ttt habituel :</b> Metformine 1000 x2/j</div>" in html


def test_chaque_region_et_motif_associe_est_sur_sa_propre_ligne(base, dossier):
    _pid, sid = dossier
    base.mettre_a_jour("sejour", sid, {"traumatique": 1})
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien", "thoracique"],
        precisions={"cranien": "Hématome extra-dural droit"},
    )
    sejours.definir_motifs(base, sid, motif_principal=None, motifs_associes=["acidocetose"])
    html = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "<div>Traumatisme crânien : Hématome extra-dural droit</div>" in html
    assert "<div>Traumatisme thoracique</div>" in html
    assert "<div>Acidocétose diabétique</div>" in html


# -- récapitulatif biologique : lignes combinées (6 septembre) ---------------

def test_tp_et_inr_partagent_une_ligne(base, dossier):
    """Remarque du service : toujours lus ensemble, ils doivent tenir sur
    une seule ligne du récapitulatif, pas deux."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"tp": 85, "inr": 1.1})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    libelles = [l["libelle"] for l in contexte["bioHemato"]]
    assert "TP / INR" in libelles
    assert "TP" not in libelles and "INR" not in libelles
    ligne = next(l for l in contexte["bioHemato"] if l["libelle"] == "TP / INR")
    assert "85/1,1" in ligne["valeurs"].html


def test_une_seule_valeur_du_couple_ne_perd_pas_le_separateur(base, dossier):
    """Si seul le TP est arrivé, la case affiche « 85 », pas « 85/ »."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"tp": 85})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["bioHemato"] if l["libelle"] == "TP / INR")
    assert "85" in ligne["valeurs"].html
    assert "85/" not in ligne["valeurs"].html


def test_calcium_magnesium_phosphore_regroupes(base, dossier):
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"ca": 2.3, "mg": 0.8, "phosphore": 1.0})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    libelles = [l["libelle"] for l in contexte["bioAutres"]]
    assert "Ca²⁺ / Mg²⁺ / Phosphore" in libelles
    assert "CRP" in libelles  # pas retirée, seulement complétée


def test_sao2_vt_ai_sont_reportes(base, dossier):
    """Nouveaux paramètres de ventilation (remarque du service, 6
    septembre) : Vt et l'aide inspiratoire (combinée à FR), SaO2 remplace
    le SpO2 continu dans le tableau des gaz du sang (déjà suivi heure par
    heure sur le verso)."""
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T07:00", sao2=97, vt=450, ai=12, fr=18)
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    libelles_gaz = [l["libelle"] for l in contexte["gdsGaz"]]
    libelles_vent = [l["libelle"] for l in contexte["gdsVent"]]
    assert "SaO₂" in libelles_gaz
    assert "SpO₂" not in libelles_gaz
    assert "Vt" in libelles_vent
    assert "FR / AI" in libelles_vent
    ligne = next(l for l in contexte["gdsGaz"] if l["libelle"] == "SaO₂")
    assert "97" in ligne["valeurs"].html
