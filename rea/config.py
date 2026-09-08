"""Configuration du poste.

Tout ce qui peut changer d'un poste à l'autre ou d'une décision de service à
l'autre est ici, et nulle part ailleurs.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Emplacement des données (SPEC §2.2)
# --------------------------------------------------------------------------
# Sur le poste du service (Windows) : C:\ReaService
# Ailleurs (poste de développement) : ~/ReaService
# Surchargeable par la variable d'environnement REA_DIR, ce dont se servent
# les tests.

def _racine_par_defaut() -> Path:
    if os.name == "nt":
        return Path("C:/ReaService")
    return Path.home() / "ReaService"


RACINE = Path(os.environ.get("REA_DIR") or _racine_par_defaut())
DOSSIER_DONNEES = RACINE / "donnees"
DOSSIER_SAUVEGARDES = RACINE / "sauvegardes"
DOSSIER_EXPORTS = RACINE / "exports"
DOSSIER_PANCARTES = RACINE / "pancartes"
FICHIER_BASE = DOSSIER_DONNEES / "rea.db"

# Dossier des protocoles, livré avec le code (versionné, signé — SPEC §4.5)
DOSSIER_PROTOCOLES = Path(__file__).resolve().parent.parent / "protocoles"

# --------------------------------------------------------------------------
# Réseau et authentification (§2.4 — contraintes d'architecture)
# --------------------------------------------------------------------------
# ÉTAT ACTUEL : un seul poste Windows, celui du DMI, sans réseau ni internet.
# Le logiciel n'écoute donc que sur la boucle locale : rien de ce dossier ne
# doit être joignable depuis une autre machine. Sans cette ligne, Streamlit
# écoute sur toutes les interfaces — le jour où le poste touche le réseau de
# l'hôpital, la base entière devient lisible sans mot de passe.
#
# ÉVOLUTION POSSIBLE, NON DÉCIDÉE : postes du service via LAN. Ce jour-là,
# HOTE passe à "0.0.0.0" et AUTH_REQUISE à True — les deux ensemble, jamais
# l'un sans l'autre.
HOTE = "127.0.0.1"
PORT = 8501
AUTH_REQUISE = False

# --------------------------------------------------------------------------
# Sauvegardes (SPEC §2.2)
# --------------------------------------------------------------------------
INTERVALLE_SAUVEGARDE_MINUTES = 15
# Nombre de sauvegardes conservées avant rotation. Une base de service pèse
# quelques mégaoctets : garder large ne coûte rien.
SAUVEGARDES_CONSERVEES = 200

# --------------------------------------------------------------------------
# Service (SPEC §1.1)
# --------------------------------------------------------------------------
NB_LITS = 12
# Chambre 1 → lits 1-4, chambre 2 → lits 5-8, chambre 3 → lits 9-12.
LITS_PAR_CHAMBRE = 4


def chambre_du_lit(lit: int) -> int:
    """Numéro de chambre d'un lit. Reste juste si le service s'agrandit."""
    return (lit - 1) // LITS_PAR_CHAMBRE + 1


# --------------------------------------------------------------------------
# Impression (SPEC §2.2)
# --------------------------------------------------------------------------
# « A4 portrait » aujourd'hui. Le jour où l'imprimante A3 arrive, une seule
# ligne change ici — la mise en page de la pancarte suit toute seule.
FORMAT_PAGE = "A4 portrait"
FORMATS_PAGE_POSSIBLES = ("A4 portrait", "A4 landscape", "A3 landscape")

# --------------------------------------------------------------------------
# Horaires d'administration (SPEC §5.3 — question 6, tranchée en v1.3)
# --------------------------------------------------------------------------
# La journée du service commence à 8 h, pas à minuit : la relève du matin
# ouvre la feuille, et la grille horaire imprimée suit cet ordre (8 h → 7 h le
# lendemain). C'est aussi la fenêtre dans laquelle se rangent les changements
# de vitesse d'une seringue : un réglage à 2 h du matin appartient à la
# journée ouverte la veille à 8 h, pas à celle qui commence six heures plus
# tard.
HEURE_DEBUT_JOURNEE = 8

# ×4/j et ×6/j sont calés sur minuit plutôt que sur 8 h : les relèves du
# service tombent ainsi sur des heures rondes. À contre-valider par un senior ;
# ces horaires restent modifiables ligne par ligne dans l'écran Prescrit.
HORAIRES_PAR_RYTHME: dict[str, tuple[int, ...]] = {
    "x1/j": (8,),
    "x2/j": (8, 20),
    "x3/j": (8, 16, 24),
    "x4/j": (6, 12, 18, 24),
    "x6/j": (4, 8, 12, 16, 20, 24),
    "1j/2": (8,),
    "continu": (),
    "conditionnel": (),
}

# --------------------------------------------------------------------------
# Texte généré (SPEC §8.2 — test de collage dans le DMI à faire)
# --------------------------------------------------------------------------
# Passer à False si le DMI abîme les indices Unicode : tout le texte généré
# sort alors en PaO2, PaCO2, HCO3-.
SYMBOLES_UNICODE = True

# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis)
# --------------------------------------------------------------------------
HEURE_PRELEVEMENT_DEFAUT = "08:00"
