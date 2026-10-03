-- Apply once, with workers stopped, after 001_knowledge_contract_v1.sql.
-- All phase-3 writers must use the repository's revision fence.
CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.${DATASET}.knowledge_processing_guard`
(guard_id STRING NOT NULL, revision INT64 NOT NULL);
INSERT INTO `${PROJECT_ID}.${DATASET}.knowledge_processing_guard` (guard_id, revision)
SELECT 'v1', 0
WHERE NOT EXISTS (
  SELECT 1 FROM `${PROJECT_ID}.${DATASET}.knowledge_processing_guard` WHERE guard_id = 'v1'
);
ASSERT (SELECT COUNT(*) = 1 FROM `${PROJECT_ID}.${DATASET}.knowledge_processing_guard`
        WHERE guard_id = 'v1') AS 'Expected exactly one processing guard';
