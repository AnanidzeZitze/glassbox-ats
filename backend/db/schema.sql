-- ============================================================================
-- Glass-Box ATS Simulator & Optimization Studio
-- PostgreSQL 16 + pgvector Schema for Hybrid BM25 + HNSW Vector RRF Search
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Candidates Table
CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name VARCHAR(255) NOT NULL,
    first_name VARCHAR(128) NOT NULL DEFAULT '',
    last_name VARCHAR(128) NOT NULL DEFAULT '',
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(64),
    phone_e164 VARCHAR(32),
    linkedin_url VARCHAR(512),
    city VARCHAR(128),
    region VARCHAR(128),
    country VARCHAR(128) DEFAULT 'United States',
    headline VARCHAR(512),
    demographic_group VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Parsed Resumes Table (with Dual-Stream Telemetry, Emulated Schemas, tsvector BM25 & pgvector HNSW)
CREATE TABLE IF NOT EXISTS parsed_resumes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    filename VARCHAR(512) NOT NULL,
    file_format VARCHAR(32) NOT NULL DEFAULT 'pdf',
    ocr_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    confidence_multiplier NUMERIC(4, 2) NOT NULL DEFAULT 1.00,
    parse_success_ratio NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    section_completeness_ratio NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    linear_stream_text TEXT NOT NULL DEFAULT '',
    layout_sorted_text TEXT NOT NULL DEFAULT '',
    canonical_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    greenhouse_schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    workday_schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    lever_schema_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Generated tsvector column for sparse lexical BM25 / ts_rank_cd retrieval
    search_tsv TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(layout_sorted_text, '')), 'A')
    ) STORED,
    -- 384-dimensional dense embedding vector (e.g. BAAI/bge-small-en-v1.5 / all-MiniLM-L6-v2)
    embedding VECTOR(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- GIN index for fast full-text lexical retrieval
CREATE INDEX IF NOT EXISTS idx_parsed_resumes_search_tsv
    ON parsed_resumes USING GIN (search_tsv);

-- HNSW index for fast approximate nearest neighbor (ANN) cosine similarity search
CREATE INDEX IF NOT EXISTS idx_parsed_resumes_embedding_hnsw
    ON parsed_resumes USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 3. Job Postings Table
CREATE TABLE IF NOT EXISTS job_postings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    target_title VARCHAR(255) NOT NULL,
    department VARCHAR(128),
    raw_description TEXT NOT NULL DEFAULT '',
    must_have_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_years_experience INTEGER NOT NULL DEFAULT 3,
    knockout_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    jd_tsv TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(target_title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(raw_description, '')), 'B')
    ) STORED,
    jd_embedding VECTOR(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_postings_jd_tsv
    ON job_postings USING GIN (jd_tsv);

CREATE INDEX IF NOT EXISTS idx_job_postings_embedding_hnsw
    ON job_postings USING hnsw (jd_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. Applications & Multi-Platform Scoring Telemetry Table
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    parsed_resume_id UUID NOT NULL REFERENCES parsed_resumes(id) ON DELETE CASCADE,
    job_posting_id UUID NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    active_platform VARCHAR(32) NOT NULL DEFAULT 'WORKDAY',
    kanban_stage VARCHAR(32) NOT NULL DEFAULT 'APPLIED',
    passed_all_knockouts BOOLEAN NOT NULL DEFAULT TRUE,
    keyword_match_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    placement_ratio NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    section_completeness_ratio NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    parse_success_ratio NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    relevance_ratio NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
    total_ats_score NUMERIC(5, 2),
    bm25_rank INTEGER,
    ann_rank INTEGER,
    rrf_score NUMERIC(8, 6),
    score_breakdown_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_applications_job_stage
    ON applications (job_posting_id, kanban_stage);

CREATE INDEX IF NOT EXISTS idx_applications_rrf_score
    ON applications (job_posting_id, rrf_score DESC NULLS LAST);

-- 5. Reciprocal Rank Fusion (RRF, k=60) SQL Helper Function
CREATE OR REPLACE FUNCTION compute_hybrid_rrf_rankings(
    p_query_text TEXT,
    p_query_embedding VECTOR(384),
    p_rrf_k INTEGER DEFAULT 60,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    parsed_resume_id UUID,
    candidate_id UUID,
    bm25_rank BIGINT,
    ann_rank BIGINT,
    rrf_score NUMERIC
) LANGUAGE sql STABLE AS $$
    WITH bm25_ranked AS (
        SELECT
            pr.id AS parsed_resume_id,
            pr.candidate_id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(pr.search_tsv, plainto_tsquery('english', p_query_text)) DESC
            ) AS r_bm25
        FROM parsed_resumes pr
        WHERE pr.search_tsv @@ plainto_tsquery('english', p_query_text)
        LIMIT p_limit
    ),
    ann_ranked AS (
        SELECT
            pr.id AS parsed_resume_id,
            pr.candidate_id,
            ROW_NUMBER() OVER (
                ORDER BY pr.embedding <=> p_query_embedding ASC
            ) AS r_ann
        FROM parsed_resumes pr
        WHERE pr.embedding IS NOT NULL
        LIMIT p_limit
    )
    SELECT
        COALESCE(b.parsed_resume_id, a.parsed_resume_id) AS parsed_resume_id,
        COALESCE(b.candidate_id, a.candidate_id) AS candidate_id,
        b.r_bm25 AS bm25_rank,
        a.r_ann AS ann_rank,
        ROUND(
            (COALESCE(1.0 / (p_rrf_k + b.r_bm25), 0.0) +
             COALESCE(1.0 / (p_rrf_k + a.r_ann), 0.0))::numeric,
            6
        ) AS rrf_score
    FROM bm25_ranked b
    FULL OUTER JOIN ann_ranked a
        ON b.parsed_resume_id = a.parsed_resume_id
    ORDER BY rrf_score DESC;
$$;
