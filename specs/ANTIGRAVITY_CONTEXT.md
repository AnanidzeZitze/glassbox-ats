# Glass-Box ATS Simulator & Optimization Studio — Master System Context & Production Roadmap

## 1. Executive Summary & Core Value Proposition
The Glass-Box ATS Simulator is a clean-room engineered platform that demystifies how Applicant Tracking Systems (ATS) ingest, parse, score, and rank candidates. Unlike existing black-box resume scanners that output conflicting single-number scores, this platform provides:
1. **Parser X-Ray Telemetry:** Side-by-side visualization of raw byte extraction versus layout-aware block sorting, exposing how two-column layouts interleave text and how PDF headers drop contact details.
2. **Platform-Specific Schema Emulation:** Adapters generating the exact JSON structures and data truncation behaviors of major enterprise ATS platforms (Greenhouse/Sovren, Workday ASCII, Lever NLP Pattern Match).
3. **Deterministic 5-Component Scoring Matrix:** Exact mathematical evaluation across platform weight vectors with zero LLM variance.
4. **Comprehensive Input Simulation:** Evaluation taking into account the full spectrum of ATS inputs—including knockout disqualifier rules, recruiter search filters, application source metadata, talent intelligence graphs, CRM history, and pre-screen assessment scores.
5. **Hybrid Search & Regulatory Compliance:** Reciprocal Rank Fusion (RRF, k=60) candidate retrieval paired with automated NYC Local Law 144 disparate impact auditing.
6. **Constrained Generative Remediation:** Guardrailed bullet point optimization using Pydantic schema validation to prevent LLM hallucinations.

---

## 2. Theoretical Architecture & Technical Foundations

### 2.1 The Ingestion Oligopoly
Over 200 commercial ATS platforms exist, but the vast majority license third-party parsing microservices from a small oligopoly:
- **Textkernel / Sovren:** Over 2 billion resumes parsed annually; deep taxonomy normalization, skills extraction, and PII anonymization. Powers platforms like Greenhouse under the hood.
- **DaXtra:** Enterprise staffing scale; outputs JSON, DaXML, and HR-XML with custom industry taxonomies.
- **RChilli & Affinda:** Fast RESTful APIs with customizable field mapping, multi-language support, and redaction.
- **HireAbility:** High-volume HR-XML Resume 2.1/2.4/2.5 extraction.

### 2.2 Dual-Stream Text Extraction Pipeline
- **Stream A (Naive Horizontal Stream):** Built with `pdfminer.six`. Reads glyphs horizontally left-to-right across the page width. Clips text within the top 1.0 inch (`y0 < 72pt`) and bottom 1.0 inch (`y1 > page_height - 72pt`) to simulate header/footer contact dropping.
- **Stream B (Layout-Aware Block Sorter):** Built with `PyMuPDF` (`fitz`) and `XY-Cut++`. Projects vertical and horizontal whitespace histograms to sort multi-column layouts into human reading order while preserving horizontal gaps under 35pt for `Key : Value` pairs.
- **Interleaving Detection:** Compares line order between Stream A and Stream B. Concatenations across horizontal gaps exceeding 15pt on overlapping baselines trigger an interleaving deduction (-35 points).
- **Stage 0 OCR Fallback:** Native character counts under 50 trigger `pytesseract` with an automatic 0.85 field-level confidence multiplier.
- **DOCX Inspection:** Analyzes XML trees via `python-docx` for `<w:tbl>` tables, floating text boxes (`<w:txbxContent>`), and non-whitelisted fonts.

### 2.3 Stage 5 Platform JSON Schemas
1. **Greenhouse (Sovren Profile):**
   - Candidate name split into `first_name` and `last_name`.
   - Dates formatted as integer `start_month`, `start_year`, `end_month`, `end_year`, and `is_current`.
   - Experience bullet points preserved as a structured array (`description_bullets`).
   - Education separates `degree` and `major`.
   - Retains multi-word soft/analytical skills (`"A/B testing"`, `"stakeholder management"`).
2. **Workday (Enterprise ASCII Profile):**
   - Merged `name` string.
   - Strict `YYYY-MM-DD` date strings.
   - Bullets concatenated into a single continuous `description` paragraph.
   - Degrees collapsed into generic `degreeLevel` tiers (drops major).
   - Drops multi-word soft skills; retains only single-token technical tools.
3. **Lever (NLP Pattern Profile):**
   - Extracts top-level `headline`.
   - Dates as `YYYY-MM` with literal `"Present"`.
   - Bullets formatted as a newline-delimited (`\n`) string under `summary`.
   - Skills truncated to the first 4 extracted tags (`tags[:4]`).
   - Secondary multi-column sidebars are aggressively dropped.

---

## 3. Mathematical Specifications

### 3.1 The Universal 5-Component ATS Scoring Formula
$$\text{Score} = (\text{Keyword Match} \times W_1) + (\text{Placement} \times W_2) + (\text{Sections} \times W_3) + (\text{Parse Success} \times W_4) + (\text{Relevance} \times W_5)$$
Where $\sum W_i = 1.00$.

#### Platform Weight Matrix:
| Platform | W1 (Keyword) | W2 (Placement) | W3 (Sections) | W4 (Parse) | W5 (Relevance) | Matching Logic |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WORKDAY** | 0.50 | 0.10 | 0.20 | 0.15 | 0.05 | Exact match + stemming |
| **TALEO** | 0.55 | 0.08 | 0.17 | 0.15 | 0.05 | Strict verbatim match |
| **ICIMS** | 0.45 | 0.12 | 0.18 | 0.15 | 0.10 | Boolean-weighted hybrid |
| **LEVER** | 0.40 | 0.15 | 0.15 | 0.15 | 0.15 | Dense vector semantic (+0.5 credit) |
| **GREENHOUSE** | N/A | N/A | N/A | N/A | N/A | Human scorecard mode |

#### Keyword Match Calculation:
$$\text{Keyword Match Rate} = 0.70 \left( \frac{\sum_{m \in \text{Must}} I(m) \cdot c_m}{\sum_{m \in \text{Must}} c_m} \right) + 0.30 \left( \frac{\sum_{p \in \text{Pref}} I(p) \cdot c_p}{\sum_{p \in \text{Pref}} c_p} \right)$$
- Skill Multipliers ($c_j$): Hard Skills = 2.0x, Certifications = 2.0x, Tools = 1.5x, Soft Skills = 0.5x.
- Exact match: $I(k) \in \{0, 1\}$.
- Semantic match (Lever): $I(k) = 0.5$ if cosine similarity exceeds threshold.

#### Positional Placement Multipliers:
- Recent Job Title: 3.0x
- Professional Summary: 2.5x
- Dedicated Skills / Certifications Section: 2.0x
- Recent Role Bullets: 1.5x
- Education Section: 1.0x
- Older Role Bullets (3+ years prior): 0.7x

#### Ground-Truth Verification Benchmark (Senior Python Developer):
- **Inputs:** 8 must-haves, 4 preferred. Candidate matches 8/8 must-haves, mentions `"container orchestration"` (not `"Kubernetes"`), placement ratio = 85%, sections = 100%, parse success = 100%, relevance = 70%.
- **Workday Score:** $(0.70 \times 50) + (0.85 \times 10) + (1.0 \times 20) + (1.0 \times 15) + (0.70 \times 5) = 35.0 + 8.5 + 20.0 + 15.0 + 3.5 = \mathbf{82.0 / 100}$
- **Lever Score:** $(0.7375 \times 40) + (0.85 \times 15) + (1.0 \times 15) + (1.0 \times 15) + (0.90 \times 15) = 29.5 + 12.75 + 15.0 + 15.0 + 13.5 = \mathbf{85.75 / 100}$

### 3.2 Enterprise Hybrid Search: Reciprocal Rank Fusion (RRF)
$$\text{RRF\_Score}(d) = \sum_{r \in \{\text{BM25}, \text{ANN}\}} \frac{1}{60 + \text{rank}_r(d)}$$
- Constant $k = 60$ prevents single-retriever outlier domination.
- Top-100 window size per retriever.

### 3.3 NYC Local Law 144 Disparate Impact Telemetry
$$\text{Scoring Rate}_g = \frac{\text{Count}(d \in \text{Group } g \mid \text{Score}(d) > \text{Median}(\text{Pool}))}{\text{Total Applicants in Group } g}$$
$$\text{Impact Ratio}_g = \frac{\text{Scoring Rate}_g}{\max_j(\text{Scoring Rate}_j)}$$
- Adverse impact triggered if $\text{Impact Ratio} < 0.80$ (EEOC Four-Fifths Rule).

---

## 4. Multi-Layered ATS Evaluation Input Matrix
Beyond the public job description, commercial systems evaluate candidates using:
1. **Knockout Rules:** Hard Boolean disqualifiers on work authorization, onsite attendance, minimum credentials, and salary ceilings.
2. **Recruiter Search Queries:** Unpublished preferences and Boolean search parameters (`AND`, `OR`, `NOT`) that determine active retrieval.
3. **Application Source Metadata:** Prioritization channels (Employee Referral > Direct Career Site > Agency > Job Board Inbound).
4. **Talent Intelligence & Enrichment:** External graph data (GitHub, LinkedIn) benchmarked for skill adjacencies and career velocity.
5. **Historical CRM Records:** Multi-year tracking of prior application stages, interview ratings, and recruiter notes.
6. **Pre-Screening Assessments:** Technical coding metrics, cognitive evaluations, and video interview scoring.

---

## 5. Current Implementation State
The following backend architecture is fully implemented and passes all 19 verification tests:
- `backend/models/schemas.py`: Complete Pydantic domain models.
- `backend/services/extractor.py`: Dual-stream parsing with OCR and DOCX inspection.
- `backend/services/nlp_pipeline.py`: spaCy tokenization, 5-block section segmenter, Lightcast Open Skills taxonomy mapping.
- `backend/services/schema_emulators.py`: Greenhouse, Workday, and Lever JSON adapters.
- `backend/services/ats_score.py`: Universal scoring matrix and 30-parameter audit.
- `backend/services/hybrid_search.py`: RRF ranking and NYC LL144 audit calculations.
- `backend/services/tailor.py`: Constrained Pydantic bullet rewriter.
- `backend/main.py`: FastAPI routes exposed under `/api/v1`.
- `backend/tests/`: 19 passed unit and benchmark tests.

---

## 6. Production Roadmap & Engineering Deliverables

### Phase 1: Interactive Next.js Frontend Studio (`frontend/`)
Build a responsive Next.js (App Router) + Tailwind CSS + TypeScript frontend:
- **Parser X-Ray View (`frontend/components/ParserXRay.tsx`):** Split-screen document dropzone with visual bounding-box overlay and ATS Platform Switcher displaying real-time emulated JSON with red line-interleaving indicators.
- **Diagnostic Dashboard (`frontend/components/DiagnosticDashboard.tsx`):** Progress gauges for JD Match Rate (75%-85% target), Parse Success, Content Impact, and Knockout Gate validation.
- **Diff Editor & Safe Exporter (`frontend/components/TailoringStudio.tsx`):** Before-and-after bullet diffs with accept/reject toggles and 1-click export to single-column `.docx` and `pdfLaTeX`.
- **Application Kanban (`frontend/components/KanbanBoard.tsx`):** Stage tracking across Applied, Screening, Interview, and Offer.

### Phase 2: Database Migration & Vector Indexing
- Deploy PostgreSQL 16 with `pgvector` via `docker-compose.yml`.
- Initialize schema for candidates, parsed resumes, job postings, and applications with generated `tsvector` columns and HNSW vector indices.

### Phase 3: Production Hardening
- Configure CORS, JWT authentication, and per-IP rate limiting (SlowAPI).
- Implement background job processing with Celery/Redis for large document batches.
- Set up GitHub Actions CI/CD to run test suites and schema validations on every pull request.
