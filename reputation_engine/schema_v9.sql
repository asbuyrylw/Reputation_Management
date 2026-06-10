-- schema_v9.sql
-- Run after schema_v8.sql:  psql "$REP_DB_DSN" -f schema_v9.sql
--
-- Adds audit_runs.status so a budget-aborted (partial, non-representative) run can be
-- told apart from a completed one. Downstream metrics still gate on
-- finished_at IS NOT NULL; an aborted run keeps finished_at NULL and status='aborted',
-- so it is excluded from every trend / attribution / learning query.
-- (ai_state_audit.init_db() applies the same change defensively at runtime.)

ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'in_progress';

-- Backfill: any run that already has finished_at predates this column and was complete.
UPDATE audit_runs SET status = 'complete'
 WHERE finished_at IS NOT NULL AND status = 'in_progress';
