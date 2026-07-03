-- Demo login for the Replit demo, applied after seed_data.sql loads the business data.
-- Creates a CLIENT user (owner@teamunstoppable.com) with EDITOR access to Team Unstoppable, so
-- the Director sees the realistic client view (pinned to their business, no switcher) and can
-- still run jobs/audits. Re-runnable (idempotent).
--
-- The seed_data.sql now carries the full, current Team Unstoppable dataset (audits, gaps, the
-- 75-task plan, mentions, competitors, local rankings, etc.), so the older business_id=1 demo
-- extras are no longer needed -- this file is just the demo login + access grant.
--
-- The password hash below is for:  TeamUnstoppable2026!
-- CHANGE IT for anything public-facing (regenerate via rep_engine.api.auth.hash_password and
-- set a fresh value, or change the password after first login).
-- We reference the business by NAME (not a hardcoded id), so it works regardless of its id.

-- users has a UNIQUE(lower(email)) index (not a plain UNIQUE(email)), so we guard with
-- WHERE NOT EXISTS rather than ON CONFLICT, then UPDATE to keep the password/active in sync.
INSERT INTO users (email, password_hash, full_name, role, is_active, org_id, org_role)
SELECT
  'owner@teamunstoppable.com',
  'pbkdf2_sha256$600000$lun+Kk4PNt6+2AhuXMClLg==$bTGHAq4GwFUCIzEIBoeuyZSy4W60cfqVNC5/LuTZ4DE=',
  'Team Unstoppable Owner',
  'client',
  TRUE,
  (SELECT id FROM organizations ORDER BY id LIMIT 1),
  'owner'
WHERE NOT EXISTS (
  SELECT 1 FROM users WHERE lower(email) = lower('owner@teamunstoppable.com')
);

UPDATE users
  SET password_hash = 'pbkdf2_sha256$600000$lun+Kk4PNt6+2AhuXMClLg==$bTGHAq4GwFUCIzEIBoeuyZSy4W60cfqVNC5/LuTZ4DE=',
      is_active = TRUE
  WHERE lower(email) = lower('owner@teamunstoppable.com');

INSERT INTO business_access (user_id, business_id, access_role)
SELECT u.id, b.id, 'editor'
FROM users u
CROSS JOIN businesses b
WHERE lower(u.email) = lower('owner@teamunstoppable.com')
  AND b.name = 'Team Unstoppable'
  AND NOT EXISTS (
    SELECT 1 FROM business_access ba WHERE ba.user_id = u.id AND ba.business_id = b.id
  );
