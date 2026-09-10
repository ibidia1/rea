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
--
-- -------------------------------------------------------------------------
-- Traçabilité (§2.4, invariant 1) — aucune hypothèse « un seul utilisateur »
-- -------------------------------------------------------------------------
-- Toute table modifiable porte les six mêmes colonnes :
--
--     version  cree_le  cree_par  modifie_le  modifie_par  supprime
--
-- `version` part à 1 et s'incrémente à chaque écriture (rea/db.py). Personne
-- ne la lit encore : elle est là pour que le jour où deux postes écrivent en
-- même temps, détecter le conflit ne demande pas une migration sur des
-- données cliniques réelles. C'est le moment où elle est bon marché.
--
-- Quatre tables en sont exemptées, chacune pour sa raison :
--   meta               configuration clé/valeur, pas une donnée clinique
--   pancarte_snapshot  instantané figé, jamais modifié — et sa colonne
--                      `version` désigne déjà le numéro d'impression
--                      (v1, v2 d'une même feuille), un tout autre sens
--   journal            journal d'audit : ni modifié, ni supprimé, jamais
--   sauvegarde         registre des sauvegardes, tenu par le programme
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
    id          TEXT PRIMARY KEY,
    nom         TEXT NOT NULL,
    role        TEXT NOT NULL,            -- interne / resident / senior
    actif       INTEGER NOT NULL DEFAULT 1,
    -- Vide aujourd'hui : un seul poste, un seul utilisateur à la fois, aucune
    -- authentification (config.AUTH_REQUISE = False). La colonne existe pour
    -- que le jour du multi-postes ne demande pas une migration sur des données
    -- cliniques déjà là (§2.4 — évolutions possibles, non décidées).
    pin         TEXT,
    -- Pour joindre la personne sans faire le tour des chambres : le médecin
    -- qui prescrit voit qui s'occupe du patient, et son numéro (demande du
    -- service, 10 septembre).
    telephone   TEXT,
    cree_le     TEXT NOT NULL,
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    cree_par    TEXT REFERENCES utilisateur(id),
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_utilisateur_nom ON utilisateur(nom);

-- -------------------------------------------------------------------------
-- Identité (SPEC §4.1) — table séparée des données cliniques (règle 6)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patient (
    id                    TEXT PRIMARY KEY,
    matricule             TEXT NOT NULL,
    nom_affichage         TEXT NOT NULL,   -- « K. Abdelaziz »
    date_naissance        TEXT,            -- complète : permet l'âge et les tranches
    sexe                  TEXT NOT NULL DEFAULT 'non_renseigne',
    non_identifie         INTEGER NOT NULL DEFAULT 0,
    fusionne_vers         TEXT REFERENCES patient(id),  -- patient non identifié réuni au vrai dossier
    traitement_habituel   TEXT,            -- texte libre, un seul champ (SPEC §4.2)
    sans_antecedent_connu INTEGER NOT NULL DEFAULT 0,
    -- Groupe sanguin : propriété de la personne, pas du séjour — il ne
    -- change pas d'une admission à l'autre et n'a pas à être resaisi.
    groupe_sanguin        TEXT,
    -- identifiant d'étude stable, utilisé par l'export pseudonymisé (règle 8)
    identifiant_etude     TEXT NOT NULL,
    cree_le               TEXT NOT NULL,
    cree_par              TEXT REFERENCES utilisateur(id),
    modifie_le            TEXT,
    modifie_par           TEXT REFERENCES utilisateur(id),
    supprime              INTEGER NOT NULL DEFAULT 0,
    version               INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_matricule ON patient(matricule);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_etude ON patient(identifiant_etude);

-- -------------------------------------------------------------------------
-- Séjour (SPEC §4.1, §4.7)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sejour (
    id                     TEXT PRIMARY KEY,
    patient_id             TEXT NOT NULL REFERENCES patient(id),
    numero_sejour          INTEGER NOT NULL DEFAULT 1,
    date_admission         TEXT NOT NULL,
    lit_admission          INTEGER NOT NULL,          -- 1-12, figé
    provenance_type        TEXT,
    provenance_detail      TEXT,
    est_readmission        INTEGER NOT NULL DEFAULT 0,
    -- Poids et taille à l'admission. Le poids est ce qui rend la clairance de
    -- la créatinine calculable (Cockcroft-Gault) ; sans lui, aucune formule
    -- pondérale n'est possible a posteriori.
    poids_kg               REAL,
    taille_cm              REAL,
    -- Créatinine antérieure connue, en µmol/L. Sans elle, la définition KDIGO
    -- de l'insuffisance rénale aiguë est incalculable a posteriori
    -- (feuille de route §5, exploitée au bloc 15).
    creatinine_base        REAL,
    motif_readmission      TEXT,
    -- Deux variables de l'IGS II qu'aucune autre donnée ne permet de
    -- reconstituer après coup : le type d'admission (une chirurgie programmée
    -- ne pèse pas le même poids qu'une admission médicale) et la maladie
    -- chronique au sens du score, dont les trois catégories ne recouvrent pas
    -- celles des conditions chroniques ANZICS saisies par ailleurs.
    type_admission         TEXT,
    maladie_chronique_igs2 TEXT,
    -- Glasgow à l'arrivée. Facteur pronostique majeur du traumatisé crânien,
    -- et la seule valeur neurologique qu'on ne peut plus reconstituer une fois
    -- le patient sédaté : à J3 sous midazolam, personne ne sait plus s'il est
    -- arrivé à 15 ou à 6. Elle a sa case sur la feuille imprimée, sous le
    -- transport (demande du service, 8 septembre).
    glasgow_initial        INTEGER,
    -- Diagnostic principal codé CIM-10 (bloc 12). Sur le séjour et non sur le
    -- motif : un séjour traumatique n'a pas de ligne de motif, et il doit
    -- pouvoir être codé comme les autres.
    code_icd10             TEXT,

    -- Question filtre : conditionne toute la suite de l'écran d'admission
    traumatique            INTEGER,                   -- NULL = non renseigné
    mecanisme              TEXT,
    mecanisme_detail       TEXT,

    -- Sortie (SPEC §4.7)
    date_sortie            TEXT,
    mode_sortie            TEXT,
    destination            TEXT,
    meme_etablissement     INTEGER,                   -- NULL = non renseigné
    complication_statut    TEXT NOT NULL DEFAULT 'non_renseigne',
    complication_texte     TEXT,
    ordonnance_sortie      TEXT,
    consultation_externe   TEXT,

    -- Devenir (SPEC §9.2) — deux champs distincts, question ouverte 5
    deces_reanimation      INTEGER,                   -- NULL = non renseigné
    statut_j28             TEXT,                      -- vivant / decede / perdu_de_vue
    date_statut_j28        TEXT,

    cree_le                TEXT NOT NULL,
    cree_par               TEXT REFERENCES utilisateur(id),
    modifie_le             TEXT,
    modifie_par            TEXT REFERENCES utilisateur(id),
    supprime               INTEGER NOT NULL DEFAULT 0,
    version                INTEGER NOT NULL DEFAULT 1
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
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
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
    supprime              INTEGER NOT NULL DEFAULT 0,
    version               INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_antecedent_patient ON antecedent(patient_id, supprime);

-- Conditions chroniques ANZICS (SPEC §9.5) — sept catégories + « aucune »
CREATE TABLE IF NOT EXISTS condition_chronique (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    code        TEXT NOT NULL,
    statut      TEXT NOT NULL DEFAULT 'non_renseigne',  -- present / absent / non_renseigne
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_condition_sejour_code ON condition_chronique(sejour_id, code);

-- -------------------------------------------------------------------------
-- Motif d'admission (SPEC §4.3, §4.4)
-- -------------------------------------------------------------------------
-- Traumatique : multi-sélection de régions. Le statut « polytraumatisé » n'est
-- pas stocké — il se calcule (>= 2 régions), voir domaine/sejours.py.
CREATE TABLE IF NOT EXISTS sejour_region_trauma (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    region      TEXT NOT NULL,
    -- Commentaire libre sur la lésion réelle (ex. « hématome extra-dural
    -- droit avec engagement temporal / embarrure pariétale ») : la région
    -- seule ne dit rien de la gravité ni du geste attendu.
    precision   TEXT,
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_region_sejour ON sejour_region_trauma(sejour_id, region);

-- Non traumatique : un motif principal obligatoire + motifs associés.
-- `donnees` porte les précisions structurées du motif (porte d'entrée d'un
-- choc septique, surface brûlée, agent…) en JSON — ces champs varient d'un
-- motif à l'autre et n'ont pas à peupler la table de colonnes vides.
CREATE TABLE IF NOT EXISTS sejour_motif (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    code        TEXT NOT NULL,
    principal   INTEGER NOT NULL DEFAULT 0,
    texte       TEXT,
    donnees     TEXT,          -- JSON
    code_icd10  TEXT,          -- posé tôt, exploité au bloc 17
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
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
    supprime            INTEGER NOT NULL DEFAULT 0,
    version             INTEGER NOT NULL DEFAULT 1
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
    -- Code ATC (OMS). Posé dès maintenant même s'il reste vide : sans lui, la
    -- consommation antibiotique en DDD pour 1 000 jours-patients demanderait de
    -- recoder des milliers de lignes à la main (feuille de route §5).
    code_atc           TEXT,
    -- Posologie À L'INTRODUCTION, écrite une fois et jamais remise à jour.
    -- Ce qui s'applique un jour donné se lit dans `prescription_posologie`,
    -- qui contient cette première version et celles qui l'ont suivie. Garder
    -- ces colonnes permet de relire ce qui a été prescrit au départ sans
    -- reconstituer l'historique, et à une base ancienne de rester lisible.
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
    -- L'indication fait partie de l'identité de l'épisode : le même produit
    -- redonné pour autre chose est un autre traitement, et sa durée se compte
    -- à part.
    indication         TEXT,
    date_debut         TEXT NOT NULL,   -- début de l'épisode : porte le compteur J{n}
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
    supprime           INTEGER NOT NULL DEFAULT 0,
    version            INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_prescription_sejour ON prescription_ligne(sejour_id, supprime);
CREATE INDEX IF NOT EXISTS idx_prescription_periode ON prescription_ligne(sejour_id, date_debut, date_arret);

-- Les versions successives de posologie d'un même traitement (SPEC §5.1).
--
-- Deux niveaux, et il faut les deux. `prescription_ligne` est l'ÉPISODE de
-- traitement : le produit, son indication, sa date de début. C'est lui qui
-- porte le compteur J{n} et la durée d'antibiothérapie. Cette table porte les
-- VERSIONS de posologie : dose, rythme, dilution, vitesse, à partir de quand.
--
-- Sans cette séparation, un Tienam 1 g × 3/j passé à 500 mg × 3/j à J4 laissait
-- le choix entre deux erreurs : modifier la ligne et perdre la posologie
-- initiale, ou en créer une seconde et faire repartir le compteur à J1 — alors
-- que l'antibiothérapie court depuis la première dose. La durée de traitement
-- était fausse dans les deux cas, et c'est elle qu'on rend au comité des
-- infections (demande du service, 8 septembre).
--
-- Il n'y a pas de `date_fin` : une version vaut jusqu'à ce que la suivante
-- commence. Une date de fin stockée à côté de la date de début de la suivante,
-- c'est deux façons de dire la même chose, donc tôt ou tard deux réponses
-- différentes à la même question.
CREATE TABLE IF NOT EXISTS prescription_posologie (
    id                 TEXT PRIMARY KEY,
    ligne_id           TEXT NOT NULL REFERENCES prescription_ligne(id),
    date_debut         TEXT NOT NULL,   -- premier jour où cette posologie s'applique
    dose               REAL,
    unite              TEXT,
    rythme             TEXT,
    horaires_override  TEXT,
    condition_texte    TEXT,
    dilution           TEXT,            -- PSE : « 0,5 mg/cc »
    nb_ampoules        REAL,
    vitesse            REAL,            -- cc/h au départ ; la suite est dans vitesse_reglage
    volume_dilution    REAL,
    volume_24h         REAL,
    additifs           TEXT,
    motif_changement   TEXT,            -- « adaptation à la fonction rénale »
    cree_le            TEXT NOT NULL,
    cree_par           TEXT REFERENCES utilisateur(id),
    modifie_le         TEXT,
    modifie_par        TEXT REFERENCES utilisateur(id),
    supprime           INTEGER NOT NULL DEFAULT 0,
    version            INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_posologie_ligne
    ON prescription_posologie(ligne_id, date_debut);

-- Les changements de vitesse d'une seringue ou d'une perfusion.
--
-- Une vitesse n'est pas une donnée figée : on part à 25 cc/h et on descend à
-- 15 à 16 h. La ligne de prescription porte la vitesse de départ ; cette table
-- porte la suite des réglages, horodatés, et c'est elle que la feuille imprime
-- heure par heure (demande du service, 8 septembre).
--
-- `cible` désigne ce qui coule : une ligne de prescription (noradrénaline en
-- P.S.E.) ou un dispositif (la sédation, posée dans l'écran des actes et
-- reportée dans le bloc P.S.E.). Deux origines, une seule façon de lire la
-- vitesse — sans quoi la sédation, justement celle qu'on allège tous les
-- jours, serait la seule à ne pas pouvoir être suivie.
CREATE TABLE IF NOT EXISTS vitesse_reglage (
    id          TEXT PRIMARY KEY,
    cible       TEXT NOT NULL,   -- prescription_ligne / dispositif
    cible_id    TEXT NOT NULL,
    date_heure  TEXT NOT NULL,   -- « 2026-09-08T16:00 »
    vitesse     REAL NOT NULL,   -- cc/h
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_vitesse_cible
    ON vitesse_reglage(cible, cible_id, date_heure);

-- Une journée de pancarte. Créée par « Préparer la pancarte de demain ».
-- Elle ne contient pas les lignes de prescription (elles se calculent) mais
-- porte les bilans demandés pour ce jour et la trace de qui a préparé.
CREATE TABLE IF NOT EXISTS journee (
    id           TEXT PRIMARY KEY,
    sejour_id    TEXT NOT NULL REFERENCES sejour(id),
    date_jour    TEXT NOT NULL,
    preparee_le  TEXT,
    preparee_par TEXT REFERENCES utilisateur(id),
    -- Un pas de plus que « préparée » : quelqu'un a relu la pancarte
    -- reconduite avant qu'elle ne devienne imprimable (demande du service).
    validee_le   TEXT,
    validee_par  TEXT REFERENCES utilisateur(id),
    note         TEXT,
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1,
    modifie_le   TEXT,
    modifie_par  TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_journee_sejour_date ON journee(sejour_id, date_jour);

-- Bilans à demander pour le lendemain (SPEC §5.2 bis)
CREATE TABLE IF NOT EXISTS bilan_demande (
    id                TEXT PRIMARY KEY,
    journee_id        TEXT NOT NULL REFERENCES journee(id),
    examen_code       TEXT NOT NULL,
    heure_prelevement TEXT NOT NULL DEFAULT '06:00',
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 1,
    modifie_le        TEXT,
    modifie_par       TEXT REFERENCES utilisateur(id)
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
    supprime          INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 1,
    modifie_le        TEXT,
    modifie_par       TEXT REFERENCES utilisateur(id)
);
CREATE INDEX IF NOT EXISTS idx_protocole_sejour ON protocole_applique(sejour_id);

-- -------------------------------------------------------------------------
-- EXPLORATIONS (SPEC §6) — valeurs chiffrées, format long (règle 4)
-- -------------------------------------------------------------------------
-- Les avis demandés aux autres spécialités (SPEC §7).
--
-- Un avis de neurochirurgie ne se résume pas : « refaire la TDM à 48 h » est
-- une consigne datée et signée, et c'est sur elle qu'on décide trois jours
-- plus tard. Écrit dans le texte libre du plan infectieux, il disparaissait à
-- la première réécriture de ce plan — et personne ne savait plus qui avait dit
-- quoi, ni quand (demande du service, 8 septembre).
--
-- Un avis n'annule jamais le précédent, même de la même spécialité : c'est la
-- suite des avis qui raconte l'évolution d'une décision chirurgicale, et le
-- second ne se comprend souvent qu'à la lumière du premier.
-- Les analytes que le service dose et que le catalogue ne connaît pas (§8).
--
-- Le catalogue de biologie (rea/analytes.py) est du code : y ajouter la
-- troponine demande une nouvelle version du logiciel. Un service qui se met à
-- doser quelque chose ne peut pas attendre ça — il le noterait dans un
-- commentaire libre, où le résultat ne se compare pas d'un jour à l'autre et
-- ne sort dans aucune statistique (demande du service, 9 septembre).
--
-- Ici et non dans `referentiels/` : ce sont des données du service, pas du
-- logiciel. Elles sont sauvegardées et restaurées avec la base, alors qu'un
-- fichier de référentiel réécrit à l'exécution cesserait d'être versionné.
CREATE TABLE IF NOT EXISTS analyte_local (
    id           TEXT PRIMARY KEY,
    code         TEXT NOT NULL UNIQUE,   -- stable : c'est lui qui est écrit sur chaque résultat
    libelle      TEXT NOT NULL,
    unite        TEXT,
    borne_basse  REAL,
    borne_haute  REAL,
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    modifie_le   TEXT,
    modifie_par  TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS avis_specialise (
    id           TEXT PRIMARY KEY,
    sejour_id    TEXT NOT NULL REFERENCES sejour(id),
    date_avis    TEXT NOT NULL,
    specialite   TEXT NOT NULL,     -- referentiels/specialites_avis.json
    nom          TEXT,              -- « Dr X »
    grade        TEXT,              -- senior / resident
    texte        TEXT NOT NULL,
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    modifie_le   TEXT,
    modifie_par  TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_avis_sejour ON avis_specialise(sejour_id, date_avis);

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
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_exploration_sejour ON exploration(sejour_id, date_heure);

CREATE TABLE IF NOT EXISTS exploration_valeur (
    id             TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL REFERENCES exploration(id),
    cle            TEXT NOT NULL,
    valeur_num     REAL,
    valeur_texte   TEXT,
    unite          TEXT,
    supprime       INTEGER NOT NULL DEFAULT 0,
    version        INTEGER NOT NULL DEFAULT 1,
    cree_le        TEXT NOT NULL,
    cree_par       TEXT REFERENCES utilisateur(id),
    modifie_le     TEXT,
    modifie_par    TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_expl_valeur ON exploration_valeur(exploration_id, cle);

-- -------------------------------------------------------------------------
-- BILANS (SPEC §7) — bloc 4. Fichier HTML de saisie reçu (v1.5), intégré
-- directement : mêmes analytes, même format de texte généré.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bilan_resultat (
    id            TEXT PRIMARY KEY,
    sejour_id     TEXT NOT NULL REFERENCES sejour(id),
    date_heure    TEXT NOT NULL,
    analyte       TEXT NOT NULL,     -- 'hb', 'creatinine', 'crp'…
    valeur_num    REAL,
    valeur_texte  TEXT,
    unite         TEXT,              -- unité affichée, telle que saisie
    -- Codes standards, remplis depuis le catalogue au moment de
    -- l'enregistrement (feuille de route §5). Une unité UCUM normalisée est ce
    -- qui empêche de confondre µmol/L et mg/L à l'analyse.
    code_loinc    TEXT,
    unite_ucum    TEXT,
    -- Valeur enregistrée malgré un avertissement de cohérence (bloc 4).
    saisie_forcee INTEGER NOT NULL DEFAULT 0,
    source        TEXT,              -- 'import_html' / 'saisie'
    cree_le       TEXT NOT NULL,
    cree_par      TEXT REFERENCES utilisateur(id),
    supprime      INTEGER NOT NULL DEFAULT 0,
    version       INTEGER NOT NULL DEFAULT 1,
    modifie_le    TEXT,
    modifie_par   TEXT REFERENCES utilisateur(id)
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
    sao2              REAL,          -- en % — saturation artérielle du gaz, distincte du SpO2 continu
    vt                REAL,          -- volume courant, mL
    ai                REAL,          -- aide inspiratoire, cmH2O
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 1,
    modifie_le        TEXT,
    modifie_par       TEXT REFERENCES utilisateur(id)
);
CREATE INDEX IF NOT EXISTS idx_gds_sejour ON gaz_du_sang(sejour_id, date_heure);

CREATE TABLE IF NOT EXISTS microbiologie (
    id               TEXT PRIMARY KEY,
    sejour_id        TEXT NOT NULL REFERENCES sejour(id),
    date_prelevement TEXT NOT NULL,
    type_prelevement TEXT NOT NULL,
    resultat         TEXT NOT NULL DEFAULT 'en_cours',
    germe            TEXT,
    antibiogramme    TEXT,           -- texte libre en v1
    cree_le          TEXT NOT NULL,
    cree_par         TEXT REFERENCES utilisateur(id),
    modifie_le       TEXT,
    modifie_par      TEXT REFERENCES utilisateur(id),
    supprime         INTEGER NOT NULL DEFAULT 0,
    version          INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_micro_sejour ON microbiologie(sejour_id, date_prelevement);

-- -------------------------------------------------------------------------
-- ÉVOLUTION QUOTIDIENNE (SPEC §8)
-- -------------------------------------------------------------------------
-- Seule la partie rédigée par le médecin est stockée. L'en-tête, les
-- explorations, les bilans et le traitement sont générés à l'affichage.
CREATE TABLE IF NOT EXISTS evolution_jour (
    id                 TEXT PRIMARY KEY,
    sejour_id          TEXT NOT NULL REFERENCES sejour(id),
    date_jour          TEXT NOT NULL,
    plan_neurologique  TEXT,
    plan_respiratoire  TEXT,
    plan_hemodynamique TEXT,
    plan_infectieux    TEXT,
    conduite           TEXT,
    cree_le            TEXT NOT NULL,
    cree_par           TEXT REFERENCES utilisateur(id),
    modifie_le         TEXT,
    modifie_par        TEXT REFERENCES utilisateur(id),
    supprime           INTEGER NOT NULL DEFAULT 0,
    version            INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evolution_unique ON evolution_jour(sejour_id, date_jour);

-- Éléments fixes des quatre plans (FC, TA, diurèse, température, RASS…).
-- Format long (règle 4) : ajouter un élément ne demande aucune migration, et
-- chaque élément devient exploitable en cinétique comme un analyte.
CREATE TABLE IF NOT EXISTS evolution_element (
    id           TEXT PRIMARY KEY,
    sejour_id    TEXT NOT NULL REFERENCES sejour(id),
    date_jour    TEXT NOT NULL,
    plan         TEXT NOT NULL,   -- neurologique / respiratoire / hemodynamique / infectieux
    cle          TEXT NOT NULL,   -- fc, pas, temperature, rass…
    valeur_num   REAL,
    valeur_texte TEXT,
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    modifie_le   TEXT,
    modifie_par  TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evolution_element_unique
    ON evolution_element(sejour_id, date_jour, cle);

-- Escarres : une lésion suivie dans le temps, pas une case à cocher du jour.
-- Même logique que les dispositifs — constatée, puis guérie ou non.
CREATE TABLE IF NOT EXISTS escarre (
    id            TEXT PRIMARY KEY,
    sejour_id     TEXT NOT NULL REFERENCES sejour(id),
    localisation  TEXT NOT NULL,
    grade         INTEGER,          -- 1 à 4 (NPUAP/EPUAP)
    date_constat  TEXT NOT NULL,
    date_guerison TEXT,
    commentaire   TEXT,
    cree_le       TEXT NOT NULL,
    cree_par      TEXT REFERENCES utilisateur(id),
    modifie_le    TEXT,
    modifie_par   TEXT REFERENCES utilisateur(id),
    supprime      INTEGER NOT NULL DEFAULT 0,
    version       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_escarre_sejour ON escarre(sejour_id, supprime);

-- -------------------------------------------------------------------------
-- SOCLE DE RECHERCHE (SPEC §9.2, §9.5)
-- Tables créées mais aucune saisie imposée tant que le socle n'est pas validé
-- (questions ouvertes 1 à 5).
-- -------------------------------------------------------------------------
-- Dispositifs et actes invasifs — écran « Explorations et actes ».
-- UNE SEULE table pour tout ce qui se pose et se retire : intubation,
-- sédation, sonde nasogastrique, cathéters, drains, épuration… Les tables
-- séparées `ventilation_episode` et `epuration_episode` de la v1.3 sont
-- supprimées : elles auraient donné deux endroits où lire la date
-- d'intubation, donc deux vérités possibles. La durée de ventilation et la
-- durée d'épuration se calculent maintenant depuis cette table (SPEC §9.2).
--
-- Aucune durée n'est stockée : les compteurs de jours (« Intubé J3 »,
-- « Extubé J2 ») se calculent à l'affichage depuis date_pose / date_retrait.
CREATE TABLE IF NOT EXISTS dispositif (
    id            TEXT PRIMARY KEY,
    sejour_id     TEXT NOT NULL REFERENCES sejour(id),
    type          TEXT NOT NULL,   -- voir listes.TYPES_DISPOSITIF
    date_pose     TEXT NOT NULL,
    date_retrait  TEXT,            -- NULL = toujours en place / en cours
    site          TEXT,            -- jugulaire droite, radiale gauche, narine…
    details       TEXT,            -- JSON : fixation_cm, taille, molécules…
    motif_retrait TEXT,
    commentaire   TEXT,
    cree_le       TEXT NOT NULL,
    cree_par      TEXT REFERENCES utilisateur(id),
    modifie_le    TEXT,
    modifie_par   TEXT REFERENCES utilisateur(id),
    supprime      INTEGER NOT NULL DEFAULT 0,
    version       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_dispositif_sejour ON dispositif(sejour_id, supprime);
CREATE INDEX IF NOT EXISTS idx_dispositif_type ON dispositif(sejour_id, type, date_pose);

CREATE TABLE IF NOT EXISTS infection_nosocomiale (
    id              TEXT PRIMARY KEY,
    sejour_id       TEXT NOT NULL REFERENCES sejour(id),
    type            TEXT NOT NULL,    -- pavm / ilc / iu / iss / autre
    date_diagnostic TEXT NOT NULL,
    germe           TEXT,
    commentaire     TEXT,
    cree_le         TEXT NOT NULL,
    cree_par        TEXT REFERENCES utilisateur(id),
    supprime        INTEGER NOT NULL DEFAULT 0,
    version         INTEGER NOT NULL DEFAULT 1,
    modifie_le      TEXT,
    modifie_par     TEXT REFERENCES utilisateur(id)
);
CREATE INDEX IF NOT EXISTS idx_infection_sejour ON infection_nosocomiale(sejour_id);

-- Scores quotidiens en format long : une ligne par score et par jour (règle 4)
CREATE TABLE IF NOT EXISTS score_quotidien (
    id          TEXT PRIMARY KEY,
    sejour_id   TEXT NOT NULL REFERENCES sejour(id),
    date_jour   TEXT NOT NULL,
    score       TEXT NOT NULL,     -- 'sofa', 'igs2'…
    valeur      REAL,
    detail      TEXT,              -- JSON des sous-scores
    cree_le     TEXT NOT NULL,
    cree_par    TEXT REFERENCES utilisateur(id),
    supprime    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER NOT NULL DEFAULT 1,
    modifie_le  TEXT,
    modifie_par TEXT REFERENCES utilisateur(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_score_unique ON score_quotidien(sejour_id, date_jour, score);

-- Variables d'admission alignées ANZICS (SPEC §9.5) : valeurs d'admission,
-- pas pires valeurs des 24 h — simplification assumée, à mentionner dans
-- toute publication.
CREATE TABLE IF NOT EXISTS evaluation_admission (
    id                      TEXT PRIMARY KEY,
    sejour_id               TEXT NOT NULL REFERENCES sejour(id),
    glasgow_oeil            INTEGER,
    glasgow_verbal          INTEGER,
    glasgow_moteur          INTEGER,
    glasgow_non_evaluable   INTEGER NOT NULL DEFAULT 0,   -- patient sédaté
    fragilite               INTEGER,       -- score de fragilité clinique 1-9
    temperature_min         REAL,
    temperature_max         REAL,
    fc_min                  REAL,
    fc_max                  REAL,
    pas_min                 REAL,
    pas_max                 REAL,
    pam_min                 REAL,
    pam_max                 REAL,
    fr_min                  REAL,
    fr_max                  REAL,
    diurese_24h             REAL,          -- mL
    ventilation_invasive_j1 INTEGER,      -- NULL = non renseigné
    cree_le                 TEXT NOT NULL,
    cree_par                TEXT REFERENCES utilisateur(id),
    modifie_le              TEXT,
    modifie_par             TEXT REFERENCES utilisateur(id),
    supprime                INTEGER NOT NULL DEFAULT 0,
    version                 INTEGER NOT NULL DEFAULT 1
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

-- -------------------------------------------------------------------------
-- Le travail infirmier : affectations, administrations, surveillance horaire
-- (SPEC §5.8, demande du service du 9 septembre 2026)
-- -------------------------------------------------------------------------

-- Qui s'occupe de qui, sur quelle vacation. Une ligne par infirmier, par
-- patient et par vacation : un infirmier peut avoir plusieurs patients, et un
-- patient change d'infirmier trois fois par jour. C'est cette table que le
-- surveillant lit pour savoir qui appeler à trois heures du matin.
CREATE TABLE IF NOT EXISTS affectation (
    id             TEXT PRIMARY KEY,
    sejour_id      TEXT NOT NULL REFERENCES sejour(id),
    utilisateur_id TEXT NOT NULL REFERENCES utilisateur(id),
    date_jour      TEXT NOT NULL,   -- le jour de PRISE DE POSTE : la nuit du 9
                                    -- se termine le 10, elle reste datée du 9
    vacation       TEXT NOT NULL,   -- matin / apres_midi / nuit
    cree_le        TEXT NOT NULL,
    cree_par       TEXT REFERENCES utilisateur(id),
    modifie_le     TEXT,
    modifie_par    TEXT REFERENCES utilisateur(id),
    supprime       INTEGER NOT NULL DEFAULT 0,
    version        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_affectation_jour
    ON affectation(date_jour, vacation, supprime);
CREATE INDEX IF NOT EXISTS idx_affectation_sejour
    ON affectation(sejour_id, date_jour, supprime);

-- Une prise administrée (ou non), à son heure prévue.
--
-- `heure_prevue` est l'heure de la pancarte, pas l'heure réelle : c'est elle
-- qui identifie la prise, et elle ne bouge pas si l'infirmière coche à 8 h 20.
-- `date_heure_reelle` garde le moment du clic. Les deux servent : la première
-- pour retrouver la prise, la seconde pour relire ce qui s'est passé.
--
-- Une prise NON donnée se note, elle ne s'omet pas : une case vide veut dire
-- « pas encore », une ligne « non_donne » veut dire « décidé ». Confondre les
-- deux, c'est perdre la seule trace d'un traitement volontairement sauté.
CREATE TABLE IF NOT EXISTS administration (
    id                TEXT PRIMARY KEY,
    sejour_id         TEXT NOT NULL REFERENCES sejour(id),
    ligne_id          TEXT NOT NULL REFERENCES prescription_ligne(id),
    date_jour         TEXT NOT NULL,
    heure_prevue      INTEGER NOT NULL,
    statut            TEXT NOT NULL,   -- donne / non_donne / refuse
    -- Le motif CODÉ (voir referentiels/motifs_non_administration.json) et,
    -- à côté, la précision en texte libre. Les deux, pas l'un ou l'autre :
    -- « rupture » écrit à la main ne se compte pas et ne remonte nulle part,
    -- et un code seul ne dit pas quelle voie était obstruée.
    motif_code        TEXT,
    motif             TEXT,
    date_heure_reelle TEXT,
    cree_le           TEXT NOT NULL,
    cree_par          TEXT REFERENCES utilisateur(id),
    modifie_le        TEXT,
    modifie_par       TEXT REFERENCES utilisateur(id),
    supprime          INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_administration_jour
    ON administration(sejour_id, date_jour, supprime);
CREATE UNIQUE INDEX IF NOT EXISTS idx_administration_prise
    ON administration(ligne_id, date_jour, heure_prevue)
    WHERE supprime = 0;

-- La surveillance clinique heure par heure — celle du verso de la feuille.
-- Format long (une ligne par mesure) comme `evolution_element`, pour la même
-- raison : ajouter une constante ne doit pas demander une colonne de plus.
CREATE TABLE IF NOT EXISTS constante_horaire (
    id           TEXT PRIMARY KEY,
    sejour_id    TEXT NOT NULL REFERENCES sejour(id),
    date_jour    TEXT NOT NULL,   -- jour de service (8 h → 8 h), comme la feuille
    heure        INTEGER NOT NULL,
    cle          TEXT NOT NULL,   -- fc, pas, pad, temperature, spo2, diurese…
    valeur_num   REAL,
    valeur_texte TEXT,
    -- Pour ce qui se recueille dans un sac (la diurèse), valeur_num est le
    -- NIVEAU LU sur le sac, pas ce qui est sorti pendant l'heure : c'est ce
    -- que l'infirmier voit, et lui demander la soustraction au lit du malade
    -- serait lui demander de se tromper. Ce drapeau dit que le sac a été jeté
    -- juste après ce relevé — le suivant repart donc de zéro. Sans lui, un
    -- changement de sac se lirait comme une diurèse qui s'effondre.
    sac_jete     INTEGER NOT NULL DEFAULT 0,
    cree_le      TEXT NOT NULL,
    cree_par     TEXT REFERENCES utilisateur(id),
    modifie_le   TEXT,
    modifie_par  TEXT REFERENCES utilisateur(id),
    supprime     INTEGER NOT NULL DEFAULT 0,
    version      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_constante_jour
    ON constante_horaire(sejour_id, date_jour, supprime);
CREATE UNIQUE INDEX IF NOT EXISTS idx_constante_mesure
    ON constante_horaire(sejour_id, date_jour, heure, cle)
    WHERE supprime = 0;
