# Glass-Box ATS Simulator & Optimization Studio — Clean-Room Functional Specification

## 1. Architectural Mandate & Clean-Room Boundaries
1. **Strict Separation of Diagnostics and Generation:** All document text extraction, layout reading-order detection, section segmentation, entity extraction, 5-component ATS scoring, and 30-parameter content auditing MUST execute as 100% deterministic plain Python code (`pdfminer.six`, `PyMuPDF`, `python-docx`, `spaCy`, `pytesseract`). Large Language Models (LLMs) MUST NEVER be invoked to compute an ATS parse check or compatibility score.
2. **Constrained Generative Remediation:** LLMs (via `google-genai`, `instructor` + `pydantic`, or local `Ollama`) are restricted strictly to rewriting experience bullet points and summaries. Validation rules must reject any generated skill, tool, employer, or metric not already present in the candidate's master resume or verified user inputs.
3. **Clean-Room Compliance:** All emulators and scoring formulas are implemented from public developer documentation, academic retrieval algorithms (`XY-Cut++`, BM25, Reciprocal Rank Fusion), and synthetic resume benchmarks.

### Target Monorepo Directory Structure
- `specs/SPECIFICATION.md` (This source-of-truth specification)
- `backend/main.py` (FastAPI application entry point and CORS/router config)
- `backend/models/schemas.py` (Canonical, Greenhouse, Workday, Lever, and Audit Pydantic schemas)
- `backend/services/extractor.py` (Module 1: Stage 0 OCR & Stage 1 Dual-Stream PDF/DOCX extraction)
- `backend/services/nlp_pipeline.py` (Module 2: Stage 2 Tokenization, Stage 3 Segmentation, Stage 4 NER & Taxonomy)
- `backend/services/schema_emulators.py` (Module 3: Stage 5 Platform JSON adapters)
- `backend/services/ats_score.py` (Module 4: 5-Component Scoring Matrix & 30-Parameter Content Auditor)
- `backend/services/hybrid_search.py` (Module 5: PostgreSQL + pgvector RRF Search & NYC LL144 Bias Engine)
- `backend/services/tailor.py` (Module 6: Constrained Instructor/Pydantic LLM Bullet Rewriter)
- `backend/tests/` (Pytest ground-truth test suite)
- `frontend/` (Next.js + TypeScript + Tailwind CSS Split-Screen Studio)

---

## 2. Module 1: Dual-Stream Document Ingestion (`backend/services/extractor.py`)

### Stage 0: Optical Character Recognition (OCR) Fallback
- **Trigger Condition:** Inspect uploaded PDF byte stream. If extracted native character count is `< 50` characters (indicating a scanned paper document, flat screenshot, or outlined vector curves exported from Canva, Figma, or Illustrator), route page pixmaps through `pytesseract`.
- **Degradation Penalty:** Apply a `0.85` field-level confidence multiplier to simulate the compounding error from 98% character-level OCR accuracy down to 85% downstream NER accuracy. If OCR is disabled by the selected platform profile (e.g., standard Greenhouse without OCR), return empty strings for graphic-embedded text.

### Stage 1: Parallel PDF & DOCX Stream Extraction
Every uploaded file must be processed through two parallel extraction strategies to expose formatting corruption:

1. **Stream A — Naive Horizontal Stream (`extract_linear_stream`):**
   - **Engine:** `pdfminer.six` (or Apache Tika equivalent).
   - **Behavior:** Reads glyph coordinates strictly left-to-right, top-to-bottom across the full width of the page (`x0` to `page_width`) and strips all CSS/styling into raw ASCII.
   - **Header/Footer Clipping:** Any text bounding box whose vertical coordinates fall within the top `1.0 inch` (`y0 < 72pt`) or bottom `1.0 inch` (`y1 > page_height - 72pt`) of a PDF page is clipped and logged in `dropped_header_footer_text` to replicate Greenhouse and job-board header stripping.

2. **Stream B — Layout-Aware Block Sorter (`extract_layout_blocks`):**
   - **Engine:** `PyMuPDF` (`fitz.open()`) paired with the recursive `XY-Cut++` bounding-box projection algorithm.
   - **Behavior:** Extracts spatial text blocks `(x0, y0, x1, y1, text, block_no)`. Projects horizontal and vertical whitespace histograms to split multi-column layouts into human reading order (reading Column 1 top-to-bottom before Column 2 top-to-bottom).
   - **Key-Value Preservation:** Deliberately ignores narrow horizontal visual gaps (`< 35pt`) on the same vertical baseline so `Key : Value` skill tables remain intact.

3. **Column Interleaving Detector (`detect_column_interleaving`):**
   - Compares line sequences in Stream A against block-sorted lines in Stream B.
   - If a line in Stream A concatenates tokens belonging to spatially separate horizontal columns in Stream B (`abs(col1_x1 - col2_x0) > 15pt` with overlapping `y` coordinates), flag those lines as `interleaved_lines` and deduct points from `Parse Success`.

4. **DOCX XML Inspector (`extract_docx_xml`):**
   - Parses `.docx` archives via `python-docx`.
   - Inspects underlying XML for `<w:tbl>` (tables), `<w:txbxContent>` (floating text boxes), header/footer contact placement, and font descriptors outside the ATS-safe whitelist (`Calibri`, `Arial`, `Garamond`, `Georgia`, `Helvetica`, `Times New Roman`).

---

## 3. Module 2: NLP Pipeline & Taxonomy Normalizer (`backend/services/nlp_pipeline.py`)

### Stage 2: Tokenization & Unicode Glyph Sanitization
- Tokenize streams using `spaCy` (`en_core_web_md` or `en_core_web_trf`).
- **Bullet Sanitizer:** Whitelist standard solid circles, open circles, squares, and ASCII hyphens (`-`, `*`). Flag decorative Unicode symbols (custom arrows, checkmarks, stars, em-dashes used as bullets) as `phantom_token_hazards` before normalizing them.

### Stage 3: Section Segmentation & Boundary Detection
- Classify document lines into the **5 Mandatory ATS Sections**:
  1. `Contact Information`
  2. `Work Experience`
  3. `Education`
  4. `Skills`
  5. `Employment Dates`
- Also recognize optional standard sections: `Professional Summary`, `Certifications`, `Projects`.
- **Whitelisted Standard Headers:** `"Professional Summary"`, `"Summary"`, `"Work Experience"`, `"Professional Experience"`, `"Experience"`, `"Education"`, `"Skills"`, `"Technical Skills"`, `"Certifications"`, `"Projects"`.
- **Non-Standard Header Penalty:** If employment history or skills blocks are introduced by non-standard creative headings (e.g., `"My Journey"`, `"What I Bring"`, `"Superpowers"`, `"Toolkit"`, `"Knowledge"`), flag a `section_boundary_failure` (simulating Lever unmapped section drops).

### Stage 4: Named Entity Recognition (NER) & Open Skills Taxonomy
- **Deterministic Regex Layer (>99% Target Accuracy):**
  - `EMAIL`: Standard RFC 5322 email regex.
  - `PHONE`: US and international phone regexes.
  - `LINKEDIN_URL`: `linkedin\.com/in/[a-zA-Z0-9_-]+`
  - `DATE`: Enforce consistent date spans (`Month YYYY - Month YYYY`, `Jan 2021 - Mar 2024`, `01/2021 - 03/2024`, or `YYYY-MM`). Flag mixed date formats within the same resume.
- **Statistical NER Layer (70%-90% Target Accuracy):**
  - Extract `PERSON`, `ORG` (Company/Institution), `GPE` (City, State, Country), `TITLE` (Job Role), and `SKILL`.
- **Taxonomy Normalization (Lightcast Open Skills & ESCO v1.2):**
  - Map extracted skill tokens against a local lookup table seeded from **Lightcast Open Skills** (34,000+ skills in `Category -> Subcategory -> Skill` hierarchy) and **ESCO v1.2**.
  - Normalize synonyms/acronyms to canonical IDs (e.g., `"Python"` -> `SKILL_ID_402`) and classify every term into one of four weighted buckets:
    - `HARD_SKILL` (Weight: `2.0x`)
    - `CERTIFICATION` (Weight: `2.0x`)
    - `TOOL` (Weight: `1.5x`)
    - `SOFT_SKILL` (Weight: `0.5x`)

---

## 4. Module 3: Stage 5 Platform JSON Schema Emulators (`backend/services/schema_emulators.py`)

Given an identical input resume (Benchmark Candidate: **Sarah Chen**), the Stage 5 adapter layer must produce the exact platform-specific JSON structures and data-truncation behaviors below:

### 4.1 Greenhouse JSON Schema (Sovren Engine Profile)
- **Behavioral Rules:** Splits candidate name into `first_name` and `last_name`. Parses dates into integer `start_month` and `start_year` with boolean `is_current`. Preserves experience bullets as a structured string array `description_bullets`. Separates `degree` and `major` in education. Retains both single-token technical skills and multi-word soft/analytical skills.

```json
{
  "first_name": "Sarah",
  "last_name": "Chen",
  "email_addresses": ["sarah.chen@example.com"],
  "phone_numbers": [{ "value": "+14155550142", "type": "mobile" }],
  "addresses": [{ "city": "San Francisco", "region": "CA", "country": "US" }],
  "employments": [
    {
      "title": "Senior Product Manager",
      "company_name": "Zendex Inc.",
      "start_month": 3,
      "start_year": 2022,
      "end_month": null,
      "end_year": null,
      "is_current": true,
      "description_bullets": [
        "Led roadmap for enterprise analytics suite, $8M ARR in year one",
        "Managed team of 4 PMs and 18 engineers across 3 time zones",
        "Shipped 14 major releases with 99.2% on-time delivery"
      ]
    }
  ],
  "educations": [
    { "degree": "M.B.A.", "school": "Stanford Graduate School of Business", "end_year": 2019 },
    { "degree": "B.S.", "major": "Computer Science", "school": "UC Berkeley", "end_year": 2015 }
  ],
  "skills": [
    "SQL", "Python", "Tableau", "Jira", "Confluence", "Figma",
    "A/B testing", "product analytics", "stakeholder management", "OKRs"
  ]
}
```

### 4.2 Workday JSON Schema (Enterprise ASCII Profile)
- **Behavioral Rules:** Enforces strict ISO-8601 date strings (`YYYY-MM-DD`). Concatenates experience bullet points into a single space-separated paragraph `description`. Collapses degrees into broad `degreeLevel` tiers (`"Master's"`, `"Bachelor's"`), dropping the `major` field. Drops multi-word soft and analytical skill phrases (`"A/B testing"`, `"product analytics"`, `"stakeholder management"`, `"OKRs"`), retaining only single-token technical tools.

```json
{
  "name": "Sarah Chen",
  "email": "sarah.chen@example.com",
  "phone": "(415) 555-0142",
  "country": "United States",
  "experience": [
    {
      "jobTitle": "Senior Product Manager",
      "company": "Zendex Inc.",
      "startDate": "2022-03-01",
      "endDate": null,
      "currentlyWorkHere": true,
      "description": "Led roadmap for enterprise analytics suite, $8M ARR in year one. Managed team of 4 PMs and 18 engineers across 3 time zones. Shipped 14 major releases with 99.2% on-time delivery."
    }
  ],
  "education": [
    { "degreeLevel": "Master's", "schoolName": "Stanford Graduate School of Business", "graduationYear": 2019 },
    { "degreeLevel": "Bachelor's", "schoolName": "UC Berkeley", "graduationYear": 2015 }
  ],
  "skills": ["SQL", "Python", "Tableau", "Jira", "Confluence", "Figma"]
}
```

### 4.3 Lever JSON Schema (NLP Pattern & Tag-Truncated Profile)
- **Behavioral Rules:** Extracts top-level `headline`. Formats dates as `YYYY-MM` and stores `"Present"` as a literal string for active roles. Compresses bullets into a newline-delimited (`\n`) string under `summary`. Concatenates degree and major into a single `degree` string. Truncates extracted skills under `tags` to the **first 4 tokens only** (`tags[:4]`), and drops secondary multi-column sidebars entirely.

```json
{
  "name": "Sarah Chen",
  "contact": {
    "email": "sarah.chen@example.com",
    "phone": "(415) 555-0142",
    "links": ["[https://linkedin.com/in/sarahchen](https://linkedin.com/in/sarahchen)"]
  },
  "headline": "Senior Product Manager",
  "positions": [
    {
      "title": "Senior Product Manager",
      "org": "Zendex Inc.",
      "start": "2022-03",
      "end": "Present",
      "summary": "Led roadmap for enterprise analytics suite, $8M ARR in year one\nManaged team of 4 PMs and 18 engineers across 3 time zones\nShipped 14 major releases with 99.2% on-time delivery"
    }
  ],
  "schools": [
    { "name": "Stanford Graduate School of Business", "degree": "M.B.A.", "end": "2019" },
    { "name": "UC Berkeley", "degree": "B.S. Computer Science", "end": "2015" }
  ],
  "tags": ["SQL", "Python", "Tableau", "Jira"]
}
```

---

## 5. Module 4: Deterministic 5-Component Scoring & 30-Parameter Audit (`backend/services/ats_score.py`)

### 5.1 Universal Five-Component ATS Score Formula
```text
Score = (Keyword_Match * W1) + (Placement * W2) + (Sections * W3) + (Parse_Success * W4) + (Relevance * W5)
```
Where `W1 + W2 + W3 + W4 + W5 = 1.00 (100%)`.

### 5.2 Platform Weight Matrix (`W1` through `W5`)
| Platform | Keyword Match (W1) | Placement (W2) | Section Completeness (W3) | Parse Success (W4) | Relevance Boost (W5) | Matching Logic |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WORKDAY** | 0.50 (50%) | 0.10 (10%) | 0.20 (20%) | 0.15 (15%) | 0.05 (5%) | Exact verbatim + limited stemming |
| **TALEO** | 0.55 (55%) | 0.08 (8%) | 0.17 (17%) | 0.15 (15%) | 0.05 (5%) | Strict exact match only |
| **ICIMS** | 0.45 (45%) | 0.12 (12%) | 0.18 (18%) | 0.15 (15%) | 0.10 (10%) | Boolean-weighted hybrid |
| **LEVER** | 0.40 (40%) | 0.15 (15%) | 0.15 (15%) | 0.15 (15%) | 0.15 (15%) | Semantic embeddings (+0.5 neighbor credit) |
| **GREENHOUSE** | N/A | N/A | N/A | N/A | N/A | No algorithmic score; manual scorecard mode |

### 5.3 Component Sub-Formulas
1. **Keyword Match (`W1`):**
   - Extract 30 to 60 JD keywords, categorized with weights: `HARD_SKILL = 2.0`, `CERTIFICATION = 2.0`, `TOOL = 1.5`, `SOFT_SKILL = 0.5`.
   - Split requirements into **Must-Have (`0.70` pool weight)** and **Preferred (`0.30` pool weight)**:
     ```text
     must_rate = sum(matched_must_weights) / sum(total_must_weights)
     pref_rate = sum(matched_pref_weights) / sum(total_pref_weights)
     keyword_match_pct = (must_rate * 0.70) + (pref_rate * 0.30)
     ```
   - In **Exact Match** mode (`WORKDAY`, `TALEO`), a keyword scores `1.0` only if present verbatim. In **Semantic Match** mode (`LEVER`), if exact match is absent but embedding cosine similarity exceeds threshold (e.g., `"container orchestration"` matching `"Kubernetes"`), credit `+0.5`.

2. **Positional Placement Multipliers (`W2`):**
   - Each matched keyword is multiplied by a location factor based on where it appears in the parsed resume:
     - Job title in most recent role: `3.0x`
     - Professional summary / headline: `2.5x`
     - Dedicated Skills section: `2.0x`
     - Dedicated Certifications section: `2.0x`
     - Bullet points in recent role: `1.5x`
     - Education section: `1.0x`
     - Bullet points in older roles (3+ years back): `0.7x`

3. **Section Completeness (`W3`):**
   - `20%` awarded for each of the 5 mandatory sections extracted with standard headers: Contact Info, Work Experience, Education, Skills, and standard-formatted Employment Dates.

4. **Parse Success (`W4`):**
   - Starts at `100%`.
   - **Zero-out failures (`0%`):** Unreadable flat image PDF without OCR, outlined vector text, encrypted/copy-protected PDF, or corrupted DOCX.
   - **Graduated deductions:** Two-column interleaving (`-33` to `-46` pts), tables/floating text boxes (`-15` pts), contact info in PDF header/footer (`-15` pts), non-standard Unicode bullets or fonts (`-5` pts).

5. **Relevance Boost (`W5`):**
   - Evaluates 5 alignment signals normalized to `0-100%`:
     - Title match (`+3` to `+8` raw pts)
     - Tenure fit (`+2` to `+5` raw pts)
     - Education level & field match (`+1` to `+3` raw pts)
     - Industry consistency (`+1` to `+3` raw pts)
     - Clean employment timeline with no unexplained gaps or overlapping dates (`+1` to `+2` raw pts)

### 5.4 Ground-Truth Unit Test Benchmark (Senior Python Developer)
`backend/tests/test_ats_score.py` MUST verify this exact benchmark calculation:
- **Inputs:**
  - *Must-have JD skills (8):* Python, Django, PostgreSQL, AWS, Docker, REST APIs, Git, CI/CD
  - *Preferred JD skills (4):* Kubernetes, Celery, Redis, microservices architecture
  - *Candidate Resume:* Matches 8 of 8 must-haves (`100%`). Mentions `"container orchestration"` in experience bullets (0 of 4 preferred on Workday; 0.5 of 4 = `12.5%` semantic credit on Lever). Placement ratio = `85%`. Sections = `100%` (all 5 present). Parse Success = `100%` (clean single-column). Relevance = `70%` (title is `"Senior Software Engineer"` vs `"Senior Python Developer"`, exact tenure/education fit).
- **Expected Workday Output:**
  - Keyword Match: `((1.00 * 0.70) + (0.00 * 0.30)) * 50 = 35.0`
  - Placement: `0.85 * 10 = 8.5`
  - Sections: `1.00 * 20 = 20.0`
  - Parse Success: `1.00 * 15 = 15.0`
  - Relevance: `0.70 * 5 = 3.5`
  - **Total Workday Score:** `35.0 + 8.5 + 20.0 + 15.0 + 3.5 = 82.0 / 100`
- **Expected Lever Output:**
  - Keyword Match: `((1.00 * 0.70) + (0.125 * 0.30)) * 40 = 0.7375 * 40 = 29.5`
  - Placement: `0.85 * 15 = 12.75`
  - Sections: `1.00 * 15 = 15.0`
  - Parse Success: `1.00 * 15 = 15.0`
  - Relevance: `0.90 * 15 = 13.5` (semantic neighbor credit on title)
  - **Total Lever Score:** `29.5 + 12.75 + 15.0 + 15.0 + 13.5 = 85.75 / 100`

### 5.5 The 30-Parameter Content & Formatting Audit Checklist
`audit_resume_content()` must evaluate and return individual pass/warn/fail diagnostics for:
1. Single-column layout (zero multi-column X-coordinate interleaving).
2. Zero tables (`<w:tbl>`) or floating text boxes (`<w:txbxContent>`).
3. Approved file format (`.docx` or native text-layer `.pdf`).
4. Contact info located in main document body (not in top/bottom 1-inch header/footer).
5. Professional email format (`firstname.lastname` style, no numeric spam strings).
6. Phone number present and parseable.
7. Customized LinkedIn URL present.
8. Location formatted strictly as `City, State` (no full street address).
9. Zero embedded photos, headshots, date of birth, marital status, or nationality (PII/blind-hiring compliance).
10. Web-safe font family (`Calibri`, `Arial`, `Garamond`, `Georgia`, `Helvetica`, `Times New Roman`).
11. Body font size between `10pt` and `12pt`; headings between `14pt` and `16pt`.
12. Standard bullet glyphs only (solid/open circles, squares, or hyphens; zero custom Unicode arrows/checkmarks).
13. Summary section labeled `"Professional Summary"` or `"Summary"`.
14. Summary contains exact target job title.
15. Summary contains 2 to 3 core must-have skills from the JD.
16. Summary length is between 3 and 5 sentences.
17. Zero first-person pronouns (`I`, `me`, `my`, `we`, `our`) across Summary and Experience.
18. Dedicated Skills section with standard header.
19. Both spelled-out terms and acronyms included (e.g., `"Search Engine Optimization (SEO)"`).
20. Hard skills and tools prioritized over generic soft skills.
21. Work Experience section labeled `"Work Experience"` or `"Professional Experience"`.
22. Reverse chronological order verified across all roles.
23. Job title, company name, and dates distinctly parseable on every role.
24. Consistent date format across all entries (`Month YYYY` or `MM/YYYY`).
25. Clean timeline (zero unexplained gaps or overlapping date formatting errors).
26. Bullet density between 3 and 6 bullet points per role (no dense paragraphs).
27. Action-verb initiation: `>= 90%` of bullets begin with a strong past/present action verb (`Led`, `Built`, `Increased`, `Reduced`) verified via `spaCy` POS tagging.
28. Quantified impact: `>= 50%` of experience bullets contain measurable numeric results (`%`, `$`, multipliers `x`, or large numbers).
29. Contextual keyword embedding: core JD keywords appear inside experience bullets, not exclusively in the isolated Skills list.
30. Anti-stuffing guardrail: Target match rate band enforced at `75% - 85%`; flag a keyword-stuffing warning if overall match rate is `>= 90%` or any single keyword frequency exceeds natural density.

---

## 6. Module 5: PostgreSQL + `pgvector` Hybrid RRF & Bias Audit (`backend/services/hybrid_search.py`)

### 6.1 Production Database Schema & Reciprocal Rank Fusion (`k = 60`)
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    location_city VARCHAR(100),
    location_region VARCHAR(100),
    linkedin_url TEXT,
    demographic_cohort JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parsed_resumes (
    resume_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    raw_file_format VARCHAR(20) NOT NULL,
    linear_raw_text TEXT NOT NULL,
    layout_sorted_text TEXT NOT NULL,
    canonical_json JSONB NOT NULL,
    greenhouse_json JSONB NOT NULL,
    workday_json JSONB NOT NULL,
    lever_json JSONB NOT NULL,
    parse_success_score NUMERIC(5,2) NOT NULL,
    section_completeness_score NUMERIC(5,2) NOT NULL,
    content_audit_metrics JSONB NOT NULL,
    lexical_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', layout_sorted_text)) STORED,
    dense_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_resumes_lexical_bm25 ON parsed_resumes USING GIN (lexical_tsv);
CREATE INDEX idx_resumes_dense_hnsw ON parsed_resumes USING hnsw (dense_embedding vector_cosine_ops);

CREATE TABLE job_postings (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    target_ats_platform VARCHAR(50) DEFAULT 'WORKDAY',
    raw_description TEXT NOT NULL,
    extracted_keywords JSONB NOT NULL,
    knockout_rules JSONB,
    jd_embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE applications (
    application_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    resume_id UUID NOT NULL REFERENCES parsed_resumes(resume_id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
    passed_knockout BOOLEAN DEFAULT TRUE,
    keyword_match_score NUMERIC(5,2) NOT NULL,
    placement_multiplier_score NUMERIC(5,2) NOT NULL,
    relevance_boost_score NUMERIC(5,2) NOT NULL,
    composite_ats_score NUMERIC(5,2) NOT NULL,
    rrf_hybrid_score NUMERIC(10,8),
    UNIQUE (candidate_id, job_id)
);

-- Hybrid Search Query using Reciprocal Rank Fusion (k = 60, candidate pool window = 100)
WITH bm25_ranked AS (
    SELECT 
        resume_id,
        ROW_NUMBER() OVER (ORDER BY ts_rank_cd(lexical_tsv, plainto_tsquery('english', $1)) DESC) AS bm25_rank
    FROM parsed_resumes
    WHERE lexical_tsv @@ plainto_tsquery('english', $1)
    LIMIT 100
),
vector_ranked AS (
    SELECT 
        resume_id,
        ROW_NUMBER() OVER (ORDER BY (dense_embedding <=> $2::vector) ASC) AS ann_rank
    FROM parsed_resumes
    ORDER BY (dense_embedding <=> $2::vector) ASC
    LIMIT 100
)
SELECT 
    COALESCE(b.resume_id, v.resume_id) AS resume_id,
    b.bm25_rank,
    v.ann_rank,
    (COALESCE(1.0 / (60 + b.bm25_rank), 0.0) + COALESCE(1.0 / (60 + v.ann_rank), 0.0)) AS rrf_score
FROM bm25_ranked b
FULL OUTER JOIN vector_ranked v ON b.resume_id = v.resume_id
ORDER BY rrf_score DESC
LIMIT 25;
```

### 6.2 RRF Mathematical Verification Test
`backend/tests/test_hybrid_search.py` must verify the 3-candidate RRF tournament at `k = 60`:
- **Candidate A (Keyword Stuffer):** `bm25_rank = 1`, `ann_rank = 50` -> `1/61 + 1/110 = 0.02548` (Rank 3)
- **Candidate B (Consensus Match):** `bm25_rank = 3`, `ann_rank = 3` -> `1/63 + 1/63 = 0.03175` (Rank 1 Winner)
- **Candidate C (Semantic Outlier):** `bm25_rank = 10`, `ann_rank = 1` -> `1/70 + 1/61 = 0.03068` (Rank 2)

### 6.3 NYC Local Law 144 Bias Audit Telemetry
For continuous score outputs, compute the **Scoring Rate** and **Impact Ratio** across race, ethnicity, and sex cohorts:
```text
Scoring_Rate(group_g) = count(d in group_g where Score(d) > Median(All_Applicants)) / total_applicants(group_g)
Impact_Ratio(group_g) = Scoring_Rate(group_g) / max_over_all_groups(Scoring_Rate)
```
Flag `adverse_impact_detected = True` if `Impact_Ratio(group_g) < 0.80` (EEOC Four-Fifths Rule).

---

## 7. Module 6: Constrained AI Tailoring & Split-Screen UI (`backend/services/tailor.py` & `frontend/`)

### 7.1 Zero-Hallucination Pydantic Validator
- Use `instructor` or `google-genai` Structured Outputs (`gemini-3-flash-preview` or local `Ollama`) with `max_retries = 3`.
- Enforce `@model_validator(mode="after")` on `ValidatedResume`:
  1. Normalize and validate all employment dates against regex `^\d{4}-\d{2}$` (or literal `"Present"`), verifying `start_date <= end_date`.
  2. Cross-check every skill and metric in the generated bullet diff against the user's `master_resume_json`; raise a `ValueError` (triggering automatic LLM retry with the error traceback) if the model invents an unverified employer, tool, or metric.

### 7.2 Next.js Split-Screen Studio Views
1. **Parser X-Ray Split View:** Left panel renders the visual PDF with bounding-box overlays; right panel provides an interactive **Platform Switcher** (`Workday`, `Greenhouse`, `Lever`, `Taleo`, `iCIMS`) showing the live emulated JSON, red-highlighted interleaved lines, and dropped header/footer fields.
2. **Diagnostic Header & Knockout Check:** Displays the 3 core gauges (`JD Match Rate` with 75%-85% target zone, `Parse Success`, `30-Point Content Score`) plus hard boolean Knockout Disqualifier alerts.
3. **Interactive Diff Editor & ATS-Safe Exporter:** Renders green/red before-and-after bullet diffs requiring user confirmation, paired with 1-click export to single-column `.docx` and Overleaf-compatible `pdfLaTeX`.
4. **Application Kanban Board:** Tracks tailored applications across `Applied`, `Screening`, `Interview`, and `Offer` columns in local SQLite or PostgreSQL.
