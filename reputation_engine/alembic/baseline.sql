CREATE TABLE public.answers (
    id bigint NOT NULL,
    run_id bigint,
    business_id bigint,
    engine text,
    prompt text,
    answer_text text,
    cited_sources jsonb DEFAULT '[]'::jsonb,
    sentiment text,
    goal_alignment numeric(4,2),
    mentions_contested boolean DEFAULT false,
    surfaces_owned boolean DEFAULT false,
    raw jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    sample_idx integer DEFAULT 0,
    failed boolean DEFAULT false,
    persona text DEFAULT ''::text,
    location text DEFAULT ''::text
);

CREATE SEQUENCE public.answers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.answers_id_seq OWNED BY public.answers.id;

CREATE TABLE public.assets (
    id bigint NOT NULL,
    business_id bigint,
    work_order_id bigint,
    asset_type text,
    title text,
    url text,
    surface text,
    published_at timestamp with time zone DEFAULT now(),
    meta jsonb DEFAULT '{}'::jsonb
);

CREATE SEQUENCE public.assets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.assets_id_seq OWNED BY public.assets.id;

CREATE TABLE public.attribution (
    id bigint NOT NULL,
    business_id bigint,
    from_run_id bigint,
    to_run_id bigint,
    metric text,
    delta numeric(8,4),
    assets_in_window jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.attribution_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.attribution_id_seq OWNED BY public.attribution.id;

CREATE TABLE public.audit_runs (
    id bigint NOT NULL,
    business_id bigint,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone,
    status text DEFAULT 'in_progress'::text NOT NULL
);

CREATE SEQUENCE public.audit_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.audit_runs_id_seq OWNED BY public.audit_runs.id;

CREATE TABLE public.business_config (
    business_id bigint NOT NULL,
    disabled_tools jsonb DEFAULT '[]'::jsonb,
    samples_per_prompt integer DEFAULT 2,
    monthly_budget_usd numeric(10,2) DEFAULT 50.0,
    alert_threshold numeric(4,2) DEFAULT 0.15,
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE public.businesses (
    id bigint NOT NULL,
    name text NOT NULL,
    domain text,
    services text,
    profile text,
    goal text,
    contested_terms text,
    geo text,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.businesses_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.businesses_id_seq OWNED BY public.businesses.id;

CREATE TABLE public.citation_momentum (
    id bigint NOT NULL,
    business_id bigint,
    domain text,
    run_id bigint,
    cite_count integer,
    share numeric(6,4),
    classification text,
    first_seen_run bigint,
    last_seen_run bigint,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.citation_momentum_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.citation_momentum_id_seq OWNED BY public.citation_momentum.id;

CREATE TABLE public.competitor_answers (
    id bigint NOT NULL,
    competitor_id bigint,
    business_id bigint,
    run_id bigint,
    engine text,
    prompt text,
    answer_text text,
    cited_sources jsonb DEFAULT '[]'::jsonb,
    mentions_subject boolean,
    mentions_competitor boolean,
    sample_idx integer DEFAULT 0,
    failed boolean DEFAULT false,
    persona text DEFAULT ''::text,
    location text DEFAULT ''::text,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.competitor_answers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.competitor_answers_id_seq OWNED BY public.competitor_answers.id;

CREATE TABLE public.competitors (
    id bigint NOT NULL,
    business_id bigint,
    name text,
    domain text,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.competitors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.competitors_id_seq OWNED BY public.competitors.id;

CREATE TABLE public.content_drafts (
    id bigint NOT NULL,
    business_id bigint,
    work_order_id bigint,
    asset_type text,
    title text,
    body text,
    target_query text,
    quality_score numeric(4,2),
    quality_notes jsonb DEFAULT '{}'::jsonb,
    revision_count integer DEFAULT 0,
    compliance_pass boolean,
    compliance_flags jsonb DEFAULT '[]'::jsonb,
    status text DEFAULT 'pending_review'::text,
    reviewer text,
    reviewed_at timestamp with time zone,
    published_asset_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.content_drafts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.content_drafts_id_seq OWNED BY public.content_drafts.id;

CREATE TABLE public.cost_ledger (
    id bigint NOT NULL,
    business_id bigint,
    run_id bigint,
    provider text,
    operation text,
    model text,
    input_tokens integer,
    output_tokens integer,
    est_cost_usd numeric(10,5),
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.cost_ledger_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.cost_ledger_id_seq OWNED BY public.cost_ledger.id;

CREATE TABLE public.gap_models (
    id bigint NOT NULL,
    business_id bigint,
    run_id bigint,
    model jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.gap_models_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.gap_models_id_seq OWNED BY public.gap_models.id;

CREATE TABLE public.learned_baseline (
    business_id bigint NOT NULL,
    monthly_gain numeric(8,5),
    obs_windows integer,
    confidence text,
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE public.learned_effectiveness (
    business_id bigint NOT NULL,
    lever_type text NOT NULL,
    obs_windows integer,
    obs_units integer,
    gain_per_unit numeric(8,5),
    confidence text,
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE public.mention_replies (
    id bigint NOT NULL,
    mention_id bigint,
    business_id bigint,
    draft text,
    tone text,
    compliance_pass boolean,
    compliance_flags jsonb DEFAULT '[]'::jsonb,
    status text DEFAULT 'pending_review'::text,
    reviewer text,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.mention_replies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.mention_replies_id_seq OWNED BY public.mention_replies.id;

CREATE TABLE public.mentions (
    id bigint NOT NULL,
    business_id bigint,
    source text,
    source_url text,
    external_id text,
    author text,
    title text,
    body text,
    matched_keyword text,
    sentiment text,
    relevance numeric(4,3),
    status text DEFAULT 'new'::text,
    discovered_at timestamp with time zone DEFAULT now(),
    dedup_hash text
);

CREATE SEQUENCE public.mentions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.mentions_id_seq OWNED BY public.mentions.id;

CREATE TABLE public.monitor_keywords (
    id bigint NOT NULL,
    business_id bigint,
    keyword text,
    negative boolean DEFAULT false,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.monitor_keywords_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.monitor_keywords_id_seq OWNED BY public.monitor_keywords.id;

CREATE TABLE public.pipeline_runs (
    id bigint NOT NULL,
    business_id bigint,
    kind text,
    status text DEFAULT 'in_progress'::text,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone
);

CREATE SEQUENCE public.pipeline_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.pipeline_runs_id_seq OWNED BY public.pipeline_runs.id;

CREATE TABLE public.pipeline_steps (
    id bigint NOT NULL,
    pipeline_run_id bigint,
    step_key text,
    status text DEFAULT 'pending'::text,
    error text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone
);

CREATE SEQUENCE public.pipeline_steps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.pipeline_steps_id_seq OWNED BY public.pipeline_steps.id;

CREATE TABLE public.site_audits (
    id bigint NOT NULL,
    business_id bigint,
    run_id bigint,
    summary jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.site_audits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.site_audits_id_seq OWNED BY public.site_audits.id;

CREATE TABLE public.strategy_plans (
    id bigint NOT NULL,
    business_id bigint,
    plan jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.strategy_plans_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.strategy_plans_id_seq OWNED BY public.strategy_plans.id;

CREATE TABLE public.work_orders (
    id bigint NOT NULL,
    business_id bigint,
    plan_id bigint,
    wo_code text,
    title text,
    capability text,
    execution text,
    recommended_tool text,
    instruction text,
    phase text,
    target_date date,
    status text DEFAULT 'pending'::text,
    assignee text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    verified_at timestamp with time zone,
    result_notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.work_orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.work_orders_id_seq OWNED BY public.work_orders.id;

ALTER TABLE ONLY public.answers ALTER COLUMN id SET DEFAULT nextval('public.answers_id_seq'::regclass);

ALTER TABLE ONLY public.assets ALTER COLUMN id SET DEFAULT nextval('public.assets_id_seq'::regclass);

ALTER TABLE ONLY public.attribution ALTER COLUMN id SET DEFAULT nextval('public.attribution_id_seq'::regclass);

ALTER TABLE ONLY public.audit_runs ALTER COLUMN id SET DEFAULT nextval('public.audit_runs_id_seq'::regclass);

ALTER TABLE ONLY public.businesses ALTER COLUMN id SET DEFAULT nextval('public.businesses_id_seq'::regclass);

ALTER TABLE ONLY public.citation_momentum ALTER COLUMN id SET DEFAULT nextval('public.citation_momentum_id_seq'::regclass);

ALTER TABLE ONLY public.competitor_answers ALTER COLUMN id SET DEFAULT nextval('public.competitor_answers_id_seq'::regclass);

ALTER TABLE ONLY public.competitors ALTER COLUMN id SET DEFAULT nextval('public.competitors_id_seq'::regclass);

ALTER TABLE ONLY public.content_drafts ALTER COLUMN id SET DEFAULT nextval('public.content_drafts_id_seq'::regclass);

ALTER TABLE ONLY public.cost_ledger ALTER COLUMN id SET DEFAULT nextval('public.cost_ledger_id_seq'::regclass);

ALTER TABLE ONLY public.gap_models ALTER COLUMN id SET DEFAULT nextval('public.gap_models_id_seq'::regclass);

ALTER TABLE ONLY public.mention_replies ALTER COLUMN id SET DEFAULT nextval('public.mention_replies_id_seq'::regclass);

ALTER TABLE ONLY public.mentions ALTER COLUMN id SET DEFAULT nextval('public.mentions_id_seq'::regclass);

ALTER TABLE ONLY public.monitor_keywords ALTER COLUMN id SET DEFAULT nextval('public.monitor_keywords_id_seq'::regclass);

ALTER TABLE ONLY public.pipeline_runs ALTER COLUMN id SET DEFAULT nextval('public.pipeline_runs_id_seq'::regclass);

ALTER TABLE ONLY public.pipeline_steps ALTER COLUMN id SET DEFAULT nextval('public.pipeline_steps_id_seq'::regclass);

ALTER TABLE ONLY public.site_audits ALTER COLUMN id SET DEFAULT nextval('public.site_audits_id_seq'::regclass);

ALTER TABLE ONLY public.strategy_plans ALTER COLUMN id SET DEFAULT nextval('public.strategy_plans_id_seq'::regclass);

ALTER TABLE ONLY public.work_orders ALTER COLUMN id SET DEFAULT nextval('public.work_orders_id_seq'::regclass);

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.attribution
    ADD CONSTRAINT attribution_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.audit_runs
    ADD CONSTRAINT audit_runs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.business_config
    ADD CONSTRAINT business_config_pkey PRIMARY KEY (business_id);

ALTER TABLE ONLY public.businesses
    ADD CONSTRAINT businesses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.citation_momentum
    ADD CONSTRAINT citation_momentum_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.competitor_answers
    ADD CONSTRAINT competitor_answers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.competitors
    ADD CONSTRAINT competitors_business_id_name_key UNIQUE (business_id, name);

ALTER TABLE ONLY public.competitors
    ADD CONSTRAINT competitors_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.content_drafts
    ADD CONSTRAINT content_drafts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.cost_ledger
    ADD CONSTRAINT cost_ledger_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.gap_models
    ADD CONSTRAINT gap_models_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.learned_baseline
    ADD CONSTRAINT learned_baseline_pkey PRIMARY KEY (business_id);

ALTER TABLE ONLY public.learned_effectiveness
    ADD CONSTRAINT learned_effectiveness_pkey PRIMARY KEY (business_id, lever_type);

ALTER TABLE ONLY public.mention_replies
    ADD CONSTRAINT mention_replies_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mentions
    ADD CONSTRAINT mentions_dedup_hash_key UNIQUE (dedup_hash);

ALTER TABLE ONLY public.mentions
    ADD CONSTRAINT mentions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.monitor_keywords
    ADD CONSTRAINT monitor_keywords_business_id_keyword_key UNIQUE (business_id, keyword);

ALTER TABLE ONLY public.monitor_keywords
    ADD CONSTRAINT monitor_keywords_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.pipeline_steps
    ADD CONSTRAINT pipeline_steps_pipeline_run_id_step_key_key UNIQUE (pipeline_run_id, step_key);

ALTER TABLE ONLY public.pipeline_steps
    ADD CONSTRAINT pipeline_steps_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.site_audits
    ADD CONSTRAINT site_audits_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.strategy_plans
    ADD CONSTRAINT strategy_plans_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_pkey PRIMARY KEY (id);

CREATE INDEX idx_answers_biz ON public.answers USING btree (business_id);

CREATE INDEX idx_answers_run ON public.answers USING btree (run_id);

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id);

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.audit_runs(id);

ALTER TABLE ONLY public.audit_runs
    ADD CONSTRAINT audit_runs_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id);

ALTER TABLE ONLY public.competitor_answers
    ADD CONSTRAINT competitor_answers_competitor_id_fkey FOREIGN KEY (competitor_id) REFERENCES public.competitors(id);

ALTER TABLE ONLY public.gap_models
    ADD CONSTRAINT gap_models_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id);

ALTER TABLE ONLY public.gap_models
    ADD CONSTRAINT gap_models_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.audit_runs(id);

ALTER TABLE ONLY public.mention_replies
    ADD CONSTRAINT mention_replies_mention_id_fkey FOREIGN KEY (mention_id) REFERENCES public.mentions(id);

ALTER TABLE ONLY public.pipeline_steps
    ADD CONSTRAINT pipeline_steps_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id);
