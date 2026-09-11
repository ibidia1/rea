"""Les drains : les distinguer, les détailler, relever ce qu'ils donnent.

Trois demandes du service du 10 septembre 2026, qui n'en font qu'une : un
drain qu'on ne sait pas nommer est un drain dont on note le volume sur le
voisin.
"""

import importlib

from rea import listes
from rea.domaine import dispositifs as dom


def _service(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _etat(identifiant, type_, site=None, date_pose="2026-09-08"):
    return dom.EtatDispositif(
        type=type_, en_place=True, jour=1, texte="", id=identifiant,
        site=site, date_pose=date_pose,
    )


# --------------------------------------------------------------------------
# Nommer deux drains posés au même endroit
# --------------------------------------------------------------------------

def test_un_drain_seul_n_est_pas_numerote():
    """Le 1 donnerait à chercher le 2."""
    noms = dom.libelles_distincts([_etat("a", "redon", "Abdomen")])
    assert noms == {"a": "Redon (abdomen)"}


def test_deux_redons_dans_le_meme_abdomen_sont_numerotes():
    noms = dom.libelles_distincts([
        _etat("a", "redon", "Abdomen", "2026-09-08"),
        _etat("b", "redon", "Abdomen", "2026-09-09"),
    ])
    assert noms == {"a": "Redon (abdomen) 1", "b": "Redon (abdomen) 2"}


def test_le_numero_suit_l_ordre_de_pose():
    """Celui du chirurgien : le premier posé est le premier nommé, quel que
    soit l'ordre dans lequel la base les rend."""
    noms = dom.libelles_distincts([
        _etat("recent", "redon", "Abdomen", "2026-09-09"),
        _etat("ancien", "redon", "Abdomen", "2026-09-07"),
    ])
    assert noms["ancien"].endswith("1")
    assert noms["recent"].endswith("2")


def test_deux_redons_a_des_endroits_differents_ne_sont_pas_numerotes():
    """Le site suffit déjà à les distinguer."""
    noms = dom.libelles_distincts([
        _etat("a", "redon", "Abdomen"),
        _etat("b", "redon", "Thorax"),
    ])
    assert noms == {"a": "Redon (abdomen)", "b": "Redon (thorax)"}


def test_un_redon_et_un_drain_thoracique_ne_se_numerotent_pas_entre_eux():
    noms = dom.libelles_distincts([
        _etat("a", "redon", "Thorax"),
        _etat("b", "drain_thoracique", "Droit"),
    ])
    assert noms == {"a": "Redon (thorax)", "b": "Drain thoracique (droit)"}


def test_trois_drains_au_meme_endroit_vont_jusqu_a_trois():
    noms = dom.libelles_distincts([
        _etat(c, "drain_abdominal", "Pelvis", f"2026-09-0{i}")
        for i, c in enumerate("abc", start=6)
    ])
    assert sorted(noms.values()) == [
        "Drain abdominal (pelvis) 1",
        "Drain abdominal (pelvis) 2",
        "Drain abdominal (pelvis) 3",
    ]


# --------------------------------------------------------------------------
# Le détail du drain
# --------------------------------------------------------------------------

def test_les_drains_abdominaux_declarent_leur_nature():
    """« Drain abdominal » ne dit pas ce qu'on surveille : un transcystique
    qui donne 400 mL de bile n'est pas un drain de Douglas."""
    for type_ in ("drain_abdominal", "redon"):
        assert "nature_drain" in listes.TYPES_DISPOSITIF[type_]["champs"], type_
    assert "nature_drain" in listes.CHAMPS_DISPOSITIF


def test_la_liste_des_natures_contient_ce_qu_a_cite_le_service():
    codes = listes.codes(listes.NATURES_DRAIN)
    assert "transcystique" in codes
    assert "transcholedocien" in codes
    # La liste ne se ferme pas : aucune liste de drains n'est complète.
    assert "autre" in codes


# --------------------------------------------------------------------------
# Ce que l'infirmier relève, heure par heure
# --------------------------------------------------------------------------

def _patient(base):
    sejours = _service("sejours")
    pid = sejours.creer_patient(base, matricule="D-1", nom_affichage="K. A.",
                                date_naissance="1970-01-01", sexe="M")
    return sejours.creer_sejour(base, patient_id=pid, lit_admission=1,
                                date_admission="2026-09-08")


def test_un_drain_a_sa_cle_de_recueil(base):
    constantes = _service("constantes")
    assert constantes.cle_drain("abc") == "drain:abc"
    assert constantes.est_recueil("drain:abc") is True
    assert constantes.est_recueil("diurese") is True
    assert constantes.est_recueil("fc") is False


def test_les_niveaux_d_un_drain_se_cumulent_en_volume(base):
    """Comme la diurèse : l'infirmier écrit le niveau du bocal, le logiciel
    fait les différences. Additionner les cases recompterait le même liquide
    à chaque heure."""
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="redon",
                              site="Abdomen", date_pose="2026-09-08")
    cle = constantes.cle_drain(drain)
    for heure, niveau in ((8, 40), (9, 90), (10, 150)):
        constantes.enregistrer(base, sid, "2026-09-08", heure, {cle: niveau})

    total = constantes.total_du_jour(base, sid, "2026-09-08", cle)
    assert total.volume_ml == 110          # 150 − 40, pas 40 + 90 + 150
    assert total.heures_comptees == 2


def test_un_bocal_vide_ne_perd_pas_ce_qu_il_contenait(base):
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="redon",
                              date_pose="2026-09-08")
    cle = constantes.cle_drain(drain)
    constantes.enregistrer(base, sid, "2026-09-08", 8, {cle: 100})
    constantes.enregistrer(base, sid, "2026-09-08", 9, {cle: 300},
                           sacs_jetes={cle})
    constantes.enregistrer(base, sid, "2026-09-08", 10, {cle: 50})

    total = constantes.total_du_jour(base, sid, "2026-09-08", cle)
    assert total.volume_ml == 250          # (300 − 100) + 50


def test_le_releve_de_l_infirmier_l_emporte_sur_le_report_du_medecin(base):
    """Le relevé horaire est une mesure ; le chiffre repris dans l'observation
    est une reprise. Sinon le volume changerait selon l'écran regardé."""
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    evolution = _service("evolution")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="redon",
                              date_pose="2026-09-08")
    cle_evolution = evolution.drains_du_jour(base, sid, "2026-09-08")[0]["cle"]
    evolution.enregistrer_elements(base, sid, "2026-09-08", {cle_evolution: 500})
    assert evolution.drains_du_jour(base, sid, "2026-09-08")[0]["valeur"] == 500

    cle = constantes.cle_drain(drain)
    constantes.enregistrer(base, sid, "2026-09-08", 8, {cle: 0})
    constantes.enregistrer(base, sid, "2026-09-08", 12, {cle: 180})
    ligne = evolution.drains_du_jour(base, sid, "2026-09-08")[0]
    assert ligne["valeur"] == 180
    assert ligne["releve_infirmier"] == 180


def test_sans_releve_horaire_le_chiffre_du_medecin_reste(base):
    """Un total vide se dit « complet » — il ne manque rien à rien. Il ne doit
    pas pour autant écraser la valeur du médecin par un blanc."""
    dispositifs = _service("dispositifs")
    evolution = _service("evolution")
    sid = _patient(base)
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose="2026-09-08")
    cle = evolution.drains_du_jour(base, sid, "2026-09-08")[0]["cle"]
    evolution.enregistrer_elements(base, sid, "2026-09-08", {cle: 320})
    ligne = evolution.drains_du_jour(base, sid, "2026-09-08")[0]
    assert ligne["valeur"] == 320
    assert ligne["releve_infirmier"] is None


def test_deux_redons_donnent_deux_lignes_distinctes_au_bilan(base):
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    evolution = _service("evolution")
    sid = _patient(base)
    premier = dispositifs.poser(base, sejour_id=sid, type_="redon",
                                site="Abdomen", date_pose="2026-09-08")
    second = dispositifs.poser(base, sejour_id=sid, type_="redon",
                               site="Abdomen", date_pose="2026-09-08")
    for identifiant, volume in ((premier, 90), (second, 410)):
        cle = constantes.cle_drain(identifiant)
        constantes.enregistrer(base, sid, "2026-09-08", 8, {cle: 0})
        constantes.enregistrer(base, sid, "2026-09-08", 14, {cle: volume})

    lignes = evolution.drains_du_jour(base, sid, "2026-09-08")
    par_nom = {l["libelle"]: l["valeur"] for l in lignes}
    assert par_nom == {"Redon (abdomen) 1": 90, "Redon (abdomen) 2": 410}

    bilan = evolution.bilan_hydrique(base, sid, "2026-09-08")
    assert bilan.drains_ml == 500
    assert "90" in bilan.texte_drains and "410" in bilan.texte_drains


def test_la_sonde_urinaire_n_est_pas_un_drain(base):
    """Son volume, c'est la diurèse — comptée à part. L'ajouter la compterait
    deux fois."""
    dispositifs = _service("dispositifs")
    evolution = _service("evolution")
    sid = _patient(base)
    dispositifs.poser(base, sejour_id=sid, type_="sonde_urinaire",
                      date_pose="2026-09-08")
    assert evolution.drains_du_jour(base, sid, "2026-09-08") == []


# --------------------------------------------------------------------------
# L'etat d'un drain thoracique : dans quoi il est branche, et s'il bulle
# --------------------------------------------------------------------------
# Un drain qui ne donne rien ne se lit pas de la meme facon selon qu'il est
# clampe — c'est attendu — ou en siphonnage, ou c'est peut-etre un drain
# bouche (demande du service, 11 septembre).

def test_les_modes_du_drain_thoracique_existent():
    codes = listes.codes(listes.ETATS_DRAIN_THORACIQUE)
    assert set(codes) == {"siphonnage", "aspiration", "clampe"}


def test_le_bullage_n_est_pas_un_mode():
    """Un drain peut buller en siphonnage comme en aspiration : le mettre
    dans la liste des modes obligerait a choisir entre les deux."""
    assert "bullage" not in listes.codes(listes.ETATS_DRAIN_THORACIQUE)


def test_le_mode_et_le_bullage_se_reunissent_et_se_relisent(base):
    constantes = _service("constantes")
    assert constantes.etat_drain("aspiration", True) == "aspiration+bullage"
    assert constantes.etat_drain("clampe", False) == "clampe"
    assert constantes.etat_drain(None, True) == "bullage"
    assert constantes.etat_drain(None, False) is None

    assert constantes.lire_etat_drain("aspiration+bullage") == ("aspiration", True)
    assert constantes.lire_etat_drain("clampe") == ("clampe", False)
    assert constantes.lire_etat_drain("bullage") == (None, True)
    assert constantes.lire_etat_drain(None) == (None, False)


def test_l_etat_se_releve_heure_par_heure(base):
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                              site="Droit", date_pose="2026-09-08")
    cle = constantes.cle_etat_drain(drain)
    constantes.enregistrer(base, sid, "2026-09-08", 8, {},
                           textes={cle: constantes.etat_drain("siphonnage", True)})
    constantes.enregistrer(base, sid, "2026-09-08", 14, {},
                           textes={cle: constantes.etat_drain("clampe", False)})

    etats = constantes.etats_du_jour(base, sid, "2026-09-08")
    assert etats[8][cle] == "siphonnage+bullage"
    assert etats[14][cle] == "clampe"


def test_l_etat_et_le_volume_cohabitent_sur_la_meme_heure(base):
    """Deux cles distinctes pour le meme drain, ecrites dans le meme geste."""
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                              date_pose="2026-09-08")
    constantes.enregistrer(
        base, sid, "2026-09-08", 8,
        {constantes.cle_drain(drain): 120},
        textes={constantes.cle_etat_drain(drain): "aspiration"},
    )
    assert constantes.du_jour(base, sid, "2026-09-08")[8][constantes.cle_drain(drain)] == 120
    assert constantes.etats_du_jour(base, sid, "2026-09-08")[8][
        constantes.cle_etat_drain(drain)] == "aspiration"


def test_un_etat_efface_disparait(base):
    """Une case videe efface la note, elle n'ecrit pas une chaine vide."""
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                              date_pose="2026-09-08")
    cle = constantes.cle_etat_drain(drain)
    constantes.enregistrer(base, sid, "2026-09-08", 8, {}, textes={cle: "clampe"})
    constantes.enregistrer(base, sid, "2026-09-08", 8, {}, textes={cle: None})
    assert constantes.etats_du_jour(base, sid, "2026-09-08") == {}


def test_l_etat_n_est_pas_un_recueil(base):
    """Il ne se totalise jamais : la moyenne de « clampe » et de
    « siphonnage » n'existe pas."""
    constantes = _service("constantes")
    assert constantes.est_recueil(constantes.cle_etat_drain("abc")) is False
    assert constantes.est_recueil(constantes.cle_drain("abc")) is True


def test_le_releve_d_etat_ne_perturbe_pas_le_total_du_drain(base):
    """Les deux cles se ressemblent : `drain:x` et `etat_drain:x`. Si la
    seconde etait comptee comme un niveau, elle casserait le total."""
    constantes = _service("constantes")
    dispositifs = _service("dispositifs")
    sid = _patient(base)
    drain = dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                              date_pose="2026-09-08")
    volume, etat = constantes.cle_drain(drain), constantes.cle_etat_drain(drain)
    constantes.enregistrer(base, sid, "2026-09-08", 8, {volume: 0},
                           textes={etat: "siphonnage"})
    constantes.enregistrer(base, sid, "2026-09-08", 16, {volume: 250},
                           textes={etat: "clampe"})
    assert constantes.total_du_jour(base, sid, "2026-09-08", volume).volume_ml == 250


def test_le_type_du_drain_remonte_pour_savoir_qui_a_un_etat(base):
    """Seul un drain thoracique est clampe ou en siphonnage. Poser la
    question a un redon lui ferait dire n'importe quoi."""
    dispositifs = _service("dispositifs")
    evolution = _service("evolution")
    sid = _patient(base)
    dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                      date_pose="2026-09-08")
    dispositifs.poser(base, sejour_id=sid, type_="redon", site="Abdomen",
                      date_pose="2026-09-08")
    types = {d["type"] for d in evolution.drains_du_jour(base, sid, "2026-09-08")}
    assert types == {"drain_thoracique", "redon"}
