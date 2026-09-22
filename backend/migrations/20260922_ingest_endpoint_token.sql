-- Migration: add ingest token column to remote ingest endpoints
--
-- Why: `Base.metadata.create_all()` only creates missing *tables*. A live MySQL
-- database created before 2026-09-22 will not gain the new `token` column on
-- boot, and the ingest endpoint would then reject every sender with 401.
--
-- Idempotent: guarded by information_schema, safe to run more than once.
-- Run as a user with ALTER privilege on the dashboard schema, e.g.:
--   docker exec -i sec-mysql mysql -uroot -p security_dashboard < \
--     migrations/20260922_ingest_endpoint_token.sql

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'ingest_endpoints'
    AND COLUMN_NAME  = 'token'
);

SET @ddl := IF(
  @has_col = 0,
  'ALTER TABLE ingest_endpoints ADD COLUMN token VARCHAR(64) NULL, ADD INDEX ix_ingest_endpoints_token (token)',
  'SELECT "ingest_endpoints.token already present, skipping" AS note'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Backfill: any endpoint created before this migration has NULL token and will
-- reject every sender. Generate one and print it so the operator can copy it
-- into the sender's X-Ingest-Token header (or use the rotate-token API later).
-- MySQL has no secrets.token_urlsafe — this is a 43-char base64url-ish random
-- string from SHA2 of a random UUID salt, matching the shape of Python's output.
UPDATE ingest_endpoints
   SET token = REPLACE(REPLACE(
         TO_BASE64(UNHEX(SHA2(UUID(), 256))),
         '+', '-'), '/', '_')
 WHERE token IS NULL OR token = '';

SELECT id, name, token AS rotated_token
  FROM ingest_endpoints
 ORDER BY id;
