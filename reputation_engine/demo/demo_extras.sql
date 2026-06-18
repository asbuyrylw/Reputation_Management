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

-- Competitors to benchmark against (financial-services / insurance peers).
INSERT INTO competitors (business_id, name, domain) VALUES
  (1, 'World Financial Group', 'worldfinancialgroup.com'),
  (1, 'Northwestern Mutual', 'northwesternmutual.com'),
  (1, 'New York Life', 'newyorklife.com'),
  (1, 'Edward Jones', 'edwardjones.com')
ON CONFLICT (business_id, name) DO NOTHING;

-- A synthetic benchmark run so the Competitors page shows side-by-side standings out of the
-- box (the real benchmark runs against the AI engines when keys are present). Idempotent.
DO $$
DECLARE rid BIGINT := 999001;   -- standalone id (no audit_runs row, so the dashboard is unaffected)
DECLARE cw BIGINT; cn BIGINT; cy BIGINT; ce BIGINT;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM competitor_answers WHERE business_id=1) THEN
    SELECT id INTO cw FROM competitors WHERE business_id=1 AND name='World Financial Group';
    SELECT id INTO cn FROM competitors WHERE business_id=1 AND name='Northwestern Mutual';
    SELECT id INTO cy FROM competitors WHERE business_id=1 AND name='New York Life';
    SELECT id INTO ce FROM competitors WHERE business_id=1 AND name='Edward Jones';
    INSERT INTO competitor_answers (competitor_id, business_id, run_id, engine, prompt, answer_text, mentions_subject, mentions_competitor, failed) VALUES
      (cw,1,rid,'gemini','Best life-insurance and financial-services career opportunities','',true,true,false),
      (cn,1,rid,'gemini','Best life-insurance and financial-services career opportunities','',true,true,false),
      (cy,1,rid,'gemini','Best life-insurance and financial-services career opportunities','',true,false,false),
      (ce,1,rid,'gemini','Best life-insurance and financial-services career opportunities','',true,false,false),
      (cw,1,rid,'gemini','Top term life insurance companies','',false,false,false),
      (cn,1,rid,'gemini','Top term life insurance companies','',false,true,false),
      (cy,1,rid,'gemini','Top term life insurance companies','',false,true,false),
      (ce,1,rid,'gemini','Top term life insurance companies','',false,false,false),
      (cw,1,rid,'gemini','Most trusted financial advisors for families','',false,false,false),
      (cn,1,rid,'gemini','Most trusted financial advisors for families','',false,true,false),
      (cy,1,rid,'gemini','Most trusted financial advisors for families','',false,true,false),
      (ce,1,rid,'gemini','Most trusted financial advisors for families','',false,true,false),
      (cw,1,rid,'gemini','Best whole life insurance providers','',false,false,false),
      (cn,1,rid,'gemini','Best whole life insurance providers','',false,true,false),
      (cy,1,rid,'gemini','Best whole life insurance providers','',false,true,false),
      (ce,1,rid,'gemini','Best whole life insurance providers','',false,false,false),
      (cw,1,rid,'gemini','Financial-services companies hiring agents','',false,true,false),
      (cn,1,rid,'gemini','Financial-services companies hiring agents','',false,true,false),
      (cy,1,rid,'gemini','Financial-services companies hiring agents','',false,false,false),
      (ce,1,rid,'gemini','Financial-services companies hiring agents','',false,false,false),
      (cw,1,rid,'gemini','Highest-rated insurance companies 2026','',false,false,false),
      (cn,1,rid,'gemini','Highest-rated insurance companies 2026','',false,false,false),
      (cy,1,rid,'gemini','Highest-rated insurance companies 2026','',false,false,false),
      (ce,1,rid,'gemini','Highest-rated insurance companies 2026','',false,true,false);
  END IF;
END $$;
