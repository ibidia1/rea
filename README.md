# Logiciel de service — Réanimation polyvalente

Voir **[SPEC.md](SPEC.md)** — c'est le document de référence du projet,
à jour à chaque session de travail.

## État actuel

Fondations en cours (bloc 0 fait, bloc 1 en cours). **Il n'y a pas encore
d'interface utilisable.** Voir le journal des versions dans SPEC.md pour le
détail exact de ce qui est fait.

## Installation (poste de développement)

```bash
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

## Lancer les tests

```bash
python -m pytest
```

## Emplacement des données

Par défaut : `~/ReaService` (Linux/Mac) ou `C:\ReaService` (Windows), voir
`rea/config.py`. Surchargeable avec la variable d'environnement `REA_DIR`
(utilisée par les tests pour ne jamais toucher aux données réelles).
