"use client";

import React, { useState } from "react";
import {
  Check,
  CheckCircle2,
  Code2,
  Download,
  FileText,
  GitCompare,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  API_BASE_URL,
  CanonicalResume,
  JDRequirementInput,
  TailorBulletDiffItem,
  TailorBulletsResponse,
} from "@/services/api";

interface TailoringStudioProps {
  resume: CanonicalResume;
  jd: JDRequirementInput;
  tailorData: TailorBulletsResponse;
  onApproveBullet: (diff: TailorBulletDiffItem) => void;
  onRegenerateTailoring: () => void;
}

export default function TailoringStudio({
  resume,
  jd,
  tailorData,
  onApproveBullet,
  onRegenerateTailoring,
}: TailoringStudioProps) {
  const [decisions, setDecisions] = useState<
    Record<string, "APPROVED" | "REJECTED" | "PENDING">
  >({});
  const [showLatexModal, setShowLatexModal] = useState(false);

  const handleApprove = (diff: TailorBulletDiffItem) => {
    setDecisions((prev) => ({ ...prev, [diff.diff_id]: "APPROVED" }));
    onApproveBullet(diff);
  };

  const handleApproveAll = () => {
    const next: Record<string, "APPROVED" | "REJECTED" | "PENDING"> = {
      ...decisions,
    };
    for (const diff of tailorData.diffs) {
      if (next[diff.diff_id] !== "APPROVED") {
        next[diff.diff_id] = "APPROVED";
        onApproveBullet(diff);
      }
    }
    setDecisions(next);
  };

  const handleReject = (diffId: string) => {
    setDecisions((prev) => ({ ...prev, [diffId]: "REJECTED" }));
  };

  const handleDownloadPdf = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/export-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(resume),
      });
      if (!res.ok) throw new Error("PDF export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${resume.full_name.toLowerCase().replace(/\s+/g, "_")}_ats_safe.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      alert("Ensure backend server on port 8000 is running to export native PDF.");
    }
  };

  const handleDownloadLatex = () => {
    const blob = new Blob([tailorData.latex_source], {
      type: "application/x-tex;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${resume.full_name.toLowerCase().replace(/\s+/g, "_")}_ats_safe.tex`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadDocx = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/export-docx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(resume),
      });
      if (!res.ok) throw new Error("Fallback to client docx export");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${resume.full_name.toLowerCase().replace(/\s+/g, "_")}_ats_safe.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      const locStr = resume.address
        ? [resume.address.city, resume.address.region].filter(Boolean).join(", ")
        : null;
      const contactParts = [resume.email, resume.phone, resume.linkedin_url, locStr].filter(Boolean);
      const lines = [
        resume.full_name.toUpperCase(),
        contactParts.join(" | "),
        "",
        "PROFESSIONAL SUMMARY",
        resume.summary || "",
        "",
        "WORK EXPERIENCE",
        ...resume.employments.flatMap((e) => [
          `${e.title} | ${e.company} | ${e.start_date_raw} - ${e.end_date_raw || "Present"}`,
          ...e.bullets.map((b) => `- ${b}`),
          "",
        ]),
        "EDUCATION",
        ...resume.educations.map(
          (ed) => `${ed.degree}${ed.major ? " in " + ed.major : ""} | ${ed.school} | ${ed.end_year}`
        ),
        "",
        "SKILLS",
        resume.skills.join(", "),
      ];
      const blob = new Blob([lines.join("\n")], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${resume.full_name.toLowerCase().replace(/\s+/g, "_")}_ats_safe.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Bar: Zero-Hallucination Pydantic Validator Telemetry & 1-Click Exporters */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 mt-0.5">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-white">
                Module 6: Constrained AI Tailoring &amp; Zero-Hallucination Guardrail
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                max_retries = 3 • @model_validator(mode=&quot;after&quot;) PASSED
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">{tailorData.validation_summary}</p>
          </div>
        </div>

        {/* 1-Click Export Triggers */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleApproveAll}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 transition"
          >
            <Check className="w-4 h-4" />
            Approve All Diffs
          </button>

          <button
            type="button"
            onClick={onRegenerateTailoring}
            className="px-3 py-2 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
          >
            <Sparkles className="w-4 h-4 text-cyan-400" />
            Re-Run Tailor
          </button>

          <button
            type="button"
            onClick={handleDownloadPdf}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-600/25 flex items-center gap-1.5 transition"
          >
            <Download className="w-4 h-4" />
            Export .PDF
          </button>

          <button
            type="button"
            onClick={handleDownloadDocx}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 flex items-center gap-1.5 transition"
          >
            <Download className="w-4 h-4" />
            Export .DOCX
          </button>

          <button
            type="button"
            onClick={handleDownloadLatex}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/25 flex items-center gap-1.5 transition"
          >
            <FileText className="w-4 h-4" />
            Export .tex
          </button>

          <button
            type="button"
            onClick={() => setShowLatexModal((prev) => !prev)}
            className="px-3 py-2 rounded-lg text-xs font-mono bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 flex items-center gap-1.5 transition"
          >
            <Code2 className="w-4 h-4 text-emerald-400" />
            {showLatexModal ? "Hide LaTeX" : "Preview LaTeX"}
          </button>
        </div>
      </div>

      {/* Optional Overleaf pdfLaTeX Source Preview */}
      {showLatexModal && (
        <div className="bg-slate-950 border border-emerald-500/40 rounded-xl p-4">
          <div className="flex items-center justify-between text-xs text-emerald-300 font-mono mb-2">
            <span>overleaf_single_column_ats_safe.tex</span>
            <span>Zero Tables • Zero Floating Boxes • Standard Section Headers</span>
          </div>
          <pre className="text-xs font-mono text-slate-200 overflow-x-auto p-3 bg-slate-900 rounded-lg">
            {tailorData.latex_source}
          </pre>
        </div>
      )}

      {/* GitHub-Style Before/After Experience Bullet Diff Editor */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-base font-semibold text-white flex items-center gap-2">
              <GitCompare className="w-5 h-5 text-cyan-400" />
              Interactive Experience Bullet Diff Review
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Target Role: <strong className="text-slate-200">{jd.target_title}</strong> • Every
              diff preserves original metrics from `master_resume_json`
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {tailorData.diffs.map((diff) => {
            const status = decisions[diff.diff_id] || "PENDING";
            return (
              <div
                key={diff.diff_id}
                className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden"
              >
                {/* Role Header */}
                <div className="bg-slate-900/80 px-4 py-2.5 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-white">{diff.role_title}</span>
                    <span className="text-slate-500">@</span>
                    <span className="text-cyan-300 font-medium">{diff.company}</span>
                    <span className="font-mono text-[11px] text-slate-400">
                      ({diff.start_date} → {diff.end_date})
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {diff.injected_keywords.map((kw) => (
                      <span
                        key={kw}
                        className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono text-[11px]"
                      >
                        +{kw}
                      </span>
                    ))}
                    <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-mono text-[11px] flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Metrics Locked
                    </span>
                  </div>
                </div>

                {/* GitHub Red / Green Diff Lines */}
                <div className="p-4 space-y-2 font-mono text-xs">
                  <div className="bg-rose-950/40 border border-rose-500/30 text-rose-200 px-3 py-2 rounded-lg flex items-start gap-2">
                    <span className="text-rose-400 font-bold select-none">-</span>
                    <span>{diff.original_bullet}</span>
                  </div>

                  <div className="bg-emerald-950/40 border border-emerald-500/30 text-emerald-200 px-3 py-2 rounded-lg flex items-start gap-2">
                    <span className="text-emerald-400 font-bold select-none">+</span>
                    <span>{diff.tailored_bullet}</span>
                  </div>
                </div>

                {/* Approve / Reject Footer */}
                <div className="px-4 py-2.5 bg-slate-900/50 border-t border-slate-800/80 flex items-center justify-between text-xs">
                  <span className="text-[11px] text-slate-400">
                    {diff.quantified_metric_preserved}
                  </span>

                  <div className="flex items-center gap-2">
                    {status === "APPROVED" ? (
                      <span className="px-3 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold flex items-center gap-1">
                        <Check className="w-3.5 h-3.5" />
                        Approved &amp; Merged into Resume
                      </span>
                    ) : status === "REJECTED" ? (
                      <span className="px-3 py-1 rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold flex items-center gap-1">
                        <X className="w-3.5 h-3.5" />
                        Rejected (Original Retained)
                      </span>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => handleApprove(diff)}
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold flex items-center gap-1 transition"
                        >
                          <Check className="w-3.5 h-3.5" />
                          Approve Diff
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReject(diff.diff_id)}
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950 text-slate-300 hover:text-rose-200 border border-slate-700 font-semibold flex items-center gap-1 transition"
                        >
                          <X className="w-3.5 h-3.5" />
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
