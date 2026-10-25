"use client";

import React, { useEffect, useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Award,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Code2,
  Copy,
  Download,
  Eye,
  FileCode,
  FileText,
  FileUp,
  Flame,
  Layers,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  API_BASE_URL,
  ATSPlatform,
  CanonicalResume,
  ComputeScoreResponse,
  JDRequirementInput,
  LatexHazard,
  RecommendationItem,
  ResumeAuditReport,
  RetestLatexResponse,
  StructuredRecommendationsResponse,
  autoOptimizeLatexCode,
  fetchStructuredRecommendations,
  retestLatexCode,
} from "@/services/api";

const DEFAULT_SAMPLE_TEX = `\\documentclass[10pt,letterpaper]{article}
\\usepackage[margin=0.25in]{geometry}
\\usepackage{multicol}
\\usepackage{fontawesome5}
\\begin{document}
\\begin{center}
    {\\LARGE \\textbf{Alex Rivera}}\\\\
    \\faEnvelope\\ alex.rivera@example.com \\ $|$ \\ \\faPhone\\ (555) 019-4242 \\ $|$ \\ \\faLinkedin\\ linkedin.com/in/alexrivera
\\end{center}

\\begin{multicols}{2}
\\section{Experience}
\\textbf{Senior Cloud Architect} $|$ CloudOps Inc. \\hfill 2021 -- Present\\\\
\\begin{itemize}
    \\item Managed AWS cloud infrastructure using Terraform and Docker.
    \\item Improved API latency and helped scale backend microservices.
\\end{itemize}

\\section{Skills}
Python, AWS, Docker, Terraform
\\end{multicols}

\\section{Education}
\\textbf{B.S. in Computer Science} $|$ MIT \\hfill 2020
\\end{document}`;

interface LatexOptimizerStudioProps {
  resume: CanonicalResume;
  jd: JDRequirementInput;
  currentScore: number;
  auditReport: ResumeAuditReport;
  selectedPlatform: ATSPlatform;
  onSelectPlatform: (platform: ATSPlatform) => void;
  onUpdateCanonicalResume?: (updated: CanonicalResume) => void;
}

export default function LatexOptimizerStudio({
  resume,
  jd,
  currentScore,
  auditReport,
  selectedPlatform,
  onSelectPlatform,
  onUpdateCanonicalResume,
}: LatexOptimizerStudioProps) {
  // State for recommendations
  const [recommendationsData, setRecommendationsData] =
    useState<StructuredRecommendationsResponse | null>(null);
  const [isLoadingRecs, setIsLoadingRecs] = useState(false);

  // State for LaTeX code input
  const [rawTex, setRawTex] = useState<string>(DEFAULT_SAMPLE_TEX);
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedTex, setCopiedTex] = useState(false);
  const [showPromptPreview, setShowPromptPreview] = useState(false);

  // State for Retesting & PDF Production
  const [isRetesting, setIsRetesting] = useState(false);
  const [isAutoOptimizing, setIsAutoOptimizing] = useState(false);
  const [retestResult, setRetestResult] = useState<RetestLatexResponse | null>(
    null
  );
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);

  // Fetch structured recommendations when props change
  useEffect(() => {
    let isMounted = true;
    async function loadRecs() {
      if (!auditReport || !jd) return;
      setIsLoadingRecs(true);
      try {
        const resp = await fetchStructuredRecommendations(
          currentScore,
          auditReport,
          jd,
          resume,
          rawTex
        );
        if (isMounted) {
          setRecommendationsData(resp);
        }
      } catch (err) {
        console.error("Failed to load structured recommendations:", err);
      } finally {
        if (isMounted) setIsLoadingRecs(false);
      }
    }
    loadRecs();
    return () => {
      isMounted = false;
    };
  }, [currentScore, auditReport, jd, resume]);

  // Handle file upload of .tex file
  const handleTexUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setRawTex(text);
        // Refresh recommendations with uploaded latex
        fetchStructuredRecommendations(
          currentScore,
          auditReport,
          jd,
          resume,
          text
        ).then(setRecommendationsData);
      }
    };
    reader.readAsText(file);
  };

  // Copy structured LLM prompt
  const handleCopyPrompt = async () => {
    if (!recommendationsData?.structured_llm_prompt) return;
    await navigator.clipboard.writeText(recommendationsData.structured_llm_prompt);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2500);
  };

  // Copy raw LaTeX code
  const handleCopyTex = async () => {
    await navigator.clipboard.writeText(rawTex);
    setCopiedTex(true);
    setTimeout(() => setCopiedTex(false), 2000);
  };

  // Execute Re-test on current LaTeX code
  const handleRunRetest = async () => {
    setIsRetesting(true);
    setPdfPreviewUrl(null);
    try {
      const result = await retestLatexCode(
        rawTex,
        jd,
        selectedPlatform,
        currentScore
      );
      setRetestResult(result);
      if (onUpdateCanonicalResume) {
        onUpdateCanonicalResume(result.canonical_resume);
      }
      // Auto generate PDF preview
      generatePdfPreview(result.canonical_resume);
    } catch (err: any) {
      alert(`Re-test failed: ${err.message}`);
    } finally {
      setIsRetesting(false);
    }
  };

  // Execute In-App Auto-Optimization
  const handleAutoOptimize = async () => {
    setIsAutoOptimizing(true);
    setPdfPreviewUrl(null);
    try {
      const result = await autoOptimizeLatexCode(
        rawTex,
        jd,
        currentScore,
        auditReport,
        resume,
        selectedPlatform
      );
      setRetestResult(result);
      if (onUpdateCanonicalResume) {
        onUpdateCanonicalResume(result.canonical_resume);
      }
      // Generate PDF preview
      generatePdfPreview(result.canonical_resume);
    } catch (err: any) {
      alert(`Auto-optimization failed: ${err.message}`);
    } finally {
      setIsAutoOptimizing(false);
    }
  };

  // Generate in-browser PDF preview via export-pdf endpoint
  const generatePdfPreview = async (canonResume: CanonicalResume) => {
    setIsGeneratingPdf(true);
    try {
      const res = await fetch(`${API_BASE_URL}/export-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(canonResume),
      });
      if (!res.ok) throw new Error("PDF export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPdfPreviewUrl(url);
    } catch (err) {
      console.error("PDF generation preview failed:", err);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  // Download PDF file
  const handleDownloadPdf = async () => {
    const targetResume = retestResult?.canonical_resume || resume;
    try {
      const res = await fetch(`${API_BASE_URL}/export-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(targetResume),
      });
      if (!res.ok) throw new Error("PDF download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${targetResume.full_name.toLowerCase().replace(/\\s+/g, "_")}_ats_optimized.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("PDF download failed. Ensure backend server is running.");
    }
  };

  // Download .tex file
  const handleDownloadTex = () => {
    const blob = new Blob([rawTex], { type: "application/x-tex;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${resume.full_name.toLowerCase().replace(/\\s+/g, "_")}_ats_optimized.tex`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const currentUplift =
    retestResult != null
      ? retestResult.score_delta
      : recommendationsData
      ? recommendationsData.target_score_estimate - currentScore
      : 18.0;

  return (
    <div className="space-y-6">
      {/* Top Banner: Workflow Header & Platform Target Switcher */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-400" />
              Step 03: LaTeX Optimizer &amp; PDF Production Studio
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              Audit-Driven LLM Remediation
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Transform 30-Point Audit gaps into a structured LLM prompt, optimize LaTeX code, re-test against ATS scoring, and export clean-room PDF.
          </p>
        </div>

        {/* ATS Platform Switcher */}
        <div className="flex items-center gap-2 bg-slate-950 p-1.5 rounded-lg border border-slate-800">
          <span className="text-[11px] font-mono text-slate-400 pl-2">Platform:</span>
          {(["WORKDAY", "GREENHOUSE", "LEVER", "TALEO", "ICIMS"] as ATSPlatform[]).map(
            (p) => (
              <button
                key={p}
                type="button"
                onClick={() => onSelectPlatform(p)}
                className={`py-1.5 px-2.5 rounded text-xs font-semibold transition ${
                  selectedPlatform === p
                    ? "bg-indigo-600 text-white shadow"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {p}
              </button>
            )
          )}
        </div>
      </div>

      {/* PHASE 1: Structured Recommendations Card */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-base font-semibold text-white flex items-center gap-2">
              <Award className="w-5 h-5 text-cyan-400" />
              Diagnostic &amp; 30-Point Audit Structured Recommendations
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Specific, prioritized optimization checklist derived from your candidate scorecard
            </p>
          </div>

          {/* Score Uplift Gauge */}
          <div className="flex items-center gap-3">
            <div className="text-right">
              <span className="text-xs text-slate-400">Current Score</span>
              <p className="text-lg font-bold font-mono text-white">
                {currentScore.toFixed(1)} / 100
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-600" />
            <div className="text-right">
              <span className="text-xs text-emerald-400">Target Estimate</span>
              <p className="text-lg font-bold font-mono text-emerald-300">
                {recommendationsData?.target_score_estimate.toFixed(1) || "92.0"} / 100
              </p>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold font-mono flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5" />
              +{currentUplift.toFixed(1)} pts
            </div>
          </div>
        </div>

        {/* Missing Skills Highlights */}
        {recommendationsData && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {recommendationsData.must_have_missing.length > 0 && (
              <div className="p-3 rounded-lg bg-rose-950/20 border border-rose-500/30">
                <span className="font-semibold text-rose-300 flex items-center gap-1.5 mb-1.5">
                  <AlertOctagon className="w-4 h-4 text-rose-400" />
                  Missing Must-Have Skills (70% Weight Pool):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {recommendationsData.must_have_missing.map((s) => (
                    <span
                      key={s}
                      className="px-2 py-0.5 rounded bg-rose-900/40 text-rose-200 border border-rose-500/40 font-mono text-[11px]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {recommendationsData.preferred_missing.length > 0 && (
              <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-500/30">
                <span className="font-semibold text-amber-300 flex items-center gap-1.5 mb-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Missing Preferred Skills (30% Weight Pool):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {recommendationsData.preferred_missing.map((s) => (
                    <span
                      key={s}
                      className="px-2 py-0.5 rounded bg-amber-900/40 text-amber-200 border border-amber-500/40 font-mono text-[11px]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recommendation Action Cards List */}
        <div className="space-y-2.5">
          {recommendationsData?.recommendations.map((rec) => (
            <div
              key={rec.id}
              className={`p-3.5 rounded-xl border text-xs transition ${
                rec.priority === "CRITICAL"
                  ? "bg-rose-950/20 border-rose-500/40"
                  : rec.priority === "HIGH"
                  ? "bg-amber-950/20 border-amber-500/40"
                  : "bg-slate-950/70 border-slate-800"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                      rec.priority === "CRITICAL"
                        ? "bg-rose-500/30 text-rose-300 border border-rose-500/50"
                        : rec.priority === "HIGH"
                        ? "bg-amber-500/30 text-amber-300 border border-amber-500/50"
                        : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {rec.priority}
                  </span>
                  <span className="font-semibold text-slate-100">{rec.title}</span>
                </div>
                <span className="text-[11px] font-mono text-emerald-400 font-bold">
                  {rec.score_impact_estimate}
                </span>
              </div>
              <p className="text-slate-400 mb-1">{rec.problem_statement}</p>
              <div className="p-2 rounded bg-slate-950/80 border border-slate-800/80 text-[11px] text-slate-300 font-mono">
                <strong className="text-cyan-400 font-sans">Fix:</strong> {rec.actionable_instruction}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* PHASE 2 & 3: LaTeX Input, LLM Prompt Generator & Interactive Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: LaTeX Input & LLM Prompt Generator */}
        <div className="lg:col-span-6 flex flex-col gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <FileCode className="w-5 h-5 text-indigo-400" />
                Input LaTeX File &amp; LLM Prompt
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Upload your resume .tex code or paste below
              </p>
            </div>

            {/* LaTeX File Upload Button */}
            <label className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 flex items-center gap-1.5 cursor-pointer transition">
              <FileUp className="w-4 h-4" />
              Upload .tex
              <input
                type="file"
                accept=".tex,.txt"
                onChange={handleTexUpload}
                className="hidden"
              />
            </label>
          </div>

          {/* Structured LLM Prompt Trigger Box */}
          <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-500/30 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <span className="text-xs font-semibold text-indigo-200">
                  Ready-to-Use Structured LLM Prompt
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowPromptPreview(!showPromptPreview)}
                className="text-[11px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
              >
                {showPromptPreview ? "Hide Preview" : "Show Full Prompt"}
                {showPromptPreview ? (
                  <ChevronUp className="w-3.5 h-3.5" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5" />
                )}
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Copy this prompt into <strong>Claude 3.5 Sonnet</strong>, <strong>ChatGPT (GPT-4o)</strong>, or <strong>Gemini 1.5 Pro</strong>. It packages the full 30-Point Audit checklist, AST geometry rules, and JD requirements so the LLM outputs perfect, compliant LaTeX.
            </p>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleCopyPrompt}
                className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 flex items-center gap-1.5 transition"
              >
                {copiedPrompt ? (
                  <>
                    <Check className="w-4 h-4 text-emerald-300" />
                    Prompt Copied to Clipboard!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy LLM Prompt (for Claude / ChatGPT)
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={handleAutoOptimize}
                disabled={isAutoOptimizing}
                className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 transition disabled:opacity-50"
              >
                <Zap className="w-4 h-4 text-emerald-400" />
                {isAutoOptimizing ? "Optimizing AST..." : "Auto-Optimize in App (1-Click)"}
              </button>
            </div>

            {/* Expandable Prompt Preview */}
            {showPromptPreview && (
              <pre className="mt-3 p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-indigo-200/90 whitespace-pre-wrap max-h-64 overflow-y-auto leading-relaxed">
                {recommendationsData?.structured_llm_prompt}
              </pre>
            )}
          </div>

          {/* Interactive LaTeX Code Editor */}
          <div className="flex flex-col flex-1 gap-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-mono">LaTeX Source (.tex)</span>
              <button
                type="button"
                onClick={handleCopyTex}
                className="hover:text-slate-200 flex items-center gap-1 font-mono text-[11px]"
              >
                <Copy className="w-3.5 h-3.5" />
                {copiedTex ? "Copied" : "Copy Code"}
              </button>
            </div>
            <textarea
              value={rawTex}
              onChange={(e) => setRawTex(e.target.value)}
              rows={16}
              className="w-full p-3.5 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-slate-200 focus:outline-none focus:border-indigo-500 leading-relaxed resize-y"
              placeholder="Paste modified or original LaTeX source code here..."
            />

            {/* Action Bar: Re-Test Trigger */}
            <div className="flex items-center justify-between gap-3 pt-2">
              <span className="text-[11px] text-slate-400">
                Paste the LLM&apos;s output above, then click Re-Test:
              </span>
              <button
                type="button"
                onClick={handleRunRetest}
                disabled={isRetesting}
                className="px-4 py-2.5 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/25 flex items-center gap-2 transition disabled:opacity-50"
              >
                <Play className="w-4 h-4 fill-white" />
                {isRetesting ? "Re-Testing ATS Score..." : "Re-Test Score & Compile PDF"}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Re-Test Delta & PDF Production Preview */}
        <div className="lg:col-span-6 flex flex-col gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                Re-Test Results &amp; Native PDF Production
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Before vs. After Delta &amp; Compliant Document Export
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleDownloadPdf}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md flex items-center gap-1.5 transition"
              >
                <Download className="w-4 h-4" />
                Download PDF
              </button>
              <button
                type="button"
                onClick={handleDownloadTex}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
              >
                <FileCode className="w-4 h-4 text-cyan-400" />
                Download .tex
              </button>
            </div>
          </div>

          {/* Before vs. After Telemetry Card */}
          {retestResult ? (
            <div className="p-4 rounded-xl bg-slate-950 border border-emerald-500/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-mono text-slate-400">
                    Platform Score Delta ({selectedPlatform})
                  </span>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <span className="text-xs text-slate-400 line-through">
                      {retestResult.baseline_score?.toFixed(1) || currentScore.toFixed(1)}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 inline" />
                    <span className="text-2xl font-black font-mono text-emerald-400">
                      {retestResult.retested_score.toFixed(1)} / 100
                    </span>
                    <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-xs font-bold border border-emerald-500/30">
                      {retestResult.score_delta >= 0 ? "+" : ""}
                      {retestResult.score_delta.toFixed(1)} pts
                    </span>
                  </div>
                </div>

                <div className="text-right">
                  <span className="text-[11px] font-mono text-slate-400">Audit Status</span>
                  <p className="text-base font-bold font-mono text-cyan-300 mt-0.5">
                    {retestResult.audit_report.passed_count}/30 Passed
                  </p>
                </div>
              </div>

              {/* Summary message */}
              <p className="text-xs text-slate-300">{retestResult.summary_message}</p>

              {/* Hazards Status */}
              <div className="flex items-center gap-2 pt-1 border-t border-slate-800 text-xs font-mono">
                <span className="text-slate-400">Active Hazards:</span>
                {retestResult.hazards_detected.length === 0 ? (
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 0 AST Hazards (Clean Parse)
                  </span>
                ) : (
                  <span className="text-amber-400 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" />{" "}
                    {retestResult.hazards_detected.length} Hazard(s) Remaining
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-center py-6">
              <RefreshCw className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs font-medium text-slate-300">
                Awaiting Re-Test Execution
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                Click &ldquo;Re-Test Score &amp; Compile PDF&rdquo; or &ldquo;Auto-Optimize in App&rdquo; to see the Before vs. After delta.
              </p>
            </div>
          )}

          {/* In-Browser PDF Preview */}
          <div className="flex-1 flex flex-col rounded-xl border border-slate-800 overflow-hidden bg-slate-950 min-h-[380px]">
            <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900 border-b border-slate-800 text-xs">
              <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Eye className="w-4 h-4 text-cyan-400" />
                Live Single-Column PDF Preview (0.5-in Safe Margins)
              </span>
              <span className="text-[11px] font-mono text-emerald-400">
                {isGeneratingPdf ? "Rendering PDF..." : "Ready"}
              </span>
            </div>

            {pdfPreviewUrl ? (
              <iframe
                src={pdfPreviewUrl}
                title="ATS-Safe PDF Preview"
                className="w-full flex-1 min-h-[420px] border-none"
              />
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500">
                <FileText className="w-12 h-12 text-slate-700 mb-3" />
                <p className="text-xs text-slate-400">
                  PDF Preview will display here automatically upon re-testing.
                </p>
                <button
                  type="button"
                  onClick={() => generatePdfPreview(resume)}
                  className="mt-3 px-3 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
                >
                  Generate Initial Preview
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
