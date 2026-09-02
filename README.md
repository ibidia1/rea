# Logiciel de service — Réanimation polyvalente

Voir **[SPEC.md](SPEC.md)** — c'est le document de référence du projet,
à jour à chaque session de travail.

## État actuel

**v1 utilisable** : Lits, Admission, Prescrit (toutes voies, bilan hydrique,
impression), Bilans (saisie, courbes de cinétique, texte généré), Évolution
(reprend le bilan du jour), Sortie. Voir le journal des versions dans
SPEC.md pour le détail exact de ce qui est fait et ce qui ne l'est pas — en
particulier la mise en page de la pancarte imprimée est **provisoire** (le
PDF réel du prescrit n'a pas encore été fourni), et les écrans Explorations
et Statistiques ne sont pas commencés.

## Installation (poste de développement)

```bash
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

## Lancer l'application

```bash
streamlit run rea_app.py
```

Ouvre `http://localhost:8501`. Choisir ou créer un utilisateur, puis
cliquer sur un lit libre pour admettre un patient.

## Lancer les tests

```bash
python -m pytest
```

## Emplacement des données

Par défaut : `~/ReaService` (Linux/Mac) ou `C:\ReaService` (Windows), voir
`rea/config.py`. Surchargeable avec la variable d'environnement `REA_DIR`
(utilisée par les tests pour ne jamais toucher aux données réelles).
