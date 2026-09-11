"""La feuille de réanimation du service, remplie (maquette Kairouan).

Ce qui est vérifié ici, ce n'est pas la beauté de la page — c'est que le
logiciel remplit ce qu'il doit remplir et **laisse vide ce que le service
écrit à la main**. Les deux erreurs symétriques coûtent cher : une feuille qui
n'aide pas, ou une feuille qui affirme quelque chose que personne n'a mesuré.
"""

import re
from datetime import date, timedelta

import pytest

from rea.domaine import prescription as dom_p
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


def test_le_jour_en_cours_imprime_les_bilans_deja_saisis(base, dossier):
    """Un bilan saisi le jour même doit figurer sur la pancarte imprimée ce
    jour-là, et pas seulement sur celle du lendemain : le service imprimait une
    feuille dépourvue de ses propres résultats du jour (demande du service,
    11 septembre). Les cases restantes du jour en cours demeurent libres pour
    ce que la garde ajoutera à la main pendant la nuit."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{AUJ}T02:00",
                                 valeurs={"hb": 7.1})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne_hb = next(l for l in contexte["bioHemato"] if l["libelle"] == "Hb")
    cellules = re.findall(r">([^<>]*)</div>", ligne_hb["valeurs"].html)
    assert "7,1" in cellules          # le bilan saisi s'imprime
    assert "" in cellules             # et il reste des cases pour la garde


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


def test_une_prise_horaire_coche_les_vingt_quatre_cases(base, dossier):
    """×24/j : une prise par heure, donc toute la grille cochée.

    La grille imprimée a exactement vingt-quatre cases ; le rythme le plus
    serré qu'on puisse prescrire doit s'y ranger sans déborder ni en perdre
    une (rythmes rapprochés, 10 septembre 2026).
    """
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Insuline rapide", dose=4, unite="UI",
                                rythme="x24/j", date_debut=J2)
    grille = feuille.contexte(_dossier(base, sid, AUJ))["ivRows"][0]["grille"].html
    cases = re.findall(r'justify-content:center">(.*?)</div>', grille)
    assert len(cases) == len(feuille.ORDRE_HEURES) == 24
    assert all("○" in c for c in cases)


def test_une_prise_toutes_les_deux_heures_coche_une_case_sur_deux(base, dossier):
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                produit="Sérum salé hypertonique", dose=100,
                                unite="mL", rythme="x12/j", date_debut=J2)
    grille = feuille.contexte(_dossier(base, sid, AUJ))["ivRows"][0]["grille"].html
    cases = re.findall(r'justify-content:center">(.*?)</div>', grille)
    coches = {i for i, c in enumerate(cases) if "○" in c}
    assert coches == {_colonne(h % 24) for h in range(2, 25, 2)}
    assert len(coches) == 12


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


def test_la_crp_rejoint_les_bilans_infectieux(base, dossier):
    """Remarque du service, 6 septembre : la CRP appartient au bilan
    d'infection avec les prélèvements microbiologiques, pas seulement au
    récapitulatif de chimie générale."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"crp": 45})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["infRows"] if l["prelevement"].startswith("CRP"))
    assert "45" in ligne["resultat"]


def test_le_bilan_infectieux_a_une_ligne_par_type_dans_lordre_du_service(base, dossier):
    """L'ordre vient du fichier, pas de la date du dernier résultat : on
    cherche la CRP toujours au même endroit."""
    _pid, sid = dossier
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                              type_prelevement="hemoculture", resultat="negatif")
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00",
                                 valeurs={"crp": 60})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert [l["prelevement"] for l in contexte["infRows"]] == [
        "CRP", "PCT", "ECBU", "PDP", "Hémocultures", "PL",
    ]


def test_chaque_ligne_infectieuse_montre_sa_cinetique(base, dossier):
    """C'est la cinétique, plus que la valeur du jour, qui dit si
    l'antibiothérapie marche."""
    _pid, sid = dossier
    for jour, valeur in ((J2, 210), (J1, 185), (AUJ, 56)):
        bilans.enregistrer_resultats(base, sejour_id=sid,
                                     date_heure=f"{jour}T06:00", valeurs={"crp": valeur})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    crp = next(l for l in contexte["infRows"] if l["prelevement"] == "CRP")
    assert crp["resultat"] == "03/09 : 210 → 04/09 : 185 → 05/09 : 56"


def test_une_ligne_infectieuse_sans_resultat_existe_quand_meme(base, dossier):
    """« PL » sans rien en face se lit « pas de ponction lombaire », ce qui est
    une information ; une ligne absente ne se lit pas du tout."""
    _pid, sid = dossier
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    pl = next(l for l in contexte["infRows"] if l["prelevement"] == "PL")
    assert pl["resultat"] == ""


def test_la_crp_a_quitte_le_recapitulatif_de_chimie(base, dossier):
    """Elle appartient au bilan d'infection, et l'écrire aux deux endroits
    donnait deux cinétiques à lire pour un seul paramètre."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"crp": 60})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    for bloc in ("bioHemato", "bioIono", "bioRenal", "bioHepat", "bioAutres"):
        assert "CRP" not in [l["libelle"] for l in contexte[bloc]]
    assert "60" in next(
        l["resultat"] for l in contexte["infRows"] if l["prelevement"] == "CRP")


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
        "Drain 1 (ml)", "Drain 2 (ml)", "Drain 3 (ml)",
        # Le total des pertes ferme le bloc : devant un redon qui donne, on
        # veut savoir combien le patient a perdu, pas additionner trois
        # colonnes de tête (demande du service, 9 septembre).
        "Total des pertes (ml)",
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
    assert "Ca / Mg / P" in libelles


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


# -- ce que le service a demandé le 8 septembre ------------------------------

def test_la_dose_porte_le_nombre_de_prises(base, dossier):
    """« Tienam 1 g × 3 » : la dose d'une prise ne dit pas la dose de la
    journée, et c'est celle-là qu'on relit pour juger d'une posologie."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                date_debut=AUJ, dose=1, unite="g", rythme="x3/j")
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["ivRows"] if l["produit"] == "Tienam")
    assert ligne["dose"] == "1 g × 3"


def test_une_prise_unique_ne_porte_pas_de_multiplicateur(base, dossier):
    """« 1 g × 1 » n'apprend rien et encombre une colonne étroite."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Rocéphine",
                                date_debut=AUJ, dose=2, unite="g", rythme="x1/j")
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["ivRows"] if l["produit"] == "Rocéphine")
    assert ligne["dose"] == "2 g"


def test_un_jour_sur_deux_ne_porte_pas_de_multiplicateur(base, dossier):
    """Un demi-comprimé par jour ne se note pas « × 0,5 »."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PO", produit="Coumadine",
                                date_debut=AUJ, dose=5, unite="mg", rythme="1j/2")
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["poRows"] if l["produit"] == "Coumadine")
    assert ligne["dose"] == "5 mg"


def test_un_seul_bilan_un_jour_passe_ne_prend_quune_colonne(base, dossier):
    """Un jour prend autant de colonnes qu'il a de prélèvements. Un « 1 »
    solitaire au-dessus d'une seule valeur n'apprend rien : pas de
    numérotation non plus."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"na": 140, "k": 4})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    veille = next(j for j in contexte["days"] if j["libelle"] == "04/09")
    assert veille["poids"] == "1"
    assert veille["slots"] == [""]


def test_plusieurs_bilans_le_meme_jour_prennent_autant_de_colonnes(base, dossier):
    """Deux prélèvements dans la journée : deux colonnes, numérotées pour dire
    laquelle est laquelle."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"na": 140})
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T18:00",
                                 valeurs={"na": 144})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    veille = next(j for j in contexte["days"] if j["libelle"] == "04/09")
    assert veille["poids"] == "2"
    assert veille["slots"] == ["1", "2"]


def test_les_gaz_du_sang_ont_leurs_propres_colonnes(base, dossier):
    """Chaque tableau compte ses propres prélèvements. En les comptant
    ensemble, un jour à deux bilans et deux gaz recevait quatre colonnes dans
    le récapitulatif de chimie, qui n'en remplissait que deux : la troisième
    restait vide au milieu d'un jour, pendant qu'un autre jour, faute de place,
    n'était pas montré du tout."""
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T06:00", ph=7.4)
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T14:00", ph=7.35)
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T18:00",
                                 valeurs={"na": 140})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    # Un seul bilan ce jour-là : une colonne de chimie, pas trois.
    assert next(j for j in contexte["days"] if j["libelle"] == "04/09")["poids"] == "1"
    # Deux gaz : deux colonnes dans le tableau des gaz.
    assert next(j for j in contexte["daysGaz"] if j["libelle"] == "04/09")["poids"] == "2"


def test_aucune_colonne_vide_a_linterieur_dun_jour(base, dossier):
    """Une case vide entre deux valeurs du même jour se lit comme un bilan
    manquant, pas comme une place libre."""
    _pid, sid = dossier
    bilans.enregistrer_gaz_du_sang(base, sid, f"{J1}T14:00", ph=7.35)
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"na": 140})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne_na = next(l for l in contexte["bioIono"] if l["libelle"] == "Na⁺")
    cellules = re.findall(r">([^<>]*)</div>", ligne_na["valeurs"].html)
    assert cellules[0] == "140"          # la seule colonne du 04/09, remplie


def test_la_largeur_du_recapitulatif_ne_bouge_jamais(base, dossier):
    """Douze colonnes, toujours : la page est imprimée, elle ne s'élargit
    pas."""
    _pid, sid = dossier
    for jour, nombre in ((J1, 1), (J2, 3)):
        for i in range(nombre):
            bilans.enregistrer_resultats(base, sejour_id=sid,
                                         date_heure=f"{jour}T{6 + i * 4:02d}:00",
                                         valeurs={"na": 140 + i})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert sum(int(j["poids"]) for j in contexte["days"]) == feuille.NB_COLONNES_BIOLOGIE


def test_un_jour_sans_prelevement_ne_prend_aucune_colonne(base, dossier):
    """Sa place sert à montrer un jour plus ancien qui, lui, a des valeurs :
    c'est ce qui fait tenir une semaine de cinétique sur la feuille."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00",
                                 valeurs={"na": 140})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert "04/09" not in [j["libelle"] for j in contexte["days"]]   # J1, rien
    assert "03/09" in [j["libelle"] for j in contexte["days"]]       # J2, un bilan


def test_le_jour_en_cours_garde_ses_quatre_colonnes_meme_charge(base, dossier):
    """La garde y écrit ses bilans de la nuit : lui reprendre ses créneaux
    reviendrait à lui demander d'écrire dans la marge."""
    _pid, sid = dossier
    for jour in (J1, J2):
        for i in range(4):
            bilans.enregistrer_resultats(base, sejour_id=sid,
                                         date_heure=f"{jour}T{6 + i * 4:02d}:00",
                                         valeurs={"na": 140 + i})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert contexte["days"][-1]["poids"] == "4"
    assert contexte["days"][-1]["libelle"] == "05/09"


def test_les_colonnes_sans_emploi_reviennent_au_jour_en_cours(base, dossier):
    """Séjour trop court pour remplir les huit : le reste va au jour en cours,
    seul à avoir de vraies raisons d'avoir des cases libres. Un bloc sans date
    entre deux jours se lisait comme un jour manquant."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"na": 140})
    colonnes = feuille.contexte(_dossier(base, sid, AUJ))["days"]
    assert [j["libelle"] for j in colonnes] == ["04/09", "05/09"]
    assert [j["poids"] for j in colonnes] == ["1", "11"]


def test_aucune_colonne_anonyme_sur_la_feuille(base, dossier):
    """Toute colonne appartient à un jour daté : sans quoi la feuille donne à
    croire qu'il manque une journée."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00",
                                 valeurs={"na": 140})
    for bloc in ("days", "daysGaz"):
        assert all(j["libelle"] for j in feuille.contexte(_dossier(base, sid, AUJ))[bloc])


def test_le_jour_en_cours_garde_ses_creneaux_numerotes(base, dossier):
    """Il est manuscrit d'un bout à l'autre, et ses créneaux sont numérotés.

    Sans aucun bilan antérieur à montrer, il prend toute la largeur : les
    colonnes sans emploi lui reviennent plutôt que de former un bloc sans date
    au milieu du tableau."""
    _pid, sid = dossier
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    jour = contexte["days"][-1]
    assert jour["libelle"] == "05/09"
    assert jour["poids"] == str(feuille.NB_COLONNES_BIOLOGIE)
    assert jour["slots"][:4] == ["1", "2", "3", "4"]


def test_les_bilans_infectieux_nont_plus_de_colonne_date(base, dossier):
    """La date accompagne chaque résultat sur sa ligne : une colonne de 62 px
    pour cinq caractères prenait la place du résultat."""
    _pid, sid = dossier
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                              type_prelevement="hemoculture", resultat="positif",
                              germe="E. coli")
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["infRows"] if l["prelevement"] == "Hémocultures")
    assert "date" not in ligne
    assert ligne["resultat"] == "04/09 : E. coli"


# -- vitesses écrites heure par heure (demande du service, 8 septembre) ------

def _cases_grille(grille) -> list[str]:
    """Le contenu des 24 cases d'une grille horaire, dans l'ordre imprimé."""
    cases = re.findall(
        r'<div style="display:flex;align-items:center;justify-content:center">(.*?)</div>',
        grille.html,
    )
    return [re.sub(r"<[^>]+>", "", c) for c in cases]


def test_la_vitesse_dune_seringue_souvre_la_journee_a_huit_heures(base, dossier):
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PSE",
                                produit="Noradrénaline", vitesse=25,
                                rythme="continu", date_debut=J1)
    ligne = feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]
    cases = _cases_grille(ligne["grille"])
    assert cases[_colonne(8)] == "25"
    assert [c for c in cases if c] == ["25"]


def test_un_changement_de_vitesse_sinscrit_a_son_heure(base, dossier):
    """L'exemple du service : à 16 h la vitesse passe de 25 à 15."""
    from rea.services import vitesses

    _pid, sid = dossier
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline", vitesse=25,
        rythme="continu", date_debut=J1,
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne_id,
                    date_heure=f"{AUJ}T16:00", vitesse=15)
    cases = _cases_grille(feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]["grille"])
    assert cases[_colonne(8)] == "25"
    assert cases[_colonne(16)] == "15"


def test_la_vitesse_dhier_ouvre_la_journee_daujourdhui(base, dossier):
    """Descendue à 15 hier soir, la seringue ouvre aujourd'hui à 15 : la
    feuille ne réaffiche pas la vitesse prescrite au départ."""
    from rea.services import vitesses

    _pid, sid = dossier
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline", vitesse=25,
        rythme="continu", date_debut=J2,
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne_id,
                    date_heure=f"{J1}T22:00", vitesse=15)
    cases = _cases_grille(feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]["grille"])
    assert cases[_colonne(8)] == "15"
    assert [c for c in cases if c] == ["15"]


def test_la_sedation_porte_aussi_sa_vitesse_dans_les_cases(base, dossier):
    """C'est justement celle qu'on allège tous les jours."""
    from rea.services import vitesses

    _pid, sid = dossier
    did = dispositifs.poser(base, sejour_id=sid, type_="sedation", date_pose=J1,
                            details={"molecules": "Midazolam", "vitesse": 6})
    vitesses.regler(base, cible=vitesses.DISPOSITIF, cible_id=did,
                    date_heure=f"{AUJ}T14:00", vitesse=4)
    ligne = feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]
    cases = _cases_grille(ligne["grille"])
    assert cases[_colonne(8)] == "6"
    assert cases[_colonne(14)] == "4"


def test_une_ligne_a_heures_fixes_garde_ses_ronds(base, dossier):
    """Un rond dit « donner à cette heure-ci », un nombre dit « la pompe est à
    tant » : une ligne qui ne coule pas garde ses ronds."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                dose=1, unite="g", rythme="x3/j", date_debut=J1)
    grille = feuille.contexte(_dossier(base, sid, AUJ))["ivRows"][0]["grille"].html
    assert "○" in grille


def test_une_ligne_arretee_nimprime_plus_de_vitesse(base, dossier):
    """Une seringue arrêtée ne coule plus : ses cases restent vides, et la
    ligne barrée dit pourquoi."""
    _pid, sid = dossier
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline", vitesse=25,
        rythme="continu", date_debut=J2,
    )
    prescriptions.arreter_ligne(base, ligne_id, date_arret=AUJ)
    cases = _cases_grille(feuille.contexte(_dossier(base, sid, AUJ))["pseRows"][0]["grille"])
    assert [c for c in cases if c] == []


# -- antidater ce qui a été fait pendant la garde ---------------------------

def test_un_traitement_introduit_hier_compte_son_deuxieme_jour(base, dossier):
    """Saisi ce matin mais commencé hier soir : la pancarte du jour doit lire
    « J2 », pas « Introduction de »."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                dose=1, unite="g", rythme="x3/j", date_debut=J1)
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    assert contexte["ivRows"][0]["produit"] == "Tienam"
    lignes = feuille_dossier.rassembler(base, sid, AUJ).pancarte["lignes"]
    from rea.domaine import prescription as dom_p
    assert dom_p.etiquette_jour(lignes[0], AUJ).texte == "J2"
    assert dom_p.etiquette_jour(lignes[0], J1).texte == "Introduction de"


def test_un_bilan_antidate_se_range_a_sa_date(base, dossier):
    """Le bilan de la garde, saisi le lendemain matin, doit tomber dans la
    colonne de la nuit — pas dans celle du jour de la frappe."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T23:00",
                                 valeurs={"hb": 8.4})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    # Un seul jour prélevé : il ouvre le tableau, à gauche. Les colonnes sans
    # emploi reviennent au jour en cours — aucune colonne anonyme.
    assert [(j["libelle"], j["poids"]) for j in contexte["days"]] == [
        ("03/09", "1"), ("05/09", "11"),
    ]
    ligne_hb = next(l for l in contexte["bioHemato"] if l["libelle"] == "Hb")
    cellules = re.findall(r">([^<>]*)</div>", ligne_hb["valeurs"].html)
    assert cellules[0] == "8,4"
    assert all(c == "" for c in cellules[1:])


# -- les drains portent leur nom sur le papier -------------------------------

def test_les_lignes_de_drain_prennent_le_nom_des_drains_en_place(base, dossier):
    """Trois emplacements identiques sur du papier rempli à la main, c'est
    deux volumes intervertis tôt ou tard — et une reprise chirurgicale
    décidée sur le chiffre de l'autre drain."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                      date_pose=J1, site="Droit")
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose=J1,
                      site="Abdomen")
    libelles = [l["libelle"] for l in feuille.contexte(_dossier(base, sid, AUJ))["bilanRows"]]
    assert "Drain thoracique (droit) (ml)" in libelles
    assert "Redon (abdomen) (ml)" in libelles
    # L'emplacement inoccupé reste générique : un drain posé après
    # l'impression doit pouvoir s'écrire quelque part.
    assert "Drain 3 (ml)" in libelles


def test_sans_drain_les_emplacements_restent_generiques(base, dossier):
    _pid, sid = dossier
    libelles = [l["libelle"] for l in feuille.contexte(_dossier(base, sid, AUJ))["bilanRows"]]
    assert [l for l in libelles if l.startswith("Drain ")] == [
        "Drain 1 (ml)", "Drain 2 (ml)", "Drain 3 (ml)"
    ]


def test_la_sonde_urinaire_noccupe_pas_un_emplacement_de_drain(base, dossier):
    """Son volume, c'est la diurèse — comptée sur sa propre ligne. L'y
    reporter la compterait deux fois."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="sonde_urinaire", date_pose=J1)
    libelles = [l["libelle"] for l in feuille.contexte(_dossier(base, sid, AUJ))["bilanRows"]]
    assert "Drain 1 (ml)" in libelles


def test_les_valeurs_des_drains_restent_manuscrites(base, dossier):
    """Le volume relevé dans l'évolution est celui des 24 h ; la ligne
    imprimée est horaire. L'y imprimer le ferait lire pour autre chose."""
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose=J1, site="Abdomen")
    for ligne in feuille.contexte(_dossier(base, sid, AUJ))["bilanRows"]:
        assert ligne["valeurs"].html == ""


# -- la créatinine porte sa clairance ---------------------------------------

def test_la_creatinine_est_suivie_de_sa_clairance(base, dossier):
    """« 184 (32) » : une créatinine à 184 ne veut pas dire la même chose chez
    un homme de 40 ans de 90 kg et chez une femme de 80 ans de 45."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"creat": 184})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["bioRenal"] if "réat" in l["libelle"])
    assert "184 (" in ligne["valeurs"].html


def test_sans_poids_la_clairance_nest_pas_inventee(base):
    """Cockcroft-Gault demande le poids : sans lui, la créatinine s'écrit
    seule plutôt qu'accompagnée d'un chiffre faux."""
    pid = sejours.creer_patient(base, matricule="M-CL", nom_affichage="Test",
                                date_naissance="1970-01-01", sexe="M")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission=J2,
                               lit_admission=4)
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"creat": 184})
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = next(l for l in contexte["bioRenal"] if "réat" in l["libelle"])
    cellules = [c for c in re.findall(r">([^<>]*)</div>", ligne["valeurs"].html) if c]
    assert cellules == ["184"]


def test_les_additifs_sont_imprimes_avec_leur_perfusion(base, dossier):
    """L'infirmière prépare d'après la pancarte : une pancarte qui ne dit pas
    les additifs fait préparer un flacon incomplet."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="ENTREES", produit="Ringer Lactate",
        date_debut=J1, sous_type="perfusion", vitesse=60, rythme="continu",
        additifs=dom_p.texte_additifs([("NaCl", 1), ("KCl", 2)]),
    )
    contexte = feuille.contexte(_dossier(base, sid, AUJ))
    ligne = contexte["entRows"][0]
    assert ligne["produit"] == "Ringer Lactate (perfusion) + (1 NaCl + 2 KCl)"


def test_le_tableau_de_biologie_se_remplit_depuis_le_bord_gauche(base, dossier):
    """Une zone vide en tête donnerait à croire qu'un jour manque : les jours
    datés ouvrent le tableau."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"na": 140})
    colonnes = feuille.contexte(_dossier(base, sid, AUJ))["days"]
    assert colonnes[0]["libelle"] == "04/09"       # le jour prélevé, à gauche
    assert colonnes[-1]["libelle"] == "05/09"      # le jour en cours au bout


# -- Glasgow d'arrivée -------------------------------------------------------

def test_le_glasgow_initial_est_imprime_sous_le_transport(base):
    """À J3 sous midazolam, personne ne sait plus s'il est arrivé à 15 ou à 6,
    et c'est un facteur pronostique majeur."""
    pid = sejours.creer_patient(base, matricule="M-GCS", nom_affichage="Test",
                                date_naissance="1980-01-01", sexe="M")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission=J2,
                               lit_admission=5, glasgow_initial=7)
    texte = feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html
    assert "Glasgow initial" in texte
    assert texte.index("Transport") < texte.index("Glasgow initial")
    assert "7" in texte.split("Glasgow initial")[1][:40]


def test_sans_glasgow_initial_la_ligne_nest_pas_imprimee(base, dossier):
    """Une ligne « Glasgow initial : » vide se lit comme un 3."""
    _pid, sid = dossier
    assert "Glasgow initial" not in feuille.contexte(_dossier(base, sid, AUJ))["motifTransportAtcd"].html


# --------------------------------------------------------------------------
# Le logo de l'hôpital
# --------------------------------------------------------------------------
# Emplacement fixe en haut à gauche de la feuille. Le service y dépose son
# image ; tant qu'il ne l'a pas fait, le cadre pointillé montre où elle ira
# (demande du service, 11 septembre).

def test_sans_image_le_cadre_du_logo_montre_l_emplacement(base, dossier, tmp_path, monkeypatch):
    # RACINE isolée : sans image déposée, le cadre pointillé doit apparaître —
    # et aucun logo laissé par un autre test ne doit fausser le résultat.
    monkeypatch.setattr(feuille.config, "RACINE", tmp_path)
    _pid, sid = dossier
    ctx = feuille.contexte(_dossier(base, sid, AUJ))
    assert "LOGO" in ctx["logo"].html
    assert "dashed" in ctx["logo"].html
    assert "<img" not in ctx["logo"].html


def test_l_image_deposee_sur_le_poste_s_imprime(base, dossier, tmp_path, monkeypatch):
    """Déposée dans le dossier du poste (`config.RACINE`), elle est embarquée
    dans la page en base64 — la feuille reste un seul fichier imprimable."""
    monkeypatch.setattr(feuille.config, "RACINE", tmp_path)
    _pid, sid = dossier
    # Un PNG 1×1 valide, comme le ferait un vrai fichier logo.png.
    png_1x1 = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63f8cfc0f01f0005000100ff9a9c1c0000000049454e44ae426082"
    )
    (tmp_path / "logo.png").write_bytes(png_1x1)
    ctx = feuille.contexte(_dossier(base, sid, AUJ))
    assert '<img src="data:image/png;base64,' in ctx["logo"].html
    assert "LOGO" not in ctx["logo"].html


def test_le_gabarit_porte_la_variable_logo():
    modele = feuille.MODELE.read_text(encoding="utf-8")
    assert "{{ logo }}" in modele


# --------------------------------------------------------------------------
# Un avis long revient à la ligne
# --------------------------------------------------------------------------

def test_un_avis_long_revient_a_la_ligne_au_lieu_d_etre_coupe(base, dossier):
    """Sur une feuille imprimée, un avis coupé au bord du cadre n'est pas « un
    peu tronqué » : il est perdu. Il doit revenir à la ligne (demande du
    service, 11 septembre)."""
    from rea.services import avis as avis_service
    _pid, sid = dossier
    long_texte = (
        "Pas d'indication chirurgicale en urgence, surveillance rapprochée de "
        "la fonction rénale et de la diurèse, refaire un angioscanner à 48 h et "
        "rappeler en cas d'aggravation hémodynamique ou de déglobulisation"
    )
    avis_service.demander(base, sejour_id=sid, specialite="CCVT",
                          texte=long_texte, date_avis=AUJ, nom="Dr X",
                          grade="senior")
    ctx = feuille.contexte(_dossier(base, sid, AUJ))
    html_avis = ctx["avisRows"].html
    assert "white-space:nowrap" not in html_avis          # ne file plus hors cadre
    assert "overflow-wrap:anywhere" in html_avis          # casse même un mot trop long
    assert "aggravation hémodynamique" in html_avis       # le texte entier est là
