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
from rea.rendu.gabarit import Brut, VariableInconnue, rendre, variables_attendues
from rea.services import bilans, dispositifs, microbiologie, prescriptions, sejours

AUJ = "2026-09-05"
J1 = "2026-09-04"
J2 = "2026-09-03"


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
    fournies = set(feuille.contexte(base, sid, AUJ))
    assert not (attendues - fournies), f"non fournies : {attendues - fournies}"


# -- ce que le logiciel remplit ---------------------------------------------

def test_les_bilans_des_jours_precedents_sont_reportes(base, dossier):
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00",
                                 valeurs={"hb": 9.8, "k": 3.4})
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00",
                                 valeurs={"hb": 9.2, "k": 3.1})
    html = feuille.generer(base, sid, AUJ)
    for valeur in ("9,8", "9,2", "3,4", "3,1"):
        assert valeur in html


def test_la_colonne_du_jour_reste_vide_pour_la_garde(base, dossier):
    """Les bilans de la nuit s'écrivent à la main et sont ressaisis le
    lendemain matin : le logiciel ne doit pas occuper leur place."""
    _pid, sid = dossier
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{AUJ}T02:00",
                                 valeurs={"hb": 7.1})
    contexte = feuille.contexte(base, sid, AUJ)
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
    contexte = feuille.contexte(base, sid, AUJ)
    ligne = contexte["ivRows"][0]
    cases = re.findall(r'<div style="display:flex;align-items:center;'
                       r'justify-content:center">(.*?)</div>', ligne["grille"].html)
    heures_avec_rond = {i for i, c in enumerate(cases) if "○" in c}
    assert heures_avec_rond == {0, 6, 12, 18}


def test_la_prise_de_minuit_n_est_pas_perdue(base, dossier):
    """Le service note « 24 h » pour minuit, la grille imprimée s'arrête à 23 :
    sans repli, la prise de minuit disparaissait de la feuille."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                dose=1, unite="g", rythme="x3/j", date_debut=J2)
    grille = feuille.contexte(base, sid, AUJ)["ivRows"][0]["grille"].html
    cases = re.findall(r'justify-content:center">(.*?)</div>', grille)
    assert {i for i, c in enumerate(cases) if "○" in c} == {0, 8, 16}


def test_une_perfusion_continue_n_a_pas_de_rond(base, dossier):
    """Un débit continu se note en ml/h dans les cases, il ne se coche pas."""
    _pid, sid = dossier
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PSE",
                                produit="Noradrénaline", vitesse=12,
                                rythme="continu", date_debut=J2)
    grille = feuille.contexte(base, sid, AUJ)["pseRows"][0]["grille"].html
    assert "○" not in grille


def test_les_examens_demandes_la_veille_sont_a_leur_ligne(base, dossier):
    _pid, sid = dossier
    prescriptions.definir_bilans_demandes(
        base, sid, AUJ, [("nfs", "06:00"), ("ionogramme", "06:00")]
    )
    contexte = feuille.contexte(base, sid, AUJ)
    libelles = [l["libelle"] for l in contexte["bilanPrescRows"]]
    assert "NFS" in libelles and "Ionogramme" in libelles
    ligne = next(l for l in contexte["bilanPrescRows"] if l["libelle"] == "NFS")
    cases = re.findall(r'justify-content:center">(.*?)</div>', ligne["grille"].html)
    assert {i for i, c in enumerate(cases) if "◻" in c} == {6}


def test_les_cases_a_demander_demain_sont_cochees(base, dossier):
    _pid, sid = dossier
    demain = (date.fromisoformat(AUJ) + timedelta(days=1)).isoformat()
    prescriptions.definir_bilans_demandes(
        base, sid, demain, [("nfs", "06:00"), ("procalcitonine", "06:00")]
    )
    cases = {c["libelle"]: c["case"] for c in feuille.contexte(base, sid, AUJ)["examensDemain"]}
    assert cases["NFS"] == "☑"
    # « CRP/PCT » est une case pour deux examens : la PCT suffit à la cocher.
    assert cases["CRP/PCT"] == "☑"
    assert cases["Rx thorax"] == "☐"


def test_les_dispositifs_sont_coches_avec_leur_compteur(base, dossier):
    _pid, sid = dossier
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose=J2,
                      details={"reperage_cm": 22})
    abords = feuille.contexte(base, sid, AUJ)["abords"]
    intubation = next(a for a in abords if "Intubé" in a["texte"])
    assert intubation["texte"].startswith("☑")
    assert "J3" in intubation["texte"]          # J1 = jour de pose


def test_la_microbiologie_est_reportee(base, dossier):
    _pid, sid = dossier
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                              type_prelevement="hemoculture", resultat="positif",
                              germe="E. coli BLSE")
    html = feuille.generer(base, sid, AUJ)
    assert "E. coli BLSE" in html


# -- ce que le logiciel laisse vide -----------------------------------------

def test_les_constantes_horaires_restent_manuscrites(base, dossier):
    """Elles se relèvent au lit du malade, sur le papier. Le logiciel étiquette
    les lignes, il ne les remplit pas."""
    _pid, sid = dossier
    contexte = feuille.contexte(base, sid, AUJ)
    for bloc in ("survRowsA", "survRowsB", "survRowsC"):
        for ligne in contexte[bloc]:
            assert ligne["valeurs"].html == ""


def test_aucun_trou_de_gabarit_sur_la_feuille_imprimee(base, dossier):
    _pid, sid = dossier
    html = feuille.generer(base, sid, AUJ)
    corps = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert "{{" not in corps


def test_la_feuille_s_imprime_sans_dependance_externe(base, dossier):
    """Le poste du service peut être hors ligne : ni police téléchargée, ni
    script, ni image distante."""
    _pid, sid = dossier
    html = feuille.generer(base, sid, AUJ)
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html


def test_deux_pages_a3_paysage(base, dossier):
    _pid, sid = dossier
    html = feuille.generer(base, sid, AUJ)
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
    contexte = feuille.contexte(base, sid, AUJ)
    assert "⚠" in contexte["pied"]
    assert "2 ligne(s) de plus" in contexte["pied"]
