-- Upsert staged Solodit findings into the canonical findings table.
--
-- Replace ${PROJECT_ID} and ${DATASET} before executing.

MERGE `${PROJECT_ID}.${DATASET}.findings` AS target
USING (
  SELECT * EXCEPT(row_number)
  FROM (
    SELECT
      staging.*,
      ROW_NUMBER() OVER (
        PARTITION BY id
        ORDER BY crawled_at DESC, loaded_at DESC
      ) AS row_number
    FROM `${PROJECT_ID}.${DATASET}.findings_staging` AS staging
  )
  WHERE row_number = 1
) AS source
ON target.id = source.id
WHEN MATCHED AND target.source_payload_hash IS DISTINCT FROM source.source_payload_hash THEN
  UPDATE SET
    kind = source.kind,
    auditfirm_id = source.auditfirm_id,
    impact = source.impact,
    finders_count = source.finders_count,
    protocol_id = source.protocol_id,
    title = source.title,
    content = source.content,
    summary = source.summary,
    report_date = source.report_date,
    contest_prize_txt = source.contest_prize_txt,
    contest_link = source.contest_link,
    sponsor_name = source.sponsor_name,
    sponsor_link = source.sponsor_link,
    quality_score = source.quality_score,
    general_score = source.general_score,
    source_link = source.source_link,
    github_link = source.github_link,
    pdf_link = source.pdf_link,
    pdf_page_from = source.pdf_page_from,
    contest_id = source.contest_id,
    slug = source.slug,
    firm_name = source.firm_name,
    firm_logo_square = source.firm_logo_square,
    protocol_name = source.protocol_name,
    bookmarked = source.bookmarked,
    read = source.read,
    finder_handles = source.finder_handles,
    auditfirm = source.auditfirm,
    protocol = source.protocol,
    issue_finders = source.issue_finders,
    issue_tag_scores = source.issue_tag_scores,
    source_payload = source.source_payload,
    source_payload_hash = source.source_payload_hash,
    crawled_at = source.crawled_at,
    loaded_at = source.loaded_at
WHEN NOT MATCHED THEN
  INSERT (
    id,
    kind,
    auditfirm_id,
    impact,
    finders_count,
    protocol_id,
    title,
    content,
    summary,
    report_date,
    contest_prize_txt,
    contest_link,
    sponsor_name,
    sponsor_link,
    quality_score,
    general_score,
    source_link,
    github_link,
    pdf_link,
    pdf_page_from,
    contest_id,
    slug,
    firm_name,
    firm_logo_square,
    protocol_name,
    bookmarked,
    read,
    finder_handles,
    auditfirm,
    protocol,
    issue_finders,
    issue_tag_scores,
    source_payload,
    source_payload_hash,
    crawled_at,
    loaded_at
  )
  VALUES (
    source.id,
    source.kind,
    source.auditfirm_id,
    source.impact,
    source.finders_count,
    source.protocol_id,
    source.title,
    source.content,
    source.summary,
    source.report_date,
    source.contest_prize_txt,
    source.contest_link,
    source.sponsor_name,
    source.sponsor_link,
    source.quality_score,
    source.general_score,
    source.source_link,
    source.github_link,
    source.pdf_link,
    source.pdf_page_from,
    source.contest_id,
    source.slug,
    source.firm_name,
    source.firm_logo_square,
    source.protocol_name,
    source.bookmarked,
    source.read,
    source.finder_handles,
    source.auditfirm,
    source.protocol,
    source.issue_finders,
    source.issue_tag_scores,
    source.source_payload,
    source.source_payload_hash,
    source.crawled_at,
    source.loaded_at
  );
