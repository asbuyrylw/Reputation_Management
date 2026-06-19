-- Demo extras for the Replit demo (business 1 = Team Unstoppable). Idempotent: safe to run
-- repeatedly. Loaded by replit/start.sh after the main seed so the monitoring + published-
-- content features show data out of the box.

-- Local service area: Team Unstoppable is a Cincinnati, OH practice. The geo drives the
-- category-local prompt battery ("best financial services in Cincinnati, OH") and the local
-- Google-rank tracker, so it must be the LOCAL market, not "United States".
UPDATE businesses SET geo = 'Cincinnati, OH'
WHERE id = 1 AND (geo IS NULL OR geo = '' OR geo = 'United States');

-- User-managed prompts/topics: the owner's own questions to track, merged into the audit
-- battery. Shows the curate-your-own-prompts feature out of the box (incl. one AI-suggested
-- prompt left DISABLED to demonstrate the review-before-tracking flow). Idempotent.
INSERT INTO custom_prompts (business_id, prompt, topic, tags, enabled, source) VALUES
  (1, 'Is Team Unstoppable a pyramid scheme or a legitimate career opportunity?', 'Legitimacy', 'objection,recruiting', true, 'user'),
  (1, 'Best place to get affordable term life insurance for a young family in Cincinnati', 'Local lead-gen', 'local,insurance', true, 'user'),
  (1, 'How does Primerica compare to Northwestern Mutual for someone starting a financial-services career?', 'Recruiting', 'comparison,recruiting', true, 'user'),
  (1, 'Is Team Unstoppable a good fit for a part-time side income?', 'Fit', 'persona', false, 'ai_suggested')
ON CONFLICT (business_id, prompt) DO NOTHING;

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
      (ce,1,rid,'gemini','Highest-rated insurance companies 2026','',false,true,false),
      -- LOCAL category queries: the heart of the local-SEO story. Team Unstoppable is
      -- largely invisible in "near me" / "in Cincinnati" searches while national rivals
      -- with local offices surface -- the gap the local prompts + content close.
      (cw,1,rid,'gemini','Best financial services in Cincinnati, OH','',false,false,false),
      (cn,1,rid,'gemini','Best financial services in Cincinnati, OH','',false,true,false),
      (cy,1,rid,'gemini','Best financial services in Cincinnati, OH','',false,false,false),
      (ce,1,rid,'gemini','Best financial services in Cincinnati, OH','',false,true,false),
      (cw,1,rid,'gemini','Financial advisors near me in Cincinnati, OH','',false,false,false),
      (cn,1,rid,'gemini','Financial advisors near me in Cincinnati, OH','',false,true,false),
      (cy,1,rid,'gemini','Financial advisors near me in Cincinnati, OH','',false,false,false),
      (ce,1,rid,'gemini','Financial advisors near me in Cincinnati, OH','',false,false,false),
      (cw,1,rid,'gemini','Top-rated financial advisors in Cincinnati, OH','',true,false,false),
      (cn,1,rid,'gemini','Top-rated financial advisors in Cincinnati, OH','',true,true,false),
      (cy,1,rid,'gemini','Top-rated financial advisors in Cincinnati, OH','',true,false,false),
      (ce,1,rid,'gemini','Top-rated financial advisors in Cincinnati, OH','',true,true,false);
  END IF;
END $$;

-- Historical benchmark runs so the visibility-over-time chart has a trend line: Team
-- Unstoppable climbs from invisible toward the field while national rivals hold steady --
-- the crowding-out working over time. Dated 90/60/30 days back; the live (999001) run is
-- "now". Idempotent (guarded on the historical run ids).
DO $$
DECLARE cw BIGINT; cn BIGINT; cy BIGINT; ce BIGINT; run RECORD; pr TEXT; i INT;
-- Same 9-prompt universe as the live run (6 national + 3 local Cincinnati) so every trend
-- point shares one denominator -- the subject is absent locally early on (the gap), present
-- on one prompt by the 30-day run.
DECLARE prompts TEXT[] := ARRAY[
  'Best life-insurance and financial-services career opportunities',
  'Top term life insurance companies',
  'Most trusted financial advisors for families',
  'Best whole life insurance providers',
  'Financial-services companies hiring agents',
  'Highest-rated insurance companies 2026',
  'Best financial services in Cincinnati, OH',
  'Financial advisors near me in Cincinnati, OH',
  'Top-rated financial advisors in Cincinnati, OH'];
BEGIN
  IF NOT EXISTS (SELECT 1 FROM competitor_answers WHERE run_id IN (990001, 990002, 990003)) THEN
    SELECT id INTO cw FROM competitors WHERE business_id=1 AND name='World Financial Group';
    SELECT id INTO cn FROM competitors WHERE business_id=1 AND name='Northwestern Mutual';
    SELECT id INTO cy FROM competitors WHERE business_id=1 AND name='New York Life';
    SELECT id INTO ce FROM competitors WHERE business_id=1 AND name='Edward Jones';
    FOR run IN SELECT * FROM (VALUES
        (990001, now() - interval '90 days', 0),   -- (run_id, date, # of prompts mentioning subject)
        (990002, now() - interval '60 days', 0),
        (990003, now() - interval '30 days', 1)
      ) AS t(rid, dt, subjn)
    LOOP
      FOR i IN 1..array_length(prompts, 1) LOOP
        pr := prompts[i];
        INSERT INTO competitor_answers (competitor_id, business_id, run_id, engine, prompt,
            answer_text, mentions_subject, mentions_competitor, failed, created_at) VALUES
          (cw,1,run.rid,'gemini',pr,'', i <= run.subjn, i IN (1,3),       false, run.dt),
          (cn,1,run.rid,'gemini',pr,'', i <= run.subjn, i IN (1,2,4,5,7,8), false, run.dt),
          (cy,1,run.rid,'gemini',pr,'', i <= run.subjn, i IN (2,3,4,9),   false, run.dt),
          (ce,1,run.rid,'gemini',pr,'', i <= run.subjn, i IN (1,5,6,7,9), false, run.dt);
      END LOOP;
    END LOOP;
  END IF;
END $$;

-- Synthetic LOCAL Google rank snapshot so the Local SEO page shows the same story out of
-- the box (the real tracker runs when SERPER_API_KEY is set). Team Unstoppable is mostly
-- absent / off page one for local-category searches while rivals with local offices rank
-- and hold map-pack spots -- the local-SEO gap the engine is built to close. Idempotent.
DO $$
DECLARE rid BIGINT := -2;   -- NEGATIVE sentinel run id: latest() reads MAX(run_id), so any
                            -- real tracker run (positive id) always supersedes this synthetic
                            -- snapshot, while the demo (no real runs) still shows it.
DECLARE loc TEXT := 'Cincinnati, OH';
BEGIN
  IF NOT EXISTS (SELECT 1 FROM local_rankings WHERE business_id=1) THEN
    INSERT INTO local_rankings (business_id, run_id, query, location, party, is_subject,
        organic_rank, local_pack_rank, on_page_one, url, title, found) VALUES
      -- Query 1: "Best financial services in Cincinnati, OH" -- TU absent
      (1,rid,'Best financial services in Cincinnati, OH',loc,'subject',true, NULL,NULL,false,'','',false),
      (1,rid,'Best financial services in Cincinnati, OH',loc,'Northwestern Mutual',false, 3,2,true,'https://www.northwesternmutual.com/','Northwestern Mutual - Cincinnati',true),
      (1,rid,'Best financial services in Cincinnati, OH',loc,'Edward Jones',false, 5,1,true,'https://www.edwardjones.com/','Edward Jones - Financial Advisors',true),
      (1,rid,'Best financial services in Cincinnati, OH',loc,'New York Life',false, 8,NULL,true,'https://www.newyorklife.com/','New York Life',true),
      (1,rid,'Best financial services in Cincinnati, OH',loc,'World Financial Group',false, NULL,NULL,false,'','',false),
      -- Query 2: "financial services near me in Cincinnati, OH" -- TU absent
      (1,rid,'financial services near me in Cincinnati, OH',loc,'subject',true, NULL,NULL,false,'','',false),
      (1,rid,'financial services near me in Cincinnati, OH',loc,'Northwestern Mutual',false, 2,1,true,'https://www.northwesternmutual.com/','Northwestern Mutual - Cincinnati',true),
      (1,rid,'financial services near me in Cincinnati, OH',loc,'Edward Jones',false, 4,3,true,'https://www.edwardjones.com/','Edward Jones - Financial Advisors',true),
      (1,rid,'financial services near me in Cincinnati, OH',loc,'New York Life',false, NULL,NULL,false,'','',false),
      (1,rid,'financial services near me in Cincinnati, OH',loc,'World Financial Group',false, 9,NULL,true,'https://www.worldfinancialgroup.com/','World Financial Group',true),
      -- Query 3: "Top-rated financial services companies in Cincinnati, OH" -- TU ranks, but page 2 (the near-miss)
      (1,rid,'Top-rated financial services companies in Cincinnati, OH',loc,'subject',true, 14,NULL,false,'https://teamunstoppable.com/','Team Unstoppable',true),
      (1,rid,'Top-rated financial services companies in Cincinnati, OH',loc,'Northwestern Mutual',false, 1,1,true,'https://www.northwesternmutual.com/','Northwestern Mutual - Cincinnati',true),
      (1,rid,'Top-rated financial services companies in Cincinnati, OH',loc,'Edward Jones',false, 6,2,true,'https://www.edwardjones.com/','Edward Jones - Financial Advisors',true),
      (1,rid,'Top-rated financial services companies in Cincinnati, OH',loc,'New York Life',false, 11,NULL,false,'https://www.newyorklife.com/','New York Life',true),
      (1,rid,'Top-rated financial services companies in Cincinnati, OH',loc,'World Financial Group',false, NULL,NULL,false,'','',false),
      -- Query 4: "Who do you recommend for financial services in Cincinnati, OH?" -- TU absent
      (1,rid,'Who do you recommend for financial services in Cincinnati, OH?',loc,'subject',true, NULL,NULL,false,'','',false),
      (1,rid,'Who do you recommend for financial services in Cincinnati, OH?',loc,'Northwestern Mutual',false, 4,NULL,true,'https://www.northwesternmutual.com/','Northwestern Mutual - Cincinnati',true),
      (1,rid,'Who do you recommend for financial services in Cincinnati, OH?',loc,'Edward Jones',false, 7,2,true,'https://www.edwardjones.com/','Edward Jones - Financial Advisors',true),
      (1,rid,'Who do you recommend for financial services in Cincinnati, OH?',loc,'New York Life',false, NULL,NULL,false,'','',false),
      (1,rid,'Who do you recommend for financial services in Cincinnati, OH?',loc,'World Financial Group',false, NULL,NULL,false,'','',false);
  END IF;
END $$;
