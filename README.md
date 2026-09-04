# Logiciel de service — Réanimation polyvalente

Voir **[SPEC.md](SPEC.md)** — c'est le document de référence du projet,
à jour à chaque session de travail.

## État actuel

**v2.1** — tous les blocs codables de la feuille de route sont faits, et la
feuille imprimée est celle du service (maquette A3 de Kairouan, dans
`modeles/` : c'est un fichier, il se remplace sans reprogrammer).

*Soin quotidien* : Lits, Admission, Prescrit (toutes voies, bilan hydrique,
impression), Explorations et actes (dispositifs invasifs avec compteurs de
jours calculés), Bilans (saisie, cinétique, microbiologie, texte généré),
Évolution (check-list FAST HUG, rappels, scores, quatre plans), Sortie.

*Analyse* : écran **Recherche** — cohortes, tableau descriptif STROBE, taux
d'infections liées aux dispositifs, consommation d'antibiotiques, export
pseudonymisé avec dictionnaire des données, gel de base.

*Administration* : sauvegardes et **restauration**, journal d'audit
consultable, version de chaque référentiel, de chaque protocole et de chaque
jeu de règles.

Les listes codées (`referentiels/`), les règles d'aide et les barèmes de score
(`regles/`) sont des **fichiers JSON versionnés** : les modifier ne demande pas
de reprogrammer le logiciel.

### Ce qui reste, et qui ne dépend pas du développement

- **à faire valider par un senior** : bornes de normalité des bilans, barème
  IGS II, seuils des rappels, correspondances LOINC — tout est marqué non
  validé à l'écran ;
- **à compléter depuis leur source officielle** : la CIM-10 (58 codes de
  démarrage seulement) et la table des DDD de l'OMS ;
- le dossier de protection des données et le test sur patients réels.

Le détail exact figure dans le journal des versions de SPEC.md et dans
l'audit §10 de FEUILLE_DE_ROUTE.md.

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
