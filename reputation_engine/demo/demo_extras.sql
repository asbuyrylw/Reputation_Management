-- Demo extras for the Replit demo (business 1 = Team Unstoppable). Idempotent: safe to run
-- repeatedly. Loaded by replit/start.sh after the main seed so the monitoring + published-
-- content features show data out of the box.

-- Monitoring keywords (positives to watch; negatives to EXCLUDE the wrong-entity noise).
INSERT INTO monitor_keywords (business_id, keyword, negative) VALUES
  (1, 'Team Unstoppable', false),
  (1, 'Chris Koob', false),
  (1, 'Elizabeth Koob', false),
  (1, 'teamunstoppable.com', false),
  (1, 'Primerica Cincinnati', false),
  (1, 'Unstoppable Domains', true),
  (1, 'Unstoppable Entrepreneur', true)
ON CONFLICT (business_id, keyword) DO NOTHING;

-- A couple of demo "published" assets so the Published Content page isn't empty.
INSERT INTO assets (business_id, asset_type, title, surface, url, published_at, meta)
SELECT 1, 'article', 'Licensing & Regulatory Proof — Team Unstoppable', 'own_site',
       'https://teamunstoppable.com/licensing', now() - interval '5 days', '{"demo": true}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM assets WHERE business_id=1 AND meta->>'demo' = 'true'
                  AND title LIKE 'Licensing%');

INSERT INTO assets (business_id, asset_type, title, surface, url, published_at, meta)
SELECT 1, 'article', 'About Team Unstoppable — Who We Are & Our Primerica Affiliation', 'own_site',
       'https://teamunstoppable.com/about', now() - interval '2 days', '{"demo": true}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM assets WHERE business_id=1 AND meta->>'demo' = 'true'
                  AND title LIKE 'About%');
