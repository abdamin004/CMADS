-- ============================================================
-- Patient Clinical Timeline — Time-Series Query
-- ============================================================
-- Combines conditions, encounters, medications, procedures,
-- and observations into a single chronological timeline
-- showing the full clinical journey of a patient.
--
-- Usage: Replace the patient_id CTE value with any PATIENT id.
-- ============================================================

WITH patient_id AS (
    SELECT '0a649950-cc06-d028-1a8d-47477b9d6be7' AS pid
),

-- 1. Disease onsets and resolutions
condition_events AS (
    SELECT
        c.START                          AS event_date,
        'CONDITION_START'                AS event_type,
        c.DESCRIPTION                    AS event_description,
        c.CODE                           AS snomed_code,
        c.ENCOUNTER                      AS encounter_id,
        CASE
            WHEN c.STOP IS NULL OR c.STOP = '' THEN 'ACTIVE'
            ELSE 'RESOLVED on ' || c.STOP
        END                              AS status,
        NULL                             AS value,
        NULL                             AS unit
    FROM conditions c, patient_id p
    WHERE c.PATIENT = p.pid

    UNION ALL

    SELECT
        c.STOP                           AS event_date,
        'CONDITION_END'                  AS event_type,
        c.DESCRIPTION                    AS event_description,
        c.CODE                           AS snomed_code,
        c.ENCOUNTER                      AS encounter_id,
        'RESOLVED'                       AS status,
        NULL                             AS value,
        NULL                             AS unit
    FROM conditions c, patient_id p
    WHERE c.PATIENT = p.pid
      AND c.STOP IS NOT NULL
      AND c.STOP != ''
),

-- 2. Hospital/clinic encounters
encounter_events AS (
    SELECT
        e.START                          AS event_date,
        'ENCOUNTER'                      AS event_type,
        e.ENCOUNTERCLASS || ': ' || e.DESCRIPTION AS event_description,
        e.REASONCODE                     AS snomed_code,
        e.Id                             AS encounter_id,
        e.ENCOUNTERCLASS                 AS status,
        CAST(e.TOTAL_CLAIM_COST AS VARCHAR) AS value,
        'USD'                            AS unit
    FROM encounters e, patient_id p
    WHERE e.PATIENT = p.pid
),

-- 3. Medication starts and stops
medication_events AS (
    SELECT
        m.START                          AS event_date,
        'MEDICATION_START'               AS event_type,
        m.DESCRIPTION                    AS event_description,
        m.CODE                           AS snomed_code,
        m.ENCOUNTER                      AS encounter_id,
        CASE
            WHEN m.REASONDESCRIPTION IS NOT NULL AND m.REASONDESCRIPTION != ''
            THEN 'FOR: ' || m.REASONDESCRIPTION
            ELSE 'reason not specified'
        END                              AS status,
        CAST(m.TOTALCOST AS VARCHAR)     AS value,
        'USD'                            AS unit
    FROM medications m, patient_id p
    WHERE m.PATIENT = p.pid

    UNION ALL

    SELECT
        m.STOP                           AS event_date,
        'MEDICATION_STOP'                AS event_type,
        m.DESCRIPTION                    AS event_description,
        m.CODE                           AS snomed_code,
        m.ENCOUNTER                      AS encounter_id,
        CASE
            WHEN m.REASONDESCRIPTION IS NOT NULL AND m.REASONDESCRIPTION != ''
            THEN 'WAS FOR: ' || m.REASONDESCRIPTION
            ELSE 'reason not specified'
        END                              AS status,
        NULL                             AS value,
        NULL                             AS unit
    FROM medications m, patient_id p
    WHERE m.PATIENT = p.pid
      AND m.STOP IS NOT NULL
      AND m.STOP != ''
),

-- 4. Lab results and vitals
observation_events AS (
    SELECT
        o.DATE                           AS event_date,
        'OBSERVATION'                    AS event_type,
        o.DESCRIPTION                    AS event_description,
        o.CODE                           AS snomed_code,
        o.ENCOUNTER                      AS encounter_id,
        o.CATEGORY                       AS status,
        o.VALUE                          AS value,
        o.UNITS                          AS unit
    FROM observations o, patient_id p
    WHERE o.PATIENT = p.pid
),

-- 5. Procedures performed
procedure_events AS (
    SELECT
        pr.START                         AS event_date,
        'PROCEDURE'                      AS event_type,
        pr.DESCRIPTION                   AS event_description,
        pr.CODE                          AS snomed_code,
        pr.ENCOUNTER                     AS encounter_id,
        CASE
            WHEN pr.REASONDESCRIPTION IS NOT NULL AND pr.REASONDESCRIPTION != ''
            THEN 'FOR: ' || pr.REASONDESCRIPTION
            ELSE NULL
        END                              AS status,
        CAST(pr.BASE_COST AS VARCHAR)    AS value,
        'USD'                            AS unit
    FROM procedures pr, patient_id p
    WHERE pr.PATIENT = p.pid
),

-- Combine all events into one timeline
timeline AS (
    SELECT * FROM condition_events
    UNION ALL
    SELECT * FROM encounter_events
    UNION ALL
    SELECT * FROM medication_events
    UNION ALL
    SELECT * FROM observation_events
    UNION ALL
    SELECT * FROM procedure_events
)

-- Final output: chronological patient timeline
SELECT
    event_date,
    event_type,
    event_description,
    status,
    value,
    unit,
    snomed_code,
    encounter_id
FROM timeline
WHERE event_date IS NOT NULL
  AND event_date != ''
ORDER BY event_date ASC, event_type ASC;


-- ============================================================
-- BONUS: Active medications at any point in time
-- ============================================================
-- Shows which medications were active on a given date,
-- linked to the condition they treat.
--
-- WITH target_date AS (SELECT '2015-01-01' AS d)
-- SELECT
--     m.DESCRIPTION   AS medication,
--     m.START          AS started,
--     m.STOP           AS stopped,
--     m.REASONDESCRIPTION AS treats_condition,
--     m.DISPENSES      AS refill_count
-- FROM medications m, target_date t
-- WHERE m.PATIENT = '0a649950-cc06-d028-1a8d-47477b9d6be7'
--   AND m.START <= t.d
--   AND (m.STOP IS NULL OR m.STOP = '' OR m.STOP >= t.d)
-- ORDER BY m.START;


-- ============================================================
-- BONUS: Disease progression timeline
-- ============================================================
-- Tracks how conditions evolve over time for a patient
-- (e.g., Prediabetes → Diabetes → CKD Stage 1 → 2 → 3 → 4)
--
-- SELECT
--     c.START          AS onset_date,
--     c.STOP           AS resolution_date,
--     c.DESCRIPTION    AS condition,
--     c.CODE           AS snomed_code,
--     CASE
--         WHEN c.STOP IS NULL OR c.STOP = '' THEN 'ACTIVE'
--         ELSE 'RESOLVED'
--     END              AS current_status,
--     e.ENCOUNTERCLASS AS diagnosed_during
-- FROM conditions c
-- JOIN encounters e ON c.ENCOUNTER = e.Id
-- WHERE c.PATIENT = '0a649950-cc06-d028-1a8d-47477b9d6be7'
--   AND c.DESCRIPTION NOT LIKE '%finding%'
--   AND c.DESCRIPTION NOT LIKE '%employment%'
--   AND c.DESCRIPTION NOT LIKE '%education%'
-- ORDER BY c.START;
