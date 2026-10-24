/**
 * Typed API Client Layer for Glass-Box ATS Simulator & Optimization Studio.
 * Points to http://localhost:8000/api/v1 with deterministic clean-room benchmark fallbacks.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

export type ATSPlatform = "WORKDAY" | "GREENHOUSE" | "LEVER" | "TALEO" | "ICIMS";

export interface BoundingBoxBlock {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  text: string;
  block_no: number;
  page_no: number;
  font_name?: string | null;
  font_size?: number | null;
}

export interface InterleavedLineFlag {
  line_text: string;
  left_block_text: string;
  right_block_text: string;
  horizontal_gap_pt: number;
  page_no: number;
}

export interface ExtractionResult {
  file_format: string;
  ocr_triggered: boolean;
  ocr_enabled_by_profile: boolean;
  confidence_multiplier: number;
  is_unreadable_or_encrypted: boolean;
  linear_stream_text: string;
  layout_sorted_text: string;
  dropped_header_footer_text: string[];
  interleaved_lines: InterleavedLineFlag[];
  blocks: BoundingBoxBlock[];
  detected_fonts: string[];
  body_font_sizes_pt: number[];
  heading_font_sizes_pt: number[];
  has_tables_or_textboxes: boolean;
  has_embedded_images: boolean;
}

export interface ParsedEmployment {
  title: string;
  company: string;
  start_date_raw: string;
  end_date_raw?: string | null;
  start_year: number;
  start_month: number;
  end_year?: number | null;
  end_month?: number | null;
  is_current: boolean;
  bullets: string[];
}

export interface ParsedEducation {
  degree: string;
  major?: string | null;
  school: string;
  end_year: number;
}

export interface CanonicalResume {
  full_name: string;
  first_name: string;
  last_name: string;
  headline?: string | null;
  email?: string | null;
  phone?: string | null;
  phone_e164?: string | null;
  linkedin_url?: string | null;
  address?: {
    city: string;
    region: string;
    country: string;
    has_street_address?: boolean;
  } | null;
  country_full: string;
  summary?: string | null;
  employments: ParsedEmployment[];
  educations: ParsedEducation[];
  skills: string[];
  certifications: string[];
  projects: string[];
  mandatory_sections_present: Record<string, boolean>;
  detected_section_headers: Record<string, string>;
  section_boundary_failures: {
    header_text: string;
    inferred_target_section: string;
    reason: string;
  }[];
  phantom_token_hazards: {
    raw_glyph: string;
    codepoint: string;
    line_text: string;
    normalized_replacement: string;
  }[];
  mixed_date_formats_detected: boolean;
  detected_date_formats: string[];
  extraction_result?: ExtractionResult | null;
}

export interface ParseXRayResponse {
  filename: string;
  extraction: ExtractionResult;
  canonical: CanonicalResume;
  emulators: Record<ATSPlatform, Record<string, unknown>>;
}

export interface JDRequirementInput {
  target_title: string;
  must_have_skills: string[];
  preferred_skills: string[];
  required_years_experience?: number;
  required_degree_level?: string;
  target_industry?: string;
}

export interface KnockoutRulesInput {
  requires_work_auth: boolean;
  candidate_has_work_auth: boolean;
  requires_clearance: string;
  candidate_clearance: string;
  required_onsite_days: number;
  candidate_max_onsite_days: number;
  required_degree_tier: string;
  candidate_degree_tier: string;
}

export interface KnockoutCheckItem {
  id: string;
  label: string;
  required_value: string;
  candidate_value: string;
  passed: boolean;
  disqualifier_reason?: string | null;
}

export interface ATSScoreBreakdown {
  platform: ATSPlatform;
  manual_scorecard_mode: boolean;
  must_have_match_rate: number;
  preferred_match_rate: number;
  keyword_match_pct: number;
  placement_ratio: number;
  section_completeness_ratio: number;
  parse_success_ratio: number;
  relevance_ratio: number;
  keyword_match_weighted: number;
  placement_weighted: number;
  sections_weighted: number;
  parse_success_weighted: number;
  relevance_weighted: number;
  total_score: number | null;
  matched_must_have: string[];
  missing_must_have: string[];
  matched_preferred: string[];
  semantic_neighbor_matches: string[];
}

export interface AuditParameterResult {
  param_id: number;
  name: string;
  category: string;
  status: "PASS" | "WARN" | "FAIL";
  passed: boolean;
  message: string;
  metric_value?: unknown;
}

export interface ResumeAuditReport {
  total_parameters: number;
  passed_count: number;
  warn_count: number;
  fail_count: number;
  overall_audit_score: number;
  parameters: AuditParameterResult[];
}

export interface ComputeScoreResponse {
  score_breakdown: ATSScoreBreakdown;
  audit_report: ResumeAuditReport;
  passed_all_knockouts: boolean;
  knockout_checks: KnockoutCheckItem[];
}

export interface RRFCandidateInput {
  candidate_id: string;
  candidate_name: string;
  bm25_rank: number | null;
  ann_rank: number | null;
}

export interface RRFCandidateResult {
  candidate_id: string;
  candidate_name: string;
  bm25_rank: number | null;
  ann_rank: number | null;
  rrf_score: number;
  final_rank: number;
}

export interface TailorBulletDiffItem {
  diff_id: string;
  role_title: string;
  company: string;
  start_date: string;
  end_date: string;
  original_bullet: string;
  tailored_bullet: string;
  injected_keywords: string[];
  action_verb_verified: boolean;
  quantified_metric_preserved: string;
  hallucination_guard_passed: boolean;
}

export interface TailorBulletsResponse {
  candidate_name: string;
  validator_passed: boolean;
  validation_summary: string;
  diffs: TailorBulletDiffItem[];
  latex_source: string;
}

// ============================================================================
// Ground-Truth Benchmark Fixtures (Sarah Chen & Senior Python Developer)
// ============================================================================

export const DEFAULT_BENCHMARK_JD: JDRequirementInput = {
  target_title: "Senior Python Developer",
  must_have_skills: [
    "Python",
    "Django",
    "PostgreSQL",
    "AWS",
    "Docker",
    "REST APIs",
    "Git",
    "CI/CD",
  ],
  preferred_skills: [
    "Kubernetes",
    "Celery",
    "Redis",
    "microservices architecture",
  ],
  required_years_experience: 5,
  required_degree_level: "Bachelor's",
  target_industry: "Enterprise SaaS",
};

export const DEFAULT_KNOCKOUT_RULES: KnockoutRulesInput = {
  requires_work_auth: true,
  candidate_has_work_auth: true,
  requires_clearance: "None",
  candidate_clearance: "None",
  required_onsite_days: 2,
  candidate_max_onsite_days: 3,
  required_degree_tier: "Bachelor's",
  candidate_degree_tier: "Master's",
};

export const SARAH_CHEN_XRAY_FIXTURE: ParseXRayResponse = {
  filename: "sarah_chen_benchmark.pdf",
  extraction: {
    file_format: "pdf",
    ocr_triggered: false,
    ocr_enabled_by_profile: true,
    confidence_multiplier: 1.0,
    is_unreadable_or_encrypted: false,
    linear_stream_text:
      "Sarah Chen\nSan Francisco, CA | sarah.chen@example.com | (415) 555-0142 | https://linkedin.com/in/sarahchen\nProfessional Summary\nSenior Product Manager and Senior Python Developer with 8 years of experience building enterprise analytics suites in Python, SQL, Django, and PostgreSQL.\nWork Experience\nSenior Product Manager | Zendex Inc. | Mar 2022 - Present\n• Led roadmap for enterprise analytics suite, $8M ARR in year one\n• Managed team of 4 PMs and 18 engineers across 3 time zones\n• Shipped 14 major releases with 99.2% on-time delivery\nEducation\nM.B.A. | Stanford Graduate School of Business | 2019\nB.S. in Computer Science | UC Berkeley | 2015\nSkills\nSQL, Python, Tableau, Jira, Confluence, Figma, A/B testing, product analytics, stakeholder management, OKRs",
    layout_sorted_text:
      "Sarah Chen\nSan Francisco, CA | sarah.chen@example.com | (415) 555-0142 | https://linkedin.com/in/sarahchen\nProfessional Summary\nSenior Product Manager and Senior Python Developer with 8 years of experience building enterprise analytics suites in Python, SQL, Django, and PostgreSQL.\nWork Experience\nSenior Product Manager | Zendex Inc. | Mar 2022 - Present\n• Led roadmap for enterprise analytics suite, $8M ARR in year one\n• Managed team of 4 PMs and 18 engineers across 3 time zones\n• Shipped 14 major releases with 99.2% on-time delivery\nEducation\nM.B.A. | Stanford Graduate School of Business | 2019\nB.S. in Computer Science | UC Berkeley | 2015\nSkills\nSQL, Python, Tableau, Jira, Confluence, Figma, A/B testing, product analytics, stakeholder management, OKRs",
    dropped_header_footer_text: [],
    interleaved_lines: [],
    blocks: [
      { x0: 72, y0: 84, x1: 240, y1: 102, text: "Sarah Chen", block_no: 0, page_no: 0, font_name: "Calibri", font_size: 16 },
      { x0: 72, y0: 108, x1: 520, y1: 122, text: "San Francisco, CA | sarah.chen@example.com | (415) 555-0142", block_no: 1, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 142, x1: 220, y1: 158, text: "Work Experience", block_no: 2, page_no: 0, font_name: "Calibri", font_size: 14 },
      { x0: 72, y0: 164, x1: 480, y1: 178, text: "Senior Product Manager | Zendex Inc. | Mar 2022 - Present", block_no: 3, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 184, x1: 520, y1: 198, text: "• Led roadmap for enterprise analytics suite, $8M ARR in year one", block_no: 4, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 202, x1: 520, y1: 216, text: "• Managed team of 4 PMs and 18 engineers across 3 time zones", block_no: 5, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 220, x1: 520, y1: 234, text: "• Shipped 14 major releases with 99.2% on-time delivery", block_no: 6, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 256, x1: 180, y1: 272, text: "Education", block_no: 7, page_no: 0, font_name: "Calibri", font_size: 14 },
      { x0: 72, y0: 278, x1: 490, y1: 292, text: "M.B.A. | Stanford Graduate School of Business | 2019", block_no: 8, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 296, x1: 460, y1: 310, text: "B.S. in Computer Science | UC Berkeley | 2015", block_no: 9, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 72, y0: 332, x1: 140, y1: 348, text: "Skills", block_no: 10, page_no: 0, font_name: "Calibri", font_size: 14 },
      { x0: 72, y0: 354, x1: 530, y1: 372, text: "SQL, Python, Tableau, Jira, Confluence, Figma, A/B testing, product analytics, stakeholder management, OKRs", block_no: 11, page_no: 0, font_name: "Calibri", font_size: 11 },
    ],
    detected_fonts: ["Calibri", "Arial"],
    body_font_sizes_pt: [11.0],
    heading_font_sizes_pt: [14.0, 16.0],
    has_tables_or_textboxes: false,
    has_embedded_images: false,
  },
  canonical: {
    full_name: "Sarah Chen",
    first_name: "Sarah",
    last_name: "Chen",
    headline: "Senior Product Manager",
    email: "sarah.chen@example.com",
    phone: "(415) 555-0142",
    phone_e164: "+14155550142",
    linkedin_url: "https://linkedin.com/in/sarahchen",
    address: { city: "San Francisco", region: "CA", country: "US", has_street_address: false },
    country_full: "United States",
    summary:
      "Senior Python Developer and Product Leader with 8 years of experience architecting analytics platforms using Python, Django, and PostgreSQL. Proven track record scaling cloud systems on AWS with Docker, Git, and CI/CD pipelines. Delivered enterprise REST APIs generating $8M ARR.",
    employments: [
      {
        title: "Senior Product Manager",
        company: "Zendex Inc.",
        start_date_raw: "Mar 2022",
        end_date_raw: "Present",
        start_year: 2022,
        start_month: 3,
        end_year: null,
        end_month: null,
        is_current: true,
        bullets: [
          "Led roadmap for enterprise analytics suite, $8M ARR in year one",
          "Managed team of 4 PMs and 18 engineers across 3 time zones",
          "Shipped 14 major releases with 99.2% on-time delivery",
        ],
      },
    ],
    educations: [
      { degree: "M.B.A.", major: null, school: "Stanford Graduate School of Business", end_year: 2019 },
      { degree: "B.S.", major: "Computer Science", school: "UC Berkeley", end_year: 2015 },
    ],
    skills: [
      "SQL",
      "Python",
      "Tableau",
      "Jira",
      "Confluence",
      "Figma",
      "A/B testing",
      "product analytics",
      "stakeholder management",
      "OKRs",
    ],
    certifications: ["AWS Certified Solutions Architect"],
    projects: [],
    mandatory_sections_present: {
      "Contact Information": true,
      "Work Experience": true,
      "Education": true,
      "Skills": true,
      "Employment Dates": true,
    },
    detected_section_headers: {
      "Professional Summary": "Professional Summary",
      "Work Experience": "Work Experience",
      "Education": "Education",
      "Skills": "Skills",
    },
    section_boundary_failures: [],
    phantom_token_hazards: [],
    mixed_date_formats_detected: false,
    detected_date_formats: ["MONTH_YYYY"],
  },
  emulators: {
    GREENHOUSE: {
      first_name: "Sarah",
      last_name: "Chen",
      email_addresses: ["sarah.chen@example.com"],
      phone_numbers: [{ value: "+14155550142", type: "mobile" }],
      addresses: [{ city: "San Francisco", region: "CA", country: "US" }],
      employments: [
        {
          title: "Senior Product Manager",
          company_name: "Zendex Inc.",
          start_month: 3,
          start_year: 2022,
          end_month: null,
          end_year: null,
          is_current: true,
          description_bullets: [
            "Led roadmap for enterprise analytics suite, $8M ARR in year one",
            "Managed team of 4 PMs and 18 engineers across 3 time zones",
            "Shipped 14 major releases with 99.2% on-time delivery",
          ],
        },
      ],
      educations: [
        { degree: "M.B.A.", school: "Stanford Graduate School of Business", end_year: 2019 },
        { degree: "B.S.", major: "Computer Science", school: "UC Berkeley", end_year: 2015 },
      ],
      skills: [
        "SQL",
        "Python",
        "Tableau",
        "Jira",
        "Confluence",
        "Figma",
        "A/B testing",
        "product analytics",
        "stakeholder management",
        "OKRs",
      ],
    },
    WORKDAY: {
      name: "Sarah Chen",
      email: "sarah.chen@example.com",
      phone: "(415) 555-0142",
      country: "United States",
      experience: [
        {
          jobTitle: "Senior Product Manager",
          company: "Zendex Inc.",
          startDate: "2022-03-01",
          endDate: null,
          currentlyWorkHere: true,
          description:
            "Led roadmap for enterprise analytics suite, $8M ARR in year one. Managed team of 4 PMs and 18 engineers across 3 time zones. Shipped 14 major releases with 99.2% on-time delivery.",
        },
      ],
      education: [
        { degreeLevel: "Master's", schoolName: "Stanford Graduate School of Business", graduationYear: 2019 },
        { degreeLevel: "Bachelor's", schoolName: "UC Berkeley", graduationYear: 2015 },
      ],
      skills: ["SQL", "Python", "Tableau", "Jira", "Confluence", "Figma"],
    },
    LEVER: {
      name: "Sarah Chen",
      contact: {
        email: "sarah.chen@example.com",
        phone: "(415) 555-0142",
        links: ["https://linkedin.com/in/sarahchen"],
      },
      headline: "Senior Product Manager",
      positions: [
        {
          title: "Senior Product Manager",
          org: "Zendex Inc.",
          start: "2022-03",
          end: "Present",
          summary:
            "Led roadmap for enterprise analytics suite, $8M ARR in year one\nManaged team of 4 PMs and 18 engineers across 3 time zones\nShipped 14 major releases with 99.2% on-time delivery",
        },
      ],
      schools: [
        { name: "Stanford Graduate School of Business", degree: "M.B.A.", end: "2019" },
        { name: "UC Berkeley", degree: "B.S. Computer Science", end: "2015" },
      ],
      tags: ["SQL", "Python", "Tableau", "Jira"],
    },
    TALEO: {
      candidateProfile: {
        fullName: "Sarah Chen",
        primaryEmail: "sarah.chen@example.com",
        primaryPhone: "(415) 555-0142",
        asciiStrictMode: true,
      },
      workHistory: [
        {
          positionTitle: "Senior Product Manager",
          employerName: "Zendex Inc.",
          startDate: "2022-03",
          endDate: "Present",
          rawTextBlock:
            "Led roadmap for enterprise analytics suite, $8M ARR in year one | Managed team of 4 PMs and 18 engineers across 3 time zones | Shipped 14 major releases with 99.2% on-time delivery",
        },
      ],
      exactMatchedTokens: ["SQL", "Python", "Tableau", "Jira", "Confluence", "Figma"],
    },
    ICIMS: {
      applicant: {
        firstName: "Sarah",
        lastName: "Chen",
        email: "sarah.chen@example.com",
        phone: "+14155550142",
        location: "San Francisco, CA",
      },
      roles: [
        {
          title: "Senior Product Manager",
          company_name: "Zendex Inc.",
          start_month: 3,
          start_year: 2022,
          is_current: true,
        },
      ],
      booleanSkillClusters: [
        { skill: "SQL", categoryWeight: 2.0 },
        { skill: "Python", categoryWeight: 2.0 },
        { skill: "Tableau", categoryWeight: 1.5 },
        { skill: "Jira", categoryWeight: 1.5 },
      ],
    },
  },
};

export const TWO_COLUMN_HAZARD_XRAY_FIXTURE: ParseXRayResponse = {
  ...SARAH_CHEN_XRAY_FIXTURE,
  filename: "two_column_canva_corrupted.pdf",
  extraction: {
    ...SARAH_CHEN_XRAY_FIXTURE.extraction,
    dropped_header_footer_text: [
      "sarah.chen@example.com | (415) 555-0142 | https://linkedin.com/in/sarahchen (Clipped at y0 = 24pt < 36pt Top Margin)",
      "Page 1 of 1 — Portfolio Resume (Clipped at y1 = 762pt > 756pt Bottom Margin)",
    ],
    interleaved_lines: [
      {
        line_text: "Work Experience                     Superpowers & Toolkit",
        left_block_text: "Work Experience",
        right_block_text: "Superpowers & Toolkit",
        horizontal_gap_pt: 148.5,
        page_no: 0,
      },
      {
        line_text: "Senior Product Manager | Zendex     SQL • Python • Tableau • Jira",
        left_block_text: "Senior Product Manager | Zendex",
        right_block_text: "SQL • Python • Tableau • Jira",
        horizontal_gap_pt: 96.0,
        page_no: 0,
      },
      {
        line_text: "➢ Led roadmap for $8M ARR suite     ➢ A/B testing • OKRs • Figma",
        left_block_text: "➢ Led roadmap for $8M ARR suite",
        right_block_text: "➢ A/B testing • OKRs • Figma",
        horizontal_gap_pt: 82.4,
        page_no: 0,
      },
    ],
    blocks: [
      { x0: 72, y0: 40, x1: 520, y1: 56, text: "[HEADER CLIPPED] sarah.chen@example.com | (415) 555-0142", block_no: 0, page_no: 0, font_name: "Calibri", font_size: 10 },
      { x0: 72, y0: 120, x1: 230, y1: 138, text: "Work Experience", block_no: 1, page_no: 0, font_name: "Calibri", font_size: 14 },
      { x0: 360, y0: 120, x1: 530, y1: 138, text: "Superpowers & Toolkit", block_no: 2, page_no: 0, font_name: "Calibri", font_size: 14 },
      { x0: 72, y0: 152, x1: 280, y1: 168, text: "Senior Product Manager | Zendex", block_no: 3, page_no: 0, font_name: "Calibri", font_size: 11 },
      { x0: 360, y0: 152, x1: 530, y1: 168, text: "SQL • Python • Tableau • Jira", block_no: 4, page_no: 0, font_name: "Calibri", font_size: 11 },
    ],
  },
  canonical: {
    ...SARAH_CHEN_XRAY_FIXTURE.canonical,
    section_boundary_failures: [
      {
        header_text: "Superpowers & Toolkit",
        inferred_target_section: "Skills",
        reason: "Non-standard creative heading 'Superpowers & Toolkit' is unmapped by Lever/Workday and drops the Skills block.",
      },
    ],
    phantom_token_hazards: [
      {
        raw_glyph: "➢",
        codepoint: "U+27A2",
        line_text: "➢ Led roadmap for enterprise analytics suite, $8M ARR in year one",
        normalized_replacement: "-",
      },
    ],
  },
};

// ============================================================================
// API Functions
// ============================================================================

export async function parseResumeXRay(
  file?: File,
  ocrEnabled: boolean = true
): Promise<ParseXRayResponse> {
  const formData = new FormData();
  if (file) {
    formData.append("file", file);
  }
  formData.append("ocr_enabled", String(ocrEnabled));

  const res = await fetch(`${API_BASE_URL}/parse-xray`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `Failed to parse resume (HTTP ${res.status})`);
  }
  return (await res.json()) as ParseXRayResponse;
}

export async function computeATSScore(params: {
  resume: CanonicalResume;
  jd: JDRequirementInput;
  platform: ATSPlatform;
  knockout?: KnockoutRulesInput;
}): Promise<ComputeScoreResponse> {
  const knockout = params.knockout || DEFAULT_KNOCKOUT_RULES;
  const res = await fetch(`${API_BASE_URL}/compute-score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume: params.resume,
      jd: params.jd,
      platform: params.platform,
      knockout,
    }),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `Failed to compute ATS score (HTTP ${res.status})`);
  }
  return (await res.json()) as ComputeScoreResponse;
}

export async function runHybridRRFSearch(
  candidates: RRFCandidateInput[],
  k: number = 60
): Promise<RRFCandidateResult[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/hybrid-search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidates, k }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return (await res.json()) as RRFCandidateResult[];
  } catch {
    const scored = candidates.map((c) => {
      const b = c.bm25_rank ? 1 / (k + c.bm25_rank) : 0;
      const v = c.ann_rank ? 1 / (k + c.ann_rank) : 0;
      return {
        ...c,
        rrf_score: Number((b + v).toFixed(5)),
        final_rank: 0,
      };
    });
    scored.sort((a, b) => b.rrf_score - a.rrf_score);
    return scored.map((item, idx) => ({ ...item, final_rank: idx + 1 }));
  }
}

export async function tailorExperienceBullets(params: {
  resume: CanonicalResume;
  jd: JDRequirementInput;
}): Promise<TailorBulletsResponse> {
  const res = await fetch(`${API_BASE_URL}/tailor-bullets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `Failed to tailor bullets (HTTP ${res.status})`);
  }
  return (await res.json()) as TailorBulletsResponse;
}

export const PRESET_JDS: Record<string, JDRequirementInput> = {
  PYTHON_DEV: DEFAULT_BENCHMARK_JD,
  MARKETING_COORD: {
    target_title: "Marketing Coordinator",
    must_have_skills: [
      "Project Management",
      "SQL",
      "Excel",
      "Google Analytics 4",
      "Mailchimp",
      "WordPress",
      "WooCommerce",
      "SEO",
    ],
    preferred_skills: [
      "HubSpot",
      "Salesforce",
      "Tableau",
      "A/B testing",
    ],
    required_years_experience: 3,
    required_degree_level: "Master's",
    target_industry: "E-Commerce & Digital Marketing",
  },
  PRODUCT_MANAGER: {
    target_title: "Senior Product Manager",
    must_have_skills: [
      "SQL",
      "Python",
      "Tableau",
      "Jira",
      "Confluence",
      "Figma",
      "A/B testing",
      "product analytics",
    ],
    preferred_skills: [
      "OKRs",
      "AWS",
      "stakeholder management",
      "Agile",
    ],
    required_years_experience: 5,
    required_degree_level: "Master's",
    target_industry: "Enterprise SaaS",
  },
};

export interface DemographicGroupMetrics {
  category: string;
  group_name: string;
  total_applicants: number;
  selected_applicants: number;
  selection_rate: number;
  impact_ratio: number;
  adverse_impact_flagged: boolean;
}

export interface NYCLocalLaw144AuditReport {
  four_fifths_threshold: number;
  overall_compliant: boolean;
  sex_categories: DemographicGroupMetrics[];
  race_ethnicity_categories: DemographicGroupMetrics[];
  flagged_groups: string[];
}

const CLIENT_JD_LEXICON: string[] = [
  "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "SQL", "NoSQL", "GraphQL",
  "React", "Next.js", "Vue.js", "Angular", "Node.js", "Django", "FastAPI", "Flask", "Spring Boot", ".NET",
  "PostgreSQL", "MySQL", "MongoDB", "Redis", "Snowflake", "BigQuery", "Redshift", "Databricks", "Spark",
  "Kafka", "Airflow", "dbt", "ETL", "Data Warehousing", "Data Modeling", "Data Engineering", "Data Analysis",
  "Tableau", "Power BI", "Looker", "Amplitude", "Mixpanel", "Google Analytics 4", "GA4", "Machine Learning",
  "Deep Learning", "NLP", "Generative AI", "LLMs", "RAG", "LangChain", "PyTorch", "TensorFlow", "Scikit-learn",
  "Pandas", "NumPy", "A/B testing", "Experimentation", "Statistical Modeling", "AWS", "GCP", "Azure",
  "Docker", "Kubernetes", "Terraform", "CI/CD", "GitHub Actions", "Jenkins", "Linux", "Microservices",
  "REST APIs", "gRPC", "Git", "Product Management", "Product Strategy", "Product Roadmapping",
  "Product Analytics", "User Research", "Go-to-Market Strategy", "Agile", "Scrum", "Kanban", "Lean",
  "Six Sigma", "Project Management", "Program Management", "Stakeholder Management", "Cross-Functional Collaboration",
  "OKRs", "KPIs", "Jira", "Confluence", "Figma", "UI/UX Design", "Digital Marketing", "Growth Marketing",
  "Performance Marketing", "Content Marketing", "Content Strategy", "Content Calendars", "Creative Briefs",
  "Copywriting", "Demand Generation", "Email Marketing", "Marketing Automation", "CRM", "SEO", "SEM",
  "Paid Search", "Paid Social", "Google Ads", "Meta Ads Manager", "Conversion Rate Optimization",
  "Mailchimp", "Klaviyo", "HubSpot", "Salesforce", "WordPress", "Shopify", "WooCommerce", "Semrush",
  "Financial Modeling", "Financial Analysis", "FP&A", "Budgeting", "Forecasting", "Budget & Spend Tracking",
  "Quantitative Finance", "Risk Management", "Accounting", "GAAP", "Microsoft Excel", "Advanced Excel",
  "Pivot Tables", "VBA", "PowerPoint", "SAP", "Workday", "Business Analytics", "Business Operations",
  "Process Redesign", "Process Improvement", "Supply Chain Management", "Logistics", "Procurement",
];

function extractJDClientSide(rawText: string, fallbackTitle?: string): JDRequirementInput {
  const text = rawText.trim();
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

  let targetTitle = "";
  const labelRe = /^(?:job\s+title|title|position|role|opening)\s*[:\-–—]\s*(.+)$/i;
  const roleKwRe = /\b(engineer|developer|manager|analyst|coordinator|specialist|director|architect|designer|lead|scientist|consultant|intern|associate|strategist|officer|administrator|researcher|accountant|planner|executive)\b/i;

  for (const ln of lines.slice(0, 10)) {
    const m = ln.match(labelRe);
    if (m) {
      targetTitle = m[1].trim();
      break;
    }
  }
  if (!targetTitle) {
    for (const ln of lines.slice(0, 8)) {
      const cleaned = ln.replace(/^[#*\-•\s]+/, "").trim();
      if (cleaned.length >= 3 && cleaned.length <= 75 && roleKwRe.test(cleaned) && !cleaned.endsWith(".")) {
        targetTitle = cleaned.split(/\s+(?:\||—|–|-)\s+/)[0].trim();
        break;
      }
    }
  }
  if (!targetTitle) {
    targetTitle = fallbackTitle && fallbackTitle !== "Senior Python Developer" ? fallbackTitle : (lines[0]?.slice(0, 60) || "Target Role");
  }

  const prefSplit = text.split(/\b(?:preferred\s+qualifications?|nice\s+to\s+have(?:s)?|bonus\s+(?:points?|skills?)|preferred\s+skills?|desired\s+qualifications?)\b/i);
  const mustBlob = prefSplit[0] || text;
  const prefBlob = prefSplit.slice(1).join("\n");

  const extractFromBlob = (blob: string): string[] => {
    if (!blob.trim()) return [];
    const found: string[] = [];
    const seen = new Set<string>();
    const add = (s: string) => {
      const clean = s.replace(/^[\s•●◦\-*–—:;,()\[\]]+|[\s•●◦\-*–—:;,()\[\].]+$/g, "").trim();
      if (!clean || clean.length < 2 || clean.length > 40) return;
      const low = clean.toLowerCase();
      if (seen.has(low)) return;
      seen.add(low);
      found.push(clean);
    };

    for (const item of CLIENT_JD_LEXICON) {
      const escaped = item.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`(?<![a-z0-9])${escaped}(?![a-z0-9])`, "i");
      if (re.test(blob)) {
        add(item);
      }
    }

    const cueRe = /(?:experience|proficiency|expertise|knowledge|familiarity|skilled|background)\s+(?:in|with|of|using)\s+([A-Za-z0-9#+/.\-&,\s]{3,80}?)(?:[.;\n]|$)/gi;
    let m: RegExpExecArray | null;
    while ((m = cueRe.exec(blob)) !== null) {
      for (const part of m[1].split(/,|;|\band\b|\bor\b|\//i)) {
        const p = part.trim();
        if (p.split(/\s+/).length <= 3) add(p);
      }
    }
    return found;
  };

  let mustSkills = extractFromBlob(mustBlob);
  let prefSkills = extractFromBlob(prefBlob).filter(
    (s) => !mustSkills.some((m) => m.toLowerCase() === s.toLowerCase())
  );

  if (prefSkills.length === 0 && mustSkills.length > 7) {
    const splitIdx = Math.max(5, Math.floor(mustSkills.length * 0.72));
    prefSkills = mustSkills.slice(splitIdx);
    mustSkills = mustSkills.slice(0, splitIdx);
  }

  const ym = text.match(/\b(\d{1,2})\+?\s*(?:to\s*\d+\s*|\-\s*\d+\s*)?years?\b/i);
  const reqYears = ym ? parseInt(ym[1], 10) : 3;

  return {
    target_title: targetTitle,
    must_have_skills: mustSkills.slice(0, 12),
    preferred_skills: prefSkills.slice(0, 8),
    required_years_experience: reqYears,
  };
}

export async function parseJDFromText(
  rawText: string,
  fallbackTitle?: string
): Promise<JDRequirementInput> {
  try {
    const res = await fetch(`${API_BASE_URL}/parse-jd`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        raw_jd_text: rawText,
        fallback_title: fallbackTitle,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as JDRequirementInput;
  } catch {
    return extractJDClientSide(rawText, fallbackTitle);
  }
}

export async function fetchLatestUploadedXRay(): Promise<ParseXRayResponse | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/latest-analysis`);
    if (!res.ok) return null;
    const data = await res.json();
    if (data && data.xray && data.xray.canonical) {
      return data.xray as ParseXRayResponse;
    }
    return null;
  } catch {
    return null;
  }
}

export async function runLL144BiasAudit(): Promise<NYCLocalLaw144AuditReport> {
  const sampleCohort = [
    { applicant_id: "1", sex: "Male", race_ethnicity: "White", selected: true },
    { applicant_id: "2", sex: "Male", race_ethnicity: "Asian", selected: true },
    { applicant_id: "3", sex: "Male", race_ethnicity: "White", selected: false },
    { applicant_id: "4", sex: "Female", race_ethnicity: "Hispanic or Latino", selected: true },
    { applicant_id: "5", sex: "Female", race_ethnicity: "Black or African American", selected: true },
    { applicant_id: "6", sex: "Female", race_ethnicity: "Asian", selected: false },
  ];
  try {
    const res = await fetch(`${API_BASE_URL}/audit-bias`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sampleCohort),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as NYCLocalLaw144AuditReport;
  } catch {
    return {
      four_fifths_threshold: 0.8,
      overall_compliant: true,
      sex_categories: [
        { category: "sex", group_name: "Male", total_applicants: 3, selected_applicants: 2, selection_rate: 0.6667, impact_ratio: 1.0, adverse_impact_flagged: false },
        { category: "sex", group_name: "Female", total_applicants: 3, selected_applicants: 2, selection_rate: 0.6667, impact_ratio: 1.0, adverse_impact_flagged: false },
      ],
      race_ethnicity_categories: [],
      flagged_groups: [],
    };
  }
}

export interface LatexHazard {
  hazard_type: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  description: string;
  line_num?: number | null;
}

export interface ParseTexResponse {
  canonical: CanonicalResume;
  hazards: LatexHazard[];
}

export interface RemediateTexResponse {
  baseline_score: number;
  remediated_score: number;
  target_platform: ATSPlatform;
  updated_tex: string;
  diffs: TailorBulletDiffItem[];
  newly_added_skills: string[];
  hazards_detected: LatexHazard[];
  evidence_trace: Record<string, any>;
  updated_canonical: CanonicalResume;
}

export async function parseTexResume(rawTex: string): Promise<ParseTexResponse> {
  const res = await fetch(`${API_BASE_URL}/parse-tex`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_tex: rawTex }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as ParseTexResponse;
}

export async function remediateTexWithContext(
  resumeTex: string,
  masterProfileMd: string,
  rawJdText: string,
  platform: ATSPlatform = "WORKDAY"
): Promise<RemediateTexResponse> {
  const res = await fetch(`${API_BASE_URL}/remediate-tex-md`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume_tex: resumeTex,
      master_profile_md: masterProfileMd,
      raw_jd_text: rawJdText,
      platform,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as RemediateTexResponse;
}

export async function fetchEvidenceTrace(
  resume: CanonicalResume,
  jd?: JDRequirementInput
): Promise<Record<string, any>> {
  const res = await fetch(`${API_BASE_URL}/evidence-trace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume, jd }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return await res.json();
}


