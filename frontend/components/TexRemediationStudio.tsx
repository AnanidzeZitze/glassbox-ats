"use client";

import React, { useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Code2,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileCode,
  FileText,
  FileUp,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  API_BASE_URL,
  ATSPlatform,
  RemediateTexResponse,
  remediateTexWithContext,
} from "@/services/api";

const SAMPLE_TEX = `\\documentclass[10pt,letterpaper]{article}
\\usepackage{geometry}
\\usepackage{multicol}
\\usepackage{fontawesome5}
\\begin{document}
\\author{Alex Rivera}
\\section{Experience}
\\textbf{Senior Cloud Architect} | CloudOps Inc. \\hfill 2021 -- Present
\\begin{itemize}
    \\item Directed enterprise cloud infrastructure migration on AWS using Terraform and Docker.
\\end{itemize}
\\section{Education}
\\textbf{B.S. in Computer Science} | MIT \\hfill 2020
\\section{Skills}
Python, AWS, Docker, Terraform
\\end{document}`;

const SAMPLE_MD = `# Alex Rivera - Master Profile & Career Context
## Comprehensive Work History
At CloudOps Inc., I led the migration of 40+ microservices to Kubernetes clusters on AWS EKS, reducing deployment failure rate by 38%.
Additionally, I designed event streaming pipelines using Apache Kafka for real-time telemetry processing handling 12,000 events/sec.
I also authored automated CI/CD deployment pipelines using GitHub Actions and ArgoCD.

## Education & Certifications
- MIT: B.S. Computer Science, 2020 (GPA 3.8/4.0)
- AWS Certified Solutions Architect - Professional (2023)
- Certified Kubernetes Administrator (CKA, 2022)

## Additional Projects & Open Source
- Authored open-source Terraform provider plugin with 500+ GitHub stars.
- Implemented automated database migration testing in PostgreSQL using Python and Pytest.`;

interface TexRemediationStudioProps {
  initialJdText: string;
  selectedPlatform: ATSPlatform;
}

export default function TexRemediationStudio({
  initialJdText,
  selectedPlatform,
}: TexRemediationStudioProps) {
  const [texContent, setTexContent] = useState(SAMPLE_TEX);
  const [mdContent, setMdContent] = useState(SAMPLE_MD);
  const [jdText, setJdText] = useState(initialJdText || "Job Title: Staff Infrastructure Engineer\nMust Have: AWS, Kubernetes, Terraform, Docker, Kafka\nPreferred: GitHub Actions, PostgreSQL");
  const [isLoading, setIsLoading] = useState(false);
  const [remediationResult, setRemediationResult] = useState<RemediateTexResponse | null>(null);
  const [activeEvidenceTab, setActiveEvidenceTab] = useState<"WORKDAY" | "GREENHOUSE" | "LEVER" | "TALEO" | "ICIMS">("WORKDAY");
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [copiedTex, setCopiedTex] = useState(false);
  const [showTexCode, setShowTexCode] = useState(false);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>, type: "TEX" | "MD") => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (type === "TEX") setTexContent(text);
      else setMdContent(text);
    };
    reader.readAsText(file);
  };

  const handleRunRemediation = async () => {
    setIsLoading(true);
    setPdfPreviewUrl(null);
    try {
      const result = await remediateTexWithContext(
        texContent,
        mdContent,
        jdText,
        selectedPlatform
      );
      setRemediationResult(result);
    } catch (err: any) {
      alert(`Remediation failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyTex = async () => {
    if (!remediationResult) return;
    await navigator.clipboard.writeText(remediationResult.updated_tex);
    setCopiedTex(true);
    setTimeout(() => setCopiedTex(false), 2000);
  };

  const handleTogglePdfPreview = async () => {
    if (pdfPreviewUrl) {
      URL.revokeObjectURL(pdfPreviewUrl);
      setPdfPreviewUrl(null);
      return;
    }
    if (!remediationResult) return;
    setIsLoadingPreview(true);
    try {
      const res = await fetch(`${API_BASE_URL}/export-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(remediationResult.updated_canonical),
      });
      if (!res.ok) throw new Error("PDF generation failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPdfPreviewUrl(url);
    } catch {
      alert("Failed to render PDF preview.");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleDownloadTex = () => {
    if (!remediationResult) return;
    const blob = new Blob([remediationResult.updated_tex], {
      type: "application/x-tex;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ats_safe_optimized_resume.tex";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = async () => {
    if (!remediationResult) return;
    setIsExportingPdf(true);
    try {
      const res = await fetch(`${API_BASE_URL}/export-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(remediationResult.updated_canonical),
      });
      if (!res.ok) throw new Error("PDF export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${remediationResult.updated_canonical.full_name.toLowerCase().replace(/\\s+/g, "_")}_ats_optimized.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      alert("PDF compilation failed. Please verify the backend is running.");
    } finally {
      setIsExportingPdf(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/60 to-slate-900 border border-indigo-500/30 rounded-2xl p-6 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                Reverse-Engineered Remediator
              </span>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                Zero-Hallucination Grounded (.md)
              </span>
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <Code2 className="w-5 h-5 text-indigo-400" />
              LaTeX Resume (.tex) & Master Profile (.md) Optimization Studio
            </h2>
            <p className="text-sm text-slate-300 max-w-3xl mt-1">
              Input your LaTeX source, target Job Description, and master career background (.md). The engine reverse-engineers the ATS parsing rules, queries your real background for missing skills, and outputs an updated ATS-safe .tex and compiled PDF.
            </p>
          </div>

          <button
            onClick={handleRunRemediation}
            disabled={isLoading || !texContent.trim() || !jdText.trim()}
            className="flex items-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold text-sm shadow-lg shadow-indigo-600/30 disabled:opacity-50 transition"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            Run ATS Reverse-Engineering & Remediation
          </button>
        </div>
      </div>

      {/* Triple Input Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Panel 1: resume.tex */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-mono font-semibold text-cyan-300 uppercase flex items-center gap-1.5">
              <FileCode className="w-4 h-4 text-cyan-400" />
              1. Resume LaTeX (.tex)
            </label>
            <label className="text-xs text-indigo-400 hover:text-indigo-300 cursor-pointer flex items-center gap-1">
              <FileUp className="w-3.5 h-3.5" /> Upload .tex
              <input
                type="file"
                accept=".tex,.txt"
                onChange={(e) => handleFileUpload(e, "TEX")}
                className="hidden"
              />
            </label>
          </div>
          <textarea
            value={texContent}
            onChange={(e) => setTexContent(e.target.value)}
            rows={14}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500/60 resize-none"
            placeholder="Paste raw LaTeX resume source code..."
          />
        </div>

        {/* Panel 2: master_profile.md */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-mono font-semibold text-emerald-300 uppercase flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-emerald-400" />
              2. Master Profile (.md)
            </label>
            <label className="text-xs text-indigo-400 hover:text-indigo-300 cursor-pointer flex items-center gap-1">
              <FileUp className="w-3.5 h-3.5" /> Upload .md
              <input
                type="file"
                accept=".md,.txt"
                onChange={(e) => handleFileUpload(e, "MD")}
                className="hidden"
              />
            </label>
          </div>
          <textarea
            value={mdContent}
            onChange={(e) => setMdContent(e.target.value)}
            rows={14}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500/60 resize-none"
            placeholder="Paste your comprehensive career background (.md) with all achievements, side projects, schooling, and tools..."
          />
        </div>

        {/* Panel 3: Job Description */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col gap-3">
          <label className="text-xs font-mono font-semibold text-indigo-300 uppercase flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-indigo-400" />
            3. Target Job Description
          </label>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={14}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500/60 resize-none"
            placeholder="Paste target Job Description text..."
          />
        </div>
      </div>

      {/* Results View */}
      {remediationResult && (
        <div className="space-y-6">
          {/* Score Jump Banner */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center text-center">
              <span className="text-xs font-mono text-slate-400 uppercase">Input .tex Score ({remediationResult.target_platform})</span>
              <div className="text-3xl font-extrabold text-slate-300 mt-1 font-mono">
                {remediationResult.baseline_score.toFixed(1)} / 100
              </div>
            </div>

            <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-indigo-950/40 border border-emerald-500/40 rounded-xl p-5 flex flex-col items-center justify-center text-center">
              <span className="text-xs font-mono text-emerald-400 uppercase font-semibold">Remediated Score</span>
              <div className="text-4xl font-extrabold text-emerald-300 mt-1 font-mono flex items-center gap-2">
                {remediationResult.remediated_score.toFixed(1)} / 100
                <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  +{(remediationResult.remediated_score - remediationResult.baseline_score).toFixed(1)} pts
                </span>
              </div>
            </div>

            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col justify-center gap-2">
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleDownloadPdf}
                  disabled={isExportingPdf}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition"
                >
                  <Download className="w-3.5 h-3.5" />
                  {isExportingPdf ? "Compiling..." : "PDF Export"}
                </button>
                <button
                  onClick={handleTogglePdfPreview}
                  disabled={isLoadingPreview}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition"
                >
                  {isLoadingPreview ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : pdfPreviewUrl ? (
                    <EyeOff className="w-3.5 h-3.5" />
                  ) : (
                    <Eye className="w-3.5 h-3.5" />
                  )}
                  {pdfPreviewUrl ? "Close Preview" : "Live PDF Preview"}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleDownloadTex}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-semibold text-xs transition"
                >
                  <Download className="w-3.5 h-3.5" />
                  Save .tex
                </button>
                <button
                  onClick={handleCopyTex}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-semibold text-xs transition"
                >
                  {copiedTex ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Copy className="w-3.5 h-3.5 text-slate-400" />
                  )}
                  {copiedTex ? "Copied!" : "Copy .tex"}
                </button>
              </div>

              <button
                onClick={() => setShowTexCode((prev) => !prev)}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800 text-[11px] font-mono transition"
              >
                <Code2 className="w-3 h-3 text-cyan-400" />
                {showTexCode ? "Hide Updated LaTeX Source" : "View Updated LaTeX Source Code"}
              </button>
            </div>
          </div>

          {/* Interactive Live PDF Preview Embed */}
          {pdfPreviewUrl && (
            <div className="bg-slate-900/90 border border-indigo-500/40 rounded-xl p-5 shadow-2xl space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-indigo-400" />
                  <h3 className="text-sm font-semibold text-white">
                    Live Compiled PDF Preview (0.5-Inch Safe Margins, Single-Column PyMuPDF Render)
                  </h3>
                </div>
                <button
                  onClick={() => {
                    URL.revokeObjectURL(pdfPreviewUrl);
                    setPdfPreviewUrl(null);
                  }}
                  className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800 border border-slate-700"
                >
                  Close Preview
                </button>
              </div>
              <iframe
                src={pdfPreviewUrl}
                title="ATS-Compliant PDF Preview"
                className="w-full h-[680px] rounded-lg border border-slate-800 bg-white shadow-inner"
              />
            </div>
          )}

          {/* Collapsible Updated LaTeX Source Code Viewer */}
          {showTexCode && (
            <div className="bg-slate-900/90 border border-cyan-500/30 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                <h3 className="text-xs font-mono font-semibold text-cyan-300 flex items-center gap-2">
                  <Code2 className="w-4 h-4 text-cyan-400" />
                  ATS-Compliant LaTeX Code (Zero Tables, Clean Delimiters, 0.5-Inch Margins)
                </h3>
                <button
                  onClick={handleCopyTex}
                  className="text-xs font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                >
                  {copiedTex ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  {copiedTex ? "Copied!" : "Copy Code"}
                </button>
              </div>
              <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-96">
                <code>{remediationResult.updated_tex}</code>
              </pre>
            </div>
          )}

          {/* LaTeX Hazards Detected */}
          {remediationResult.hazards_detected.length > 0 && (
            <div className="bg-slate-900/90 border border-amber-500/30 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-amber-300 flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Detected LaTeX ATS Hazards in Original Source Code ({remediationResult.hazards_detected.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                {remediationResult.hazards_detected.map((h, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-amber-400 font-semibold">
                        {h.hazard_type}
                      </span>
                      {h.line_num && (
                        <span className="text-[10px] text-slate-500 font-mono">
                          Line {h.line_num}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 text-[11px]">{h.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Reverse-Engineering Evidence Trace Tabs */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 gap-3">
              <div>
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-indigo-400" />
                  Reverse-Engineered ATS Evidence Inspector
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Direct telemetry from clean-room emulators of the 5 major ATS architectures
                </p>
              </div>

              <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
                {(["WORKDAY", "GREENHOUSE", "LEVER", "TALEO", "ICIMS"] as const).map((plat) => (
                  <button
                    key={plat}
                    onClick={() => setActiveEvidenceTab(plat)}
                    className={`px-3 py-1.5 rounded-md font-mono text-xs transition ${
                      activeEvidenceTab === plat
                        ? "bg-indigo-600 text-white font-semibold"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {plat}
                  </button>
                ))}
              </div>
            </div>

            {/* Evidence Tab View */}
            <div className="bg-slate-950 rounded-lg p-4 font-mono text-xs text-slate-300 border border-slate-800">
              {activeEvidenceTab === "WORKDAY" && remediationResult.evidence_trace.workday && (
                <div className="space-y-3">
                  <div className="text-indigo-400 font-semibold">
                    Engine: {remediationResult.evidence_trace.workday.engine_architecture}
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {remediationResult.evidence_trace.workday.reverse_engineering_notes}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div className="p-3 bg-slate-900 rounded border border-slate-800">
                      <div className="text-emerald-400 font-semibold mb-1">Single-Token Technical Skills Retained:</div>
                      <div>{remediationResult.evidence_trace.workday.retained_single_token_skills_count} tokens indexed</div>
                    </div>
                    <div className="p-3 bg-slate-900 rounded border border-slate-800">
                      <div className="text-rose-400 font-semibold mb-1">Multi-Word Soft Phrases Dropped by Workday:</div>
                      <div>
                        {remediationResult.evidence_trace.workday.dropped_multiword_skills.length > 0
                          ? remediationResult.evidence_trace.workday.dropped_multiword_skills.join(", ")
                          : "None (All skills single-token or compliant)"}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeEvidenceTab === "GREENHOUSE" && remediationResult.evidence_trace.greenhouse && (
                <div className="space-y-3">
                  <div className="text-emerald-400 font-semibold">
                    Engine: {remediationResult.evidence_trace.greenhouse.engine_architecture}
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {remediationResult.evidence_trace.greenhouse.reverse_engineering_notes}
                  </p>
                  <div className="p-3 bg-slate-900 rounded border border-slate-800">
                    <div className="text-slate-300">Name Entity Split: First: {remediationResult.evidence_trace.greenhouse.name_parsing.first_name} | Last: {remediationResult.evidence_trace.greenhouse.name_parsing.last_name}</div>
                    <div className="text-slate-400 mt-1">Evaluation Mode: {remediationResult.evidence_trace.greenhouse.scoring_mode}</div>
                  </div>
                </div>
              )}

              {activeEvidenceTab === "LEVER" && remediationResult.evidence_trace.lever && (
                <div className="space-y-3">
                  <div className="text-cyan-400 font-semibold">
                    Engine: {remediationResult.evidence_trace.lever.engine_architecture}
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {remediationResult.evidence_trace.lever.reverse_engineering_notes}
                  </p>
                  <div className="p-3 bg-slate-900 rounded border border-slate-800 space-y-1">
                    <div className="text-emerald-400">Indexed Top 4 Tags (tags[:4]):</div>
                    <div>{remediationResult.evidence_trace.lever.tag_truncation_telemetry.indexed_primary_tags.join(", ")}</div>
                    {remediationResult.evidence_trace.lever.tag_truncation_telemetry.truncated_discarded_tags.length > 0 && (
                      <>
                        <div className="text-rose-400 mt-2">Truncated / Discarded Secondary Tags:</div>
                        <div>{remediationResult.evidence_trace.lever.tag_truncation_telemetry.truncated_discarded_tags.join(", ")}</div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {activeEvidenceTab === "TALEO" && remediationResult.evidence_trace.taleo && (
                <div className="space-y-3">
                  <div className="text-amber-400 font-semibold">
                    Engine: {remediationResult.evidence_trace.taleo.engine_architecture}
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {remediationResult.evidence_trace.taleo.reverse_engineering_notes}
                  </p>
                  <div className="p-3 bg-slate-900 rounded border border-slate-800">
                    <div>Verbatim Rule: {remediationResult.evidence_trace.taleo.verbatim_weight}</div>
                    <div className="text-slate-400 mt-1">Margin Telemetry Rule: {remediationResult.evidence_trace.taleo.margin_clipping_telemetry.rule}</div>
                  </div>
                </div>
              )}

              {activeEvidenceTab === "ICIMS" && remediationResult.evidence_trace.icims && (
                <div className="space-y-3">
                  <div className="text-purple-400 font-semibold">
                    Engine: {remediationResult.evidence_trace.icims.engine_architecture}
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    {remediationResult.evidence_trace.icims.reverse_engineering_notes}
                  </p>
                  <div className="p-3 bg-slate-900 rounded border border-slate-800">
                    <div>Boolean Density Score: {remediationResult.evidence_trace.icims.boolean_density_score}</div>
                    <div>Matched in Experience Bullets: {remediationResult.evidence_trace.icims.frequency_clusters.experience_bullets_cluster.join(", ") || "None"}</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Bullet Diffs with Grounding Evidence */}
          {remediationResult.diffs.length > 0 && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Grounded Bullet Point Enhancements ({remediationResult.diffs.length})
              </h3>
              <div className="space-y-3">
                {remediationResult.diffs.map((diff) => (
                  <div
                    key={diff.diff_id}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between text-slate-400 font-mono">
                      <span>{diff.role_title} @ {diff.company}</span>
                      <span className="text-emerald-400 font-semibold">
                        Added: {diff.injected_keywords.join(", ")}
                      </span>
                    </div>
                    <div className="p-2.5 rounded bg-rose-950/20 border border-rose-500/20 text-rose-200">
                      <span className="text-rose-400 font-mono mr-2">- ORIGINAL:</span>
                      {diff.original_bullet}
                    </div>
                    <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-500/20 text-emerald-200">
                      <span className="text-emerald-400 font-mono mr-2">+ TAILORED (GROUNDED IN .MD):</span>
                      {diff.tailored_bullet}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
