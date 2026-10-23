"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Briefcase,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Eye,
  FileText,
  GitCompare,
  Kanban,
  Layers,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
  Upload,
  UserCheck,
} from "lucide-react";
import ParserXRay from "@/components/ParserXRay";
import DiagnosticDashboard from "@/components/DiagnosticDashboard";
import TailoringStudio from "@/components/TailoringStudio";
import KanbanBoard from "@/components/KanbanBoard";
import {
  ATSPlatform,
  ComputeScoreResponse,
  DEFAULT_KNOCKOUT_RULES,
  JDRequirementInput,
  KnockoutRulesInput,
  PRESET_JDS,
  ParseXRayResponse,
  RRFCandidateResult,
  SARAH_CHEN_XRAY_FIXTURE,
  TailorBulletDiffItem,
  TailorBulletsResponse,
  computeATSScore,
  parseJDFromText,
  runHybridRRFSearch,
  tailorExperienceBullets,
  parseResumeXRay,
} from "@/services/api";

type StudioView = "XRAY" | "DIAGNOSTIC" | "TAILOR" | "KANBAN";

const EMPTY_JD: JDRequirementInput = {
  target_title: "",
  must_have_skills: [],
  preferred_skills: [],
  required_years_experience: 3,
};

const WORKFLOW_STEPS: {
  id: StudioView;
  step: string;
  title: string;
}[] = [
  {
    id: "XRAY",
    step: "01",
    title: "Parser X-Ray & Ingestion",
  },
  {
    id: "DIAGNOSTIC",
    step: "02",
    title: "Diagnostic & 30-Pt Audit",
  },
  {
    id: "TAILOR",
    step: "03",
    title: "Diff Editor & Safe Export",
  },
  {
    id: "KANBAN",
    step: "04",
    title: "Application Pipeline",
  },
];

export default function GlassBoxStudioPage() {
  const [activeView, setActiveView] = useState<StudioView>("XRAY");
  const [selectedPlatform, setSelectedPlatform] =
    useState<ATSPlatform>("WORKDAY");

  // Starts completely empty until the user uploads a resume and provides a JD
  const [xrayData, setXRayData] = useState<ParseXRayResponse | null>(null);
  const [jd, setJd] = useState<JDRequirementInput>(EMPTY_JD);

  // Onboarding Launchpad State
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState<boolean>(false);
  const [rawJdText, setRawJdText] = useState<string>("");
  const [mustHaveInput, setMustHaveInput] = useState<string>("");
  const [preferredInput, setPreferredInput] = useState<string>("");
  const [isRunningLaunchpad, setIsRunningLaunchpad] = useState<boolean>(false);
  const [launchpadError, setLaunchpadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [isJdDrawerOpen, setIsJdDrawerOpen] = useState<boolean>(false);
  const [isParsingJd, setIsParsingJd] = useState<boolean>(false);

  const [knockoutRules, setKnockoutRules] = useState<KnockoutRulesInput>(
    DEFAULT_KNOCKOUT_RULES
  );
  const [scoreData, setScoreData] = useState<ComputeScoreResponse | null>(null);
  const [rrfResults, setRrfResults] = useState<RRFCandidateResult[]>([]);
  const [tailorData, setTailorData] = useState<TailorBulletsResponse | null>(
    null
  );

  // Sync score, 30-parameter audit, RRF tournament, and tailored bullets when xrayData or JD changes
  useEffect(() => {
    if (!xrayData) {
      setScoreData(null);
      setTailorData(null);
      return;
    }

    let active = true;

    async function refreshDiagnostics(currentXRay: ParseXRayResponse) {
      const canonicalWithExt = {
        ...currentXRay.canonical,
        extraction_result: currentXRay.extraction,
      };

      const [computedScore, rrfRankings, tailored] = await Promise.all([
        computeATSScore({
          resume: canonicalWithExt,
          jd,
          platform: selectedPlatform,
          knockout: knockoutRules,
        }),
        runHybridRRFSearch(
          [
            {
              candidate_id: "cand_a",
              candidate_name: "Candidate A (Keyword Stuffer)",
              bm25_rank: 1,
              ann_rank: 50,
            },
            {
              candidate_id: "cand_b",
              candidate_name: "Candidate B (Consensus Match)",
              bm25_rank: 3,
              ann_rank: 3,
            },
            {
              candidate_id: "cand_c",
              candidate_name: "Candidate C (Semantic Outlier)",
              bm25_rank: 10,
              ann_rank: 1,
            },
          ],
          60
        ),
        tailorExperienceBullets({
          resume: canonicalWithExt,
          jd,
        }),
      ]);

      if (!active) return;
      setScoreData(computedScore);
      setRrfResults(rrfRankings);
      setTailorData(tailored);
    }

    refreshDiagnostics(xrayData);
    return () => {
      active = false;
    };
  }, [xrayData, selectedPlatform, jd, knockoutRules]);

  const handleSelectPresetJd = (presetKey: string) => {
    const preset = PRESET_JDS[presetKey];
    if (!preset) return;
    setJd(preset);
    setMustHaveInput(preset.must_have_skills.join(", "));
    setPreferredInput(preset.preferred_skills.join(", "));
  };

  const handleResetToEmpty = () => {
    setXRayData(null);
    setStagedFile(null);
    setJd(EMPTY_JD);
    setRawJdText("");
    setMustHaveInput("");
    setPreferredInput("");
    setScoreData(null);
    setTailorData(null);
    setLaunchpadError(null);
    setIsJdDrawerOpen(false);
    setActiveView("XRAY");
  };

  const handleLoadSarahChenBenchmark = () => {
    const pyPreset = PRESET_JDS.PYTHON_DEV;
    setJd(pyPreset);
    setMustHaveInput(pyPreset.must_have_skills.join(", "));
    setPreferredInput(pyPreset.preferred_skills.join(", "));
    setXRayData(SARAH_CHEN_XRAY_FIXTURE);
    setActiveView("DIAGNOSTIC");
  };

  const handleApplyManualJdEdits = () => {
    const mustList = mustHaveInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const prefList = preferredInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setJd((prev) => ({
      ...prev,
      must_have_skills: mustList,
      preferred_skills: prefList,
    }));
  };

  const handleParsePastedJd = async () => {
    if (!rawJdText.trim()) return;
    setIsParsingJd(true);
    try {
      const parsed = await parseJDFromText(
        rawJdText,
        jd.target_title || "Target Role"
      );
      setJd(parsed);
      setMustHaveInput(parsed.must_have_skills.join(", "));
      setPreferredInput(parsed.preferred_skills.join(", "));
    } finally {
      setIsParsingJd(false);
    }
  };

  const handleRunFullAnalysis = async () => {
    if (!stagedFile) {
      setLaunchpadError("Please select or drop your Resume (.pdf, .docx, or .txt) first.");
      return;
    }

    setLaunchpadError(null);
    setIsRunningLaunchpad(true);
    try {
      // 1. Parse or construct JD requirements
      let activeJd: JDRequirementInput = {
        ...jd,
        must_have_skills: mustHaveInput
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        preferred_skills: preferredInput
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };

      if (rawJdText.trim() && activeJd.must_have_skills.length === 0) {
        activeJd = await parseJDFromText(
          rawJdText,
          activeJd.target_title || undefined
        );
        setMustHaveInput(activeJd.must_have_skills.join(", "));
        setPreferredInput(activeJd.preferred_skills.join(", "));
      }

      if (!activeJd.target_title.trim()) {
        activeJd.target_title = "Target Role";
      }

      setJd(activeJd);

      // 2. Upload and run Dual-Stream X-Ray ingestion on the resume
      const parsedXRay = await parseResumeXRay(stagedFile, true);
      setXRayData(parsedXRay);
      setActiveView("DIAGNOSTIC");
    } catch (err) {
      setLaunchpadError(
        err instanceof Error ? err.message : "Failed to analyze resume."
      );
    } finally {
      setIsRunningLaunchpad(false);
    }
  };

  const handleApproveBullet = (diff: TailorBulletDiffItem) => {
    setXRayData((prev) => {
      if (!prev) return prev;
      const updatedEmployments = prev.canonical.employments.map((emp) => {
        if (emp.company !== diff.company) return emp;
        return {
          ...emp,
          bullets: emp.bullets.map((b) =>
            b === diff.original_bullet ? diff.tailored_bullet : b
          ),
        };
      });

      return {
        ...prev,
        canonical: {
          ...prev.canonical,
          employments: updatedEmployments,
        },
      };
    });
  };

  const handleRegenerateTailoring = async () => {
    if (!xrayData) return;
    const refreshed = await tailorExperienceBullets({
      resume: xrayData.canonical,
      jd,
    });
    setTailorData(refreshed);
  };

  const totalScore = scoreData?.score_breakdown.total_score;
  const parseRatioPct = Math.round(
    (scoreData?.score_breakdown.parse_success_ratio ?? 1.0) * 100
  );
  const auditPassed = scoreData?.audit_report.passed_count ?? 0;
  const auditTotal = scoreData?.audit_report.total_parameters ?? 30;
  const kwMatchPct = Math.round(
    (scoreData?.score_breakdown.keyword_match_pct ?? 0.0) * 100
  );

  return (
    <div className="min-h-screen flex flex-col bg-engineering-grid text-slate-100">
      {/* Top Executive Navigation & Telemetry Header */}
      <header className="sticky top-0 z-40 border-b border-white/[0.08] bg-slate-950/85 backdrop-blur-xl shadow-2xl shadow-black/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-4">
          {/* Brand Identity */}
          <div className="flex items-center gap-3.5">
            <div className="relative group">
              <div className="absolute -inset-0.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-500 opacity-50 blur-sm group-hover:opacity-80 transition" />
              <div className="relative p-2.5 rounded-xl bg-slate-950 border border-white/15 text-cyan-400">
                <Cpu className="w-5 h-5" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-base sm:text-lg font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                  Glass-Box ATS Studio
                </h1>
                <span className="hidden md:inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/25">
                  <ShieldCheck className="w-3 h-3" />
                  Clean-Room Deterministic v1.0
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Multi-Platform Ingestion Telemetry, 30-Parameter Auditor &amp;
                Zero-Hallucination Remediation
              </p>
            </div>
          </div>

          {/* Live Executive Telemetry Strip (Visible once a resume is analyzed) */}
          {xrayData && scoreData && (
            <div className="hidden xl:flex items-center gap-2 bg-slate-900/90 border border-white/[0.07] rounded-xl px-3 py-1.5">
              <div className="flex items-center gap-2 pr-3 border-r border-slate-800">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                  {selectedPlatform} Score
                </span>
                <span className="text-sm font-bold font-mono text-cyan-300">
                  {totalScore !== null && totalScore !== undefined
                    ? `${totalScore.toFixed(1)}`
                    : "Human Mode"}
                </span>
              </div>

              <div className="flex items-center gap-2 px-2 border-r border-slate-800">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                  JD Match
                </span>
                <span
                  className={`text-xs font-bold font-mono px-1.5 py-0.5 rounded ${
                    kwMatchPct >= 75 && kwMatchPct < 90
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-amber-500/15 text-amber-300"
                  }`}
                >
                  {kwMatchPct}%
                </span>
              </div>

              <div className="flex items-center gap-2 px-2 border-r border-slate-800">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                  Parse Integrity
                </span>
                <span className="text-xs font-bold font-mono text-emerald-300">
                  {parseRatioPct}%
                </span>
              </div>

              <div className="flex items-center gap-2 pl-2">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                  30-Pt Audit
                </span>
                <span
                  className={`text-xs font-bold font-mono px-1.5 py-0.5 rounded ${
                    auditPassed === auditTotal
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-indigo-500/15 text-indigo-300"
                  }`}
                >
                  {auditPassed}/{auditTotal}
                </span>
              </div>
            </div>
          )}

          {/* Header Action Controls */}
          <div className="flex items-center gap-2">
            {xrayData ? (
              <>
                <button
                  type="button"
                  onClick={() => setIsJdDrawerOpen((prev) => !prev)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${
                    isJdDrawerOpen
                      ? "bg-cyan-500/20 text-cyan-200 border-cyan-500/40 shadow-lg shadow-cyan-500/10"
                      : "bg-slate-900/90 hover:bg-slate-800 text-slate-200 border-white/10"
                  }`}
                >
                  <Target className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Target JD: {jd.target_title || "Not Set"}</span>
                  <span className="px-1.5 py-0.5 rounded-md bg-cyan-500/15 text-cyan-300 font-mono text-[10px]">
                    {jd.must_have_skills.length} Must
                  </span>
                  {isJdDrawerOpen ? (
                    <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleResetToEmpty}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-900 hover:bg-rose-500/15 text-slate-300 hover:text-rose-300 border border-white/10 hover:border-rose-500/30 transition"
                  title="Clear current resume and start a new ATS test"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  New ATS Test
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={handleLoadSarahChenBenchmark}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 hover:bg-slate-800 text-slate-300 border border-white/10 transition"
              >
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                Load Demo Benchmark
              </button>
            )}
          </div>
        </div>

        {/* Sub-Bar: Active Candidate & 4-Step Studio Pipeline (Shown when a session is active) */}
        {xrayData && (
          <div className="border-t border-white/[0.06] bg-slate-950/60">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-white/[0.07] text-slate-300">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-slate-400">Active Resume:</span>
                  <strong className="text-white font-semibold">
                    {xrayData.canonical.full_name}
                  </strong>
                  <span className="text-[11px] font-mono text-slate-500">
                    ({xrayData.filename})
                  </span>
                </span>
              </div>

              <nav className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-white/[0.07]">
                {WORKFLOW_STEPS.map((item, idx) => {
                  const isActive = activeView === item.id;
                  const Icon =
                    item.id === "XRAY"
                      ? Eye
                      : item.id === "DIAGNOSTIC"
                      ? Activity
                      : item.id === "TAILOR"
                      ? GitCompare
                      : Kanban;

                  return (
                    <React.Fragment key={item.id}>
                      <button
                        type="button"
                        onClick={() => setActiveView(item.id)}
                        className={`group relative px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
                          isActive
                            ? "bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-md shadow-cyan-500/20"
                            : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"
                        }`}
                      >
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                            isActive
                              ? "bg-black/25 text-cyan-200"
                              : "bg-slate-800 text-slate-400 group-hover:text-slate-200"
                          }`}
                        >
                          {item.step}
                        </span>
                        <Icon className="w-3.5 h-3.5" />
                        <span>{item.title}</span>
                      </button>
                      {idx < WORKFLOW_STEPS.length - 1 && (
                        <ArrowRight className="w-3 h-3 text-slate-700 hidden sm:block" />
                      )}
                    </React.Fragment>
                  );
                })}
              </nav>
            </div>
          </div>
        )}

        {/* Collapsible Target Job Description (JD) Configuration Drawer (During active session) */}
        {xrayData && isJdDrawerOpen && (
          <div className="border-t border-white/10 bg-slate-900/95 backdrop-blur-xl shadow-2xl">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Briefcase className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                    Target Job Description (JD) Configuration
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400">Presets:</span>
                  <button
                    type="button"
                    onClick={() => handleSelectPresetJd("MARKETING_COORD")}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-950 text-slate-300 border border-slate-800 hover:border-cyan-500/40"
                  >
                    Marketing Coordinator
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSelectPresetJd("PYTHON_DEV")}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-950 text-slate-300 border border-slate-800 hover:border-cyan-500/40"
                  >
                    Senior Python Developer
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSelectPresetJd("PRODUCT_MANAGER")}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-950 text-slate-300 border border-slate-800 hover:border-cyan-500/40"
                  >
                    Senior Product Manager
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-5 bg-slate-950/90 border border-white/[0.08] rounded-xl p-3.5 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-200">
                      Paste Raw Job Description Text
                    </label>
                    <button
                      type="button"
                      onClick={handleParsePastedJd}
                      disabled={isParsingJd || !rawJdText.trim()}
                      className="px-3 py-1 rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 text-white text-xs font-semibold flex items-center gap-1.5 disabled:opacity-40"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      {isParsingJd ? "Extracting..." : "Auto-Extract JD"}
                    </button>
                  </div>
                  <textarea
                    rows={3}
                    value={rawJdText}
                    onChange={(e) => setRawJdText(e.target.value)}
                    placeholder="Paste job description text to re-extract skills..."
                    className="w-full rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="lg:col-span-7 bg-slate-950/90 border border-white/[0.08] rounded-xl p-3.5 space-y-2.5">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div className="sm:col-span-2">
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Target Role Title
                      </label>
                      <input
                        type="text"
                        value={jd.target_title}
                        onChange={(e) =>
                          setJd((prev) => ({
                            ...prev,
                            target_title: e.target.value,
                          }))
                        }
                        className="w-full rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Required Experience (Yrs)
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={20}
                        value={jd.required_years_experience ?? 3}
                        onChange={(e) =>
                          setJd((prev) => ({
                            ...prev,
                            required_years_experience:
                              Number(e.target.value) || 0,
                          }))
                        }
                        className="w-full rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Must-Have Skills (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={mustHaveInput}
                        onChange={(e) => setMustHaveInput(e.target.value)}
                        onBlur={handleApplyManualJdEdits}
                        className="w-full rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-emerald-300 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Preferred Skills (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={preferredInput}
                        onChange={(e) => setPreferredInput(e.target.value)}
                        onBlur={handleApplyManualJdEdits}
                        className="w-full rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-xs text-cyan-300 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </header>

      {/* Main Studio Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
        {!xrayData ? (
          /* ==================================================================
             CLEAN EMPTY-STATE LAUNCHPAD: 1. Feed JD + 2. Upload Resume PDF
             ================================================================== */
          <div className="max-w-5xl mx-auto space-y-8 py-4">
            {/* Hero Header */}
            <div className="text-center space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                Clean-Room ATS Ingestion &amp; 30-Point Diagnostic Studio
              </div>
              <h2 className="text-2xl sm:text-4xl font-bold tracking-tight text-white">
                Test Your Resume Against Real Enterprise ATS Engines
              </h2>
              <p className="text-sm text-slate-400 max-w-2xl mx-auto">
                Provide your target Job Description and upload your resume (
                <code className="text-cyan-300">.pdf</code>,{" "}
                <code className="text-cyan-300">.docx</code>, or{" "}
                <code className="text-cyan-300">.txt</code>) to run the
                Dual-Stream Parser X-Ray, 5-Platform Schema Emulators, and
                30-Parameter Audit.
              </p>
            </div>

            {/* 2-Column Input Cards */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Step 1: Target Job Description Input */}
              <div className="lg:col-span-7 bg-slate-900/75 border border-white/10 rounded-2xl p-6 shadow-2xl space-y-4 flex flex-col justify-between">
                <div className="space-y-4">
                  <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                    <div className="flex items-center gap-2.5">
                      <span className="w-6 h-6 rounded-lg bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 font-mono text-xs font-bold flex items-center justify-center">
                        1
                      </span>
                      <div>
                        <h3 className="text-sm font-bold text-white">
                          Target Job Description (JD)
                        </h3>
                        <p className="text-[11px] text-slate-400">
                          Paste the raw job posting or configure role skills
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleSelectPresetJd("MARKETING_COORD")}
                        className="px-2 py-1 rounded-md text-[11px] bg-slate-950 hover:bg-slate-800 text-slate-300 border border-white/10 transition"
                      >
                        Marketing Preset
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSelectPresetJd("PYTHON_DEV")}
                        className="px-2 py-1 rounded-md text-[11px] bg-slate-950 hover:bg-slate-800 text-slate-300 border border-white/10 transition"
                      >
                        Python Preset
                      </button>
                    </div>
                  </div>

                  {/* Paste Raw JD Textarea */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-medium text-slate-300">
                        Paste Job Description Text
                      </label>
                      <button
                        type="button"
                        onClick={handleParsePastedJd}
                        disabled={isParsingJd || !rawJdText.trim()}
                        className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 disabled:opacity-40 flex items-center gap-1"
                      >
                        <Sparkles className="w-3 h-3" />
                        {isParsingJd
                          ? "Extracting Skills..."
                          : "Extract Skills from Text"}
                      </button>
                    </div>
                    <textarea
                      rows={4}
                      value={rawJdText}
                      onChange={(e) => setRawJdText(e.target.value)}
                      placeholder="Paste the full job description here... (If you don't click 'Extract Skills', they will be extracted automatically when you run the test)."
                      className="w-full rounded-xl bg-slate-950/90 border border-slate-800 px-3.5 py-2.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  {/* Extracted / Editable Target Title & Skills */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="sm:col-span-2">
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Target Role Title
                      </label>
                      <input
                        type="text"
                        value={jd.target_title}
                        onChange={(e) =>
                          setJd((prev) => ({
                            ...prev,
                            target_title: e.target.value,
                          }))
                        }
                        placeholder="e.g., Marketing Coordinator or Senior Python Developer"
                        className="w-full rounded-xl bg-slate-950/90 border border-slate-800 px-3 py-2 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Required Years
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={20}
                        value={jd.required_years_experience ?? 3}
                        onChange={(e) =>
                          setJd((prev) => ({
                            ...prev,
                            required_years_experience:
                              Number(e.target.value) || 0,
                          }))
                        }
                        className="w-full rounded-xl bg-slate-950/90 border border-slate-800 px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Must-Have Skills (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={mustHaveInput}
                        onChange={(e) => setMustHaveInput(e.target.value)}
                        onBlur={handleApplyManualJdEdits}
                        placeholder="e.g., SQL, Google Analytics 4, Excel"
                        className="w-full rounded-xl bg-slate-950/90 border border-slate-800 px-3 py-2 text-xs text-emerald-300 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">
                        Preferred Skills (comma-separated)
                      </label>
                      <input
                        type="text"
                        value={preferredInput}
                        onChange={(e) => setPreferredInput(e.target.value)}
                        onBlur={handleApplyManualJdEdits}
                        placeholder="e.g., WordPress, HubSpot, Salesforce"
                        className="w-full rounded-xl bg-slate-950/90 border border-slate-800 px-3 py-2 text-xs text-cyan-300 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Step 2: Upload Resume PDF / DOCX */}
              <div className="lg:col-span-5 bg-slate-900/75 border border-white/10 rounded-2xl p-6 shadow-2xl flex flex-col justify-between space-y-5">
                <div className="space-y-4">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.07] pb-3">
                    <span className="w-6 h-6 rounded-lg bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 font-mono text-xs font-bold flex items-center justify-center">
                      2
                    </span>
                    <div>
                      <h3 className="text-sm font-bold text-white">
                        Upload Your Resume
                      </h3>
                      <p className="text-[11px] text-slate-400">
                        Native text-layer PDF, DOCX, or TXT (Max 10 MB)
                      </p>
                    </div>
                  </div>

                  {/* Dropzone */}
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDraggingFile(true);
                    }}
                    onDragLeave={() => setIsDraggingFile(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDraggingFile(false);
                      const dropped = e.dataTransfer.files?.[0];
                      if (dropped) {
                        setStagedFile(dropped);
                        setLaunchpadError(null);
                      }
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-all flex flex-col items-center justify-center min-h-[210px] ${
                      isDraggingFile
                        ? "border-cyan-400 bg-cyan-500/10"
                        : stagedFile
                        ? "border-emerald-500/50 bg-emerald-500/[0.06]"
                        : "border-slate-700/80 hover:border-cyan-500/50 bg-slate-950/60 hover:bg-slate-950"
                    }`}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.docx,.txt"
                      className="hidden"
                      onChange={(e) => {
                        const selected = e.target.files?.[0];
                        if (selected) {
                          setStagedFile(selected);
                          setLaunchpadError(null);
                        }
                      }}
                    />

                    {stagedFile ? (
                      <div className="space-y-2">
                        <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 flex items-center justify-center mx-auto">
                          <FileText className="w-6 h-6" />
                        </div>
                        <p className="text-sm font-bold text-emerald-300">
                          {stagedFile.name}
                        </p>
                        <p className="text-xs text-slate-400 font-mono">
                          {(stagedFile.size / 1024).toFixed(1)} KB • Ready for
                          Dual-Stream Ingestion
                        </p>
                        <span className="inline-block text-[11px] text-slate-400 underline pt-1">
                          Click to replace file
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-2.5">
                        <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-white/10 text-cyan-400 flex items-center justify-center mx-auto">
                          <Upload className="w-6 h-6" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-slate-200">
                            Drop your resume PDF here, or{" "}
                            <span className="text-cyan-400 underline">
                              browse
                            </span>
                          </p>
                          <p className="text-xs text-slate-500 mt-1">
                            Supports PDF (Stream A + B XY-Cut++), DOCX XML, and
                            TXT
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Error Alert */}
                {launchpadError && (
                  <div className="rounded-xl bg-rose-500/15 border border-rose-500/30 px-3.5 py-2.5 text-xs text-rose-200">
                    {launchpadError}
                  </div>
                )}

                {/* Primary CTA Button */}
                <button
                  type="button"
                  onClick={handleRunFullAnalysis}
                  disabled={isRunningLaunchpad || !stagedFile}
                  className="w-full py-3.5 px-5 rounded-xl bg-gradient-to-r from-cyan-500 via-cyan-600 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 disabled:opacity-40 text-white font-bold text-sm shadow-xl shadow-cyan-500/20 flex items-center justify-center gap-2 transition"
                >
                  <Play className="w-4 h-4 fill-current" />
                  {isRunningLaunchpad
                    ? "Running Dual-Stream X-Ray & 30-Point Audit..."
                    : "Run ATS Simulation & 30-Point Audit"}
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* ==================================================================
             ACTIVE 4-TAB STUDIO WORKSPACE
             ================================================================== */
          <>
            {activeView === "XRAY" && (
              <ParserXRay
                xrayData={xrayData}
                selectedPlatform={selectedPlatform}
                onSelectPlatform={setSelectedPlatform}
                onUpdateXRayData={setXRayData}
              />
            )}

            {activeView === "DIAGNOSTIC" && scoreData && (
              <DiagnosticDashboard
                scoreData={scoreData}
                selectedPlatform={selectedPlatform}
                knockoutRules={knockoutRules}
                onUpdateKnockoutRules={setKnockoutRules}
                rrfResults={rrfResults}
              />
            )}

            {activeView === "TAILOR" && tailorData && (
              <TailoringStudio
                resume={xrayData.canonical}
                jd={jd}
                tailorData={tailorData}
                onApproveBullet={handleApproveBullet}
                onRegenerateTailoring={handleRegenerateTailoring}
              />
            )}

            {activeView === "KANBAN" && (
              <KanbanBoard
                currentScore={scoreData?.score_breakdown.total_score ?? 82.0}
                currentJdMatchPct={
                  scoreData?.score_breakdown.keyword_match_pct ?? 80.0
                }
                currentPlatform={selectedPlatform}
                currentRoleTitle={jd.target_title || "Target Role"}
              />
            )}
          </>
        )}
      </main>

      {/* Subtle Executive Footer */}
      <footer className="border-t border-white/[0.06] bg-slate-950/80 py-3.5 px-4 sm:px-6 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-500">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>
              Engineered per{" "}
              <strong className="text-slate-400">ANTIGRAVITY_CONTEXT.md</strong>{" "}
              Clean-Room Specification • Zero LLM Scoring Variance
            </span>
          </div>
          <div className="flex items-center gap-4 font-mono">
            <span>Stream A: pdfminer.six (72pt Clip)</span>
            <span>•</span>
            <span>Stream B: PyMuPDF XY-Cut++</span>
            <span>•</span>
            <span>RRF: k=60</span>
            <span>•</span>
            <span>NYC LL144: IR &ge; 0.80</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
