-- =========================================================================
-- Logiciel de service — Réanimation polyvalente
-- Schéma de la base (SPEC §4, règles de conception §3)
--
--  * identifiants UUID en TEXT, jamais de numéro séquentiel  (règle 1)
--  * aucune suppression physique : colonne `supprime`        (règle 2)
--  * horodatage systématique cree_le / modifie_le / modifie_par (règle 3)
--  * séries temporelles en format long                       (règle 4)
--  * le texte est calculé, sauf le snapshot de pancarte       (règle 5)
--  * identité séparée des données cliniques                   (règle 6)
--  * trois états explicites là où l'absence est possible      (règle 7)
--
-- Dates et heures : texte ISO 8601 ('2026-09-01' ou '2026-09-01T08:30:00').
-- Booléens : INTEGER 0 / 1.
-- =========================================================================

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------------------
-- Métadonnées de la base
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
    cle    TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);

-- -------------------------------------------------------------------------
-- Utilisateurs (SPEC §1.2) — pas de droits différenciés en v1
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS utilisateur (
    id       TEXT PRIMARY KEY,
    nom      TEXT NOT NULL,
    role     TEXT NOT NULL,            -- interne / resident / senior
    actif    INTEGER NOT NULL DEFAULT 1,
    cree_le  TEXT NOT NULL,
    supprime INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_utilisateur_nom ON utilisateur(nom);

-- -------------------------------------------------------------------------
-- Identité (SPEC §4.1) — table séparée des données cliniques (règle 6)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patient (
    id                     TEXT PRIMARY KEY,
    matricule              TEXT NOT NULL,
    nom_affichage          TEXT NOT NULL,   -- « K. Abdelaziz »
    date_naissance         TEXT,            -- complète : permet l'âge et les tranches
    sexe                   TEXT NOT NULL DEFAULT 'non_renseigne',
    non_identifie          INTEGER NOT NULL DEFAULT 0,
    fusionne_vers          TEXT REFERENCES patient(id),  -- patient non identifié réuni au vrai dossier
    traitement_habituel    TEXT,            -- texte libre, un seul champ (SPEC §4.2)
    sans_antecedent_connu  INTEGER NOT NULL DEFAULT 0,
    -- identifiant d'étude stable, utilisé par l'export pseudonymisé (règle 8)
    identifiant_etude      TEXT NOT NULL,
    cree_le                TEXT NOT NULL,
    cree_par               TEXT REFERENCES utilisateur(id),
    modifie_le             TEXT,
    modifie_par            TEXT REFERENCES utilisateur(id),
    supprime               INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_matricule ON patient(matricule);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_etude ON patient(identifiant_etude);

-- -------------------------------------------------------------------------
-- Séjour (SPEC §4.1, §4.7)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sejour (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL REFERENCES patient(id),
    numero_sejour       INTEGER NOT NULL DEFAULT 1,
    date_admission      TEXT NOT NULL,
    lit_admission       INTEGER NOT NULL,          -- 1-12, figé
    provenance_type     TEXT,
    provenance_detail   TEXT,
    est_readmission     INTEGER NOT NULL DEFAULT 0,
    motif_readmission   TEXT,

    -- Question filtre : conditionne toute la suite de l'écran d'admission
    traumatique         INTEGER,                   -- NULL = non renseigné
    mecanisme           TEXT,
    mecanisme_detail    TEXT,

    -- Sortie (SPEC §4.7)
    date_sortie         TEXT,
    mode_sortie         TEXT,
    destination         TEXT,
    meme_etablissement  INTEGER,                   -- NULL = non renseigné
    complication_statut TEXT NOT NULL DEFAULT 'non_renseigne',
    complication_texte  TEXT,
    ordonnance_sortie   TEXT,
    consultation_externe TEXT,

    -- Devenir (SPEC §9.2) — deux champs distincts, question ouverte 5
    deces_reanimation   INTEGER,                   -- NULL = non renseigné
    statut_j28          TEXT,                      -- vivant / decede / perdu_de_vue
    date_statut_j28     TEXT,

    cree_le             TEXT NOT NULL,
    cree_par            TEXT REFERENCES utilisateur(id),
    modifie_le          TEXT,
    modifie_par         TEXT REFERENCES utilisateur(id),
    supprime            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sejour_patient ON sejour(patient_id);
CREATE INDEX IF NOT EXISTS idx_sejour_ouvert ON sejour(date_sortie, supprime);

-- Historique des changements de lit. Le lit d'admission reste dans `sejour`.
CREATE TABLE IF NOT EXISTS sejour_lit (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    lit         INTEGER NOT NULL,
    date_debut  TEXT NOT NULL,
    date_fin    TEXT,
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sejour_lit_sejour ON sejour_lit(sejour_id);

-- -------------------------------------------------------------------------
-- Antécédents (SPEC §4.2) — attachés au patient, pas au séjour
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS antecedent (
    id                    TEXT PRIMARY KEY,
    patient_id            TEXT NOT NULL REFERENCES patient(id),
    categorie             TEXT NOT NULL,    -- personnel / familial / chirurgical / allergie / habitude
    code                  TEXT,             -- code de la liste courte, si applicable
    libelle               TEXT NOT NULL,
    code_icd10            TEXT,
    precision             TEXT,
    quantification_valeur REAL,
    quantification_unite  TEXT,
    statut                TEXT NOT NULL DEFAULT 'present',  -- present / absent / non_renseigne
    cree_le               TEXT NOT NULL,
    cree_par              TEXT REFERENCES utilisateur(id),
    modifie_le            TEXT,
    modifie_par           TEXT REFERENCES utilisateur(id),
    supprime              INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_antecedent_patient ON antecedent(patient_id, supprime);

-- Conditions chroniques ANZICS (SPEC §9.5) — sept catégories + « aucune »
CREATE TABLE IF NOT EXISTS condition_chronique (
    id         TEXT PRIMARY KEY,
    sejour_id  TEXT NOT NULL REFERENCES sejour(id),
    code       TEXT NOT NULL,
    statut     TEXT NOT NULL DEFAULT 'non_renseigne',  -- present / absent / non_renseigne
    cree_le    TEXT NOT NULL,
    cree_par   TEXT REFERENCES utilisateur(id),
    supprime   INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_condition_sejour_code ON condition_chronique(sejour_id, code);

-- -------------------------------------------------------------------------
-- Motif d'admission (SPEC §4.3, §4.4)
-- -------------------------------------------------------------------------
-- Traumatique : multi-sélection de régions. Le statut « polytraumatisé » n'est
-- pas stocké — il se calcule (>= 2 régions), voir domaine/sejours.py.
CREATE TABLE IF NOT EXISTS sejour_region_trauma (
    id         TEXT PRIMARY KEY,
    sejour_id  TEXT NOT NULL REFERENCES sejour(id),
    region     TEXT NOT NULL,
    cree_le    TEXT NOT NULL,
    cree_par   TEXT REFERENCES utilisateur(id),
    supprime   INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_region_sejour ON sejour_region_trauma(sejour_id, region);

-- Non traumatique : un motif principal obligatoire + motifs associés.
-- `donnees` porte les précisions structurées du motif (porte d'entrée d'un
-- choc septique, surface brûlée, agent…) en JSON — ces champs varient d'un
-- motif à l'autre et n'ont pas à peupler la table de colonnes vides.
CREATE TABLE IF NOT EXISTS sejour_motif (
    id         TEXT PRIMARY KEY,
    sejour_id  TEXT NOT NULL REFERENCES sejour(id),
    code       TEXT NOT NULL,
    principal  INTEGER NOT NULL DEFAULT 0,
    texte      TEXT,
    donnees    TEXT,          -- JSON
    cree_le    TEXT NOT NULL,
    cree_par   TEXT REFERENCES utilisateur(id),
    supprime   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_motif_sejour ON sejour_motif(sejour_id, supprime);

-- -------------------------------------------------------------------------
-- Interventions chirurgicales (SPEC §4.6)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intervention (
    id                  TEXT PRIMARY KEY,
    sejour_id           TEXT NOT NULL REFERENCES sejour(id),
    date_acte           TEXT NOT NULL,
    geste               TEXT NOT NULL,
    geste_detail        TEXT,
    est_reprise         INTEGER NOT NULL DEFAULT 0,
    -- trois états, défaut « non renseigné » : demande initiale « sans
    -- complication par défaut » refusée, voir SPEC §4.6
    complication_statut TEXT NOT NULL DEFAULT 'non_renseigne',
    complication_texte  TEXT,
    cree_le             TEXT NOT NULL,
    cree_par            TEXT REFERENCES utilisateur(id),
    modifie_le          TEXT,
    modifie_par         TEXT REFERENCES utilisateur(id),
    supprime            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_intervention_sejour ON intervention(sejour_id, supprime);

-- -------------------------------------------------------------------------
-- PRESCRIPTION (SPEC §5) — cœur du logiciel
-- -------------------------------------------------------------------------
-- Une ligne n'est JAMAIS dupliquée pour le lendemain (décision v1.3). Elle
-- porte sa période d'activité (date_debut → date_arret) ; la pancarte d'un
-- jour donné est calculée par intersection avec cette période. C'est ce qui
-- rend le compteur de jours exact sans recopie et interdit deux versions
-- divergentes d'une même prescription.
CREATE TABLE IF NOT EXISTS prescription_ligne (
    id                 TEXT PRIMARY KEY,
    sejour_id          TEXT NOT NULL REFERENCES sejour(id),
    voie               TEXT NOT NULL,   -- PO / IV / PSE / SC / AEROSOL / SOINS / KINE / ENTREES
    sous_type          TEXT,            -- perfusion / nutrition_enterale / nutrition_parenterale
    produit            TEXT NOT NULL,
    dose               REAL,
    unite              TEXT,
    rythme             TEXT,
    horaires_override  TEXT,            -- « 6,12,18,24 » si le prescripteur a modifié
    condition_texte    TEXT,            -- « si T ≥ 38,5 °C »
    dilution           TEXT,            -- PSE : « 0,5 mg/cc »
    nb_ampoules        REAL,            -- affiché entre parenthèses pour les infirmiers
    vitesse            REAL,            -- cc/h (PSE et perfusions)
    volume_dilution    REAL,            -- mL par prise d'un IV, pour le bilan des entrées
    volume_24h         REAL,            -- mL/24 h (nutrition)
    additifs           TEXT,            -- « + 3 KCl + 2 NaCl »
    date_debut         TEXT NOT NULL,   -- détermine le compteur de jours
    duree_prevue_jours INTEGER,         -- nécessaire pour afficher « J7/7 »
    date_arret         TEXT,
    statut             TEXT NOT NULL DEFAULT 'active',  -- active / arretee
    motif_arret        TEXT,
    -- traçabilité d'origine si la ligne vient d'un protocole (SPEC §4.5)
    protocole_code     TEXT,
    protocole_version  TEXT,
    cree_le            TEXT NOT NULL,
    cree_par           TEXT REFERENCES utilisateur(id),   -- le prescripteur
    modifie_le         TEXT,
    modifie_par        TEXT REFERENCES utilisateur(id),
    supprime           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prescription_sejour ON prescription_ligne(sejour_id, supprime);
CREATE INDEX IF NOT EXISTS idx_prescription_periode ON prescription_ligne(sejour_id, date_debut, date_arret);

-- Une journée de pancarte. Créée par « Préparer la pancarte de demain ».
-- Elle ne contient pas les lignes de prescription (elles se calculent) mais
-- porte les bilans demandés pour ce jour et la trace de qui a préparé.
CREATE TABLE IF NOT EXISTS journee (
    id            TEXT PRIMARY KEY,
    sejour_id     TEXT NOT NULL REFERENCES sejour(id),
    date_jour     TEXT NOT NULL,
    preparee_le   TEXT,
    preparee_par  TEXT REFERENCES utilisateur(id),
    note          TEXT,
    cree_le       TEXT NOT NULL,
    cree_par      TEXT REFERENCES utilisateur(id),
    supprime      INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_journee_sejour_date ON journee(sejour_id, date_jour);

-- Bilans à demander pour le lendemain (SPEC §5.2 bis)
CREATE TABLE IF NOT EXISTS bilan_demande (
    id                 TEXT PRIMARY KEY,
    journee_id         TEXT NOT NULL REFERENCES journee(id),
    examen_code        TEXT NOT NULL,
    heure_prelevement  TEXT NOT NULL DEFAULT '06:00',
    cree_le            TEXT NOT NULL,
    cree_par           TEXT REFERENCES utilisateur(id),
    supprime           INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bilan_demande_unique ON bilan_demande(journee_id, examen_code);

-- Snapshot immuable d'une pancarte imprimée (exception à la règle 5).
-- Aucune mise à jour n'est permise sur cette table : on n'y ajoute que des
-- lignes, et une pancarte réimprimée reçoit un nouveau numéro de version.
CREATE TABLE IF NOT EXISTS pancarte_snapshot (
    id                 TEXT PRIMARY KEY,
    sejour_id          TEXT NOT NULL REFERENCES sejour(id),
    date_jour          TEXT NOT NULL,
    version            INTEGER NOT NULL,
    html               TEXT NOT NULL,
    format_page        TEXT NOT NULL,
    protocoles_version TEXT,
    imprime_le         TEXT NOT NULL,
    imprime_par        TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshot_unique
    ON pancarte_snapshot(sejour_id, date_jour, version);

-- Protocoles retenus pour un séjour (SPEC §4.5) — trace de ce qui a été
-- proposé et de la version du fichier au moment où il a été proposé.
CREATE TABLE IF NOT EXISTS protocole_applique (
    id                TEXT PRIMARY KEY,
    sejour_id         TEXT NOT NULL REFERENCES sejour(id),
    protocole_code    TEXT NOT NULL,
    protocole_version TEXT NOT NULL,
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_protocole_sejour ON protocole_applique(sejour_id);

-- -------------------------------------------------------------------------
-- EXPLORATIONS (SPEC §6) — valeurs chiffrées, format long (règle 4)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exploration (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    date_heure  TEXT NOT NULL,
    type        TEXT NOT NULL,
    conclusion  TEXT,
    operateur   TEXT,
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exploration_sejour ON exploration(sejour_id, date_heure);

CREATE TABLE IF NOT EXISTS exploration_valeur (
    id              TEXT PRIMARY KEY,
    exploration_id  TEXT NOT NULL REFERENCES exploration(id),
    cle             TEXT NOT NULL,
    valeur_num      REAL,
    valeur_texte    TEXT,
    unite           TEXT,
    supprime        INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_expl_valeur ON exploration_valeur(exploration_id, cle);

-- -------------------------------------------------------------------------
-- BILANS (SPEC §7) — bloc 4. Fichier HTML de saisie reçu (v1.5), intégré
-- directement : mêmes analytes, même format de texte généré.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bilan_resultat (
    id           TEXT PRIMARY KEY,
    sejour_id    TEXT NOT NULL REFERENCES sejour(id),
    date_heure   TEXT NOT NULL,
    analyte      TEXT NOT NULL,     -- 'hb', 'creatinine', 'crp'…
    valeur_num   REAL,
    valeur_texte TEXT,
    unite        TEXT,
    source       TEXT,              -- 'import_html' / 'saisie'
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bilan_sejour ON bilan_resultat(sejour_id, date_heure);
CREATE INDEX IF NOT EXISTS idx_bilan_analyte ON bilan_resultat(sejour_id, analyte, date_heure);

-- Gaz du sang : toujours groupé avec les paramètres ventilatoires (SPEC §7.3).
-- Le rapport P/F n'est pas stocké, il se calcule.
CREATE TABLE IF NOT EXISTS gaz_du_sang (
    id                TEXT PRIMARY KEY,
    sejour_id         TEXT NOT NULL REFERENCES sejour(id),
    date_heure        TEXT NOT NULL,
    ph                REAL,
    pao2              REAL,
    paco2             REAL,
    hco3              REAL,
    lactate           REAL,
    mode_ventilatoire TEXT,
    debit_o2          REAL,          -- L/min — Masque / Lunette seulement
    fio2              REAL,          -- en %
    pep               REAL,
    fr                REAL,
    spo2              REAL,          -- en %
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gds_sejour ON gaz_du_sang(sejour_id, date_heure);

CREATE TABLE IF NOT EXISTS microbiologie (
    id                TEXT PRIMARY KEY,
    sejour_id         TEXT NOT NULL REFERENCES sejour(id),
    date_prelevement  TEXT NOT NULL,
    type_prelevement  TEXT NOT NULL,
    resultat          TEXT NOT NULL DEFAULT 'en_cours',
    germe             TEXT,
    antibiogramme     TEXT,           -- texte libre en v1
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    modifie_le        TEXT,
    modifie_par       TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_micro_sejour ON microbiologie(sejour_id, date_prelevement);

-- -------------------------------------------------------------------------
-- ÉVOLUTION QUOTIDIENNE (SPEC §8)
-- -------------------------------------------------------------------------
-- Seule la partie rédigée par le médecin est stockée. L'en-tête, les
-- explorations, les bilans et le traitement sont générés à l'affichage.
CREATE TABLE IF NOT EXISTS evolution_jour (
    id                   TEXT PRIMARY KEY,
    sejour_id            TEXT NOT NULL REFERENCES sejour(id),
    date_jour            TEXT NOT NULL,
    plan_neurologique    TEXT,
    plan_respiratoire    TEXT,
    plan_hemodynamique   TEXT,
    plan_infectieux      TEXT,
    conduite             TEXT,
    cree_le              TEXT NOT NULL,
    cree_par             TEXT REFERENCES utilisateur(id),
    modifie_le           TEXT,
    modifie_par          TEXT REFERENCES utilisateur(id),
    supprime             INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evolution_unique ON evolution_jour(sejour_id, date_jour);

-- -------------------------------------------------------------------------
-- SOCLE DE RECHERCHE (SPEC §9.2, §9.5)
-- Tables créées mais aucune saisie imposée tant que le socle n'est pas validé
-- (questions ouvertes 1 à 5).
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ventilation_episode (
    id               TEXT PRIMARY KEY,
    sejour_id        TEXT NOT NULL REFERENCES sejour(id),
    date_intubation  TEXT NOT NULL,
    date_extubation  TEXT,
    mode_initial     TEXT,
    tracheotomie     INTEGER NOT NULL DEFAULT 0,
    cree_le          TEXT NOT NULL,
    cree_par         TEXT REFERENCES utilisateur(id),
    modifie_le       TEXT,
    modifie_par      TEXT REFERENCES utilisateur(id),
    supprime         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ventilation_sejour ON ventilation_episode(sejour_id);

CREATE TABLE IF NOT EXISTS epuration_episode (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    date_debut  TEXT NOT NULL,
    date_fin    TEXT,
    technique   TEXT,           -- hemodialyse / hemofiltration / autre
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_epuration_sejour ON epuration_episode(sejour_id);

CREATE TABLE IF NOT EXISTS infection_nosocomiale (
    id               TEXT PRIMARY KEY,
    sejour_id        TEXT NOT NULL REFERENCES sejour(id),
    type             TEXT NOT NULL,    -- pavm / ilc / iu / iss / autre
    date_diagnostic  TEXT NOT NULL,
    germe            TEXT,
    commentaire      TEXT,
    cree_le          TEXT NOT NULL,
    cree_par         TEXT REFERENCES utilisateur(id),
    supprime         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_infection_sejour ON infection_nosocomiale(sejour_id);

-- Scores quotidiens en format long : une ligne par score et par jour (règle 4)
CREATE TABLE IF NOT EXISTS score_quotidien (
    id         TEXT PRIMARY KEY,
    sejour_id  TEXT NOT NULL REFERENCES sejour(id),
    date_jour  TEXT NOT NULL,
    score      TEXT NOT NULL,     -- 'sofa', 'igs2'…
    valeur     REAL,
    detail     TEXT,              -- JSON des sous-scores
    cree_le    TEXT NOT NULL,
    cree_par   TEXT REFERENCES utilisateur(id),
    supprime   INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_score_unique ON score_quotidien(sejour_id, date_jour, score);

-- Variables d'admission alignées ANZICS (SPEC §9.5) : valeurs d'admission,
-- pas pires valeurs des 24 h — simplification assumée, à mentionner dans
-- toute publication.
CREATE TABLE IF NOT EXISTS evaluation_admission (
    id                     TEXT PRIMARY KEY,
    sejour_id              TEXT NOT NULL REFERENCES sejour(id),
    glasgow_oeil           INTEGER,
    glasgow_verbal         INTEGER,
    glasgow_moteur         INTEGER,
    glasgow_non_evaluable  INTEGER NOT NULL DEFAULT 0,   -- patient sédaté
    fragilite              INTEGER,       -- score de fragilité clinique 1-9
    temperature_min        REAL,
    temperature_max        REAL,
    fc_min                 REAL,
    fc_max                 REAL,
    pas_min                REAL,
    pas_max                REAL,
    pam_min                REAL,
    pam_max                REAL,
    fr_min                 REAL,
    fr_max                 REAL,
    diurese_24h            REAL,          -- mL
    ventilation_invasive_j1 INTEGER,      -- NULL = non renseigné
    cree_le                TEXT NOT NULL,
    cree_par               TEXT REFERENCES utilisateur(id),
    modifie_le             TEXT,
    modifie_par            TEXT REFERENCES utilisateur(id),
    supprime               INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluation_sejour ON evaluation_admission(sejour_id);

-- -------------------------------------------------------------------------
-- Journal des modifications (SPEC §10, bloc 7)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journal (
    id             TEXT PRIMARY KEY,
    date_heure     TEXT NOT NULL,
    utilisateur_id TEXT REFERENCES utilisateur(id),
    table_cible    TEXT NOT NULL,
    ligne_id       TEXT,
    action         TEXT NOT NULL,   -- creation / modification / arret / impression / sortie
    details        TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date_heure);
CREATE INDEX IF NOT EXISTS idx_journal_ligne ON journal(table_cible, ligne_id);

-- Trace des sauvegardes automatiques (SPEC §2.2)
CREATE TABLE IF NOT EXISTS sauvegarde (
    id          TEXT PRIMARY KEY,
    date_heure  TEXT NOT NULL,
    fichier     TEXT NOT NULL,
    taille      INTEGER,
    motif       TEXT NOT NULL    -- ouverture / periodique / fermeture / manuelle
);
CREATE INDEX IF NOT EXISTS idx_sauvegarde_date ON sauvegarde(date_heure);
