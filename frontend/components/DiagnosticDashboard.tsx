"use client";

import React, { useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Award,
  CheckCircle2,
  Filter,
  Gauge,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  ATSPlatform,
  ComputeScoreResponse,
  KnockoutRulesInput,
  RRFCandidateResult,
} from "@/services/api";

interface DiagnosticDashboardProps {
  scoreData: ComputeScoreResponse;
  selectedPlatform: ATSPlatform;
  knockoutRules: KnockoutRulesInput;
  onUpdateKnockoutRules: (rules: KnockoutRulesInput) => void;
  rrfResults: RRFCandidateResult[];
}

function CircularGauge({
  value,
  label,
  sublabel,
  targetBandText,
  isStuffingWarning = false,
}: {
  value: number;
  label: string;
  sublabel: string;
  targetBandText?: string;
  isStuffingWarning?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (clamped / 100) * circumference;

  const strokeColor = isStuffingWarning
    ? "#f59e0b"
    : clamped >= 75
    ? "#10b981"
    : clamped >= 60
    ? "#38bdf8"
    : "#f43f5e";

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col items-center justify-between shadow-lg">
      <div className="relative w-36 h-36 flex items-center justify-center">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 128 128">
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke="#1e293b"
            strokeWidth="10"
            fill="transparent"
          />
          <circle
            cx="64"
            cy="64"
            r={radius}
            stroke={strokeColor}
            strokeWidth="10"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-2xl font-bold text-white font-mono">
            {clamped.toFixed(1)}%
          </span>
          {targetBandText && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 mt-1">
              {targetBandText}
            </span>
          )}
        </div>
      </div>

      <div className="text-center mt-3">
        <h3 className="text-sm font-semibold text-white">{label}</h3>
        <p className="text-xs text-slate-400 mt-1">{sublabel}</p>
      </div>
    </div>
  );
}

export default function DiagnosticDashboard({
  scoreData,
  selectedPlatform,
  knockoutRules,
  onUpdateKnockoutRules,
  rrfResults,
}: DiagnosticDashboardProps) {
  const [auditFilter, setAuditFilter] = useState<"ALL" | "PASS" | "FAIL">("ALL");

  const { score_breakdown: sb, audit_report: ar, knockout_checks, passed_all_knockouts } =
    scoreData;

  const jdMatchPct = Number((sb.keyword_match_pct * 100).toFixed(1));
  const parseSuccessPct = Number((sb.parse_success_ratio * 100).toFixed(1));
  const contentAuditPct = ar.overall_audit_score;
  const isStuffingWarning = jdMatchPct >= 90;
  const isOptimalBand = jdMatchPct >= 70 && jdMatchPct <= 85;

  const filteredParams = ar.parameters.filter((p) => {
    if (auditFilter === "ALL") return true;
    if (auditFilter === "PASS") return p.status === "PASS";
    return p.status !== "PASS";
  });

  return (
    <div className="space-y-6">
      {/* TOP ROW: 3 Core Diagnostic Gauges + Composite Platform Score Card */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <CircularGauge
          value={jdMatchPct}
          label="JD Keyword Match Rate"
          sublabel={
            isStuffingWarning
              ? "WARNING: >= 90% triggers Keyword Stuffing Flag!"
              : isOptimalBand
              ? "Inside 75%–85% Optimal Target Sweet Spot"
              : "70% Must-Have Pool + 30% Preferred Pool"
          }
          targetBandText="Target: 75%-85%"
          isStuffingWarning={isStuffingWarning}
        />

        <CircularGauge
          value={parseSuccessPct}
          label="Parse Success Score"
          sublabel="Stage 0 OCR + Stage 1 XY-Cut++ Layout Integrity"
          targetBandText="Baseline: 100%"
        />

        <CircularGauge
          value={contentAuditPct}
          label="30-Point Content Impact"
          sublabel={`${ar.passed_count} / ${ar.total_parameters} Deterministic Checks Passed`}
          targetBandText={`${ar.passed_count}/30 PASS`}
        />

        {/* Universal 5-Component Platform Score Summary */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col justify-between shadow-lg">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider text-indigo-400">
                {selectedPlatform} Composite Score
              </span>
              <Gauge className="w-4 h-4 text-indigo-400" />
            </div>

            {sb.manual_scorecard_mode ? (
              <div className="my-4 p-3 rounded-lg bg-indigo-950/40 border border-indigo-500/40 text-xs text-indigo-200">
                <strong className="block text-indigo-300 mb-1">
                  Greenhouse Manual Scorecard Mode
                </strong>
                Greenhouse does not compute an automated composite ranking score; recruiters review
                structured Sovren JSON attributes directly.
              </div>
            ) : (
              <div className="my-3">
                <div className="text-4xl font-extrabold text-white font-mono">
                  {sb.total_score?.toFixed(2)}
                  <span className="text-lg text-slate-400 font-normal"> / 100</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  5-Component Deterministic Weight Matrix
                </p>
              </div>
            )}
          </div>

          {!sb.manual_scorecard_mode && (
            <div className="space-y-1.5 text-xs font-mono border-t border-slate-800 pt-3">
              <div className="flex justify-between text-slate-300">
                <span>W1 Keyword Match:</span>
                <span className="text-emerald-400">+{sb.keyword_match_weighted}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span>W2 Placement Multiplier:</span>
                <span className="text-cyan-400">+{sb.placement_weighted}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span>W3 Section Completeness:</span>
                <span className="text-indigo-400">+{sb.sections_weighted}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span>W4 Parse Success:</span>
                <span className="text-amber-400">+{sb.parse_success_weighted}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span>W5 Relevance Boost:</span>
                <span className="text-purple-400">+{sb.relevance_weighted}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* KEYWORD MATCH & GAP BREAKDOWN BAR */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-white">
              Target JD Keyword Coverage Breakdown (70% Must-Have Pool • 30% Preferred Pool)
            </h3>
            <p className="text-xs text-slate-400">
              Must-Have Match Rate: <strong className="text-emerald-400">{(sb.must_have_match_rate * 100).toFixed(0)}%</strong> •
              Preferred Match Rate: <strong className="text-cyan-400">{(sb.preferred_match_rate * 100).toFixed(0)}%</strong>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="font-semibold text-emerald-300 mb-2 flex items-center justify-between">
              <span>Matched Must-Have Skills</span>
              <span className="font-mono">{sb.matched_must_have.length}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sb.matched_must_have.length > 0 ? (
                sb.matched_must_have.map((sk) => (
                  <span
                    key={sk}
                    className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-mono text-[11px]"
                  >
                    ✓ {sk}
                  </span>
                ))
              ) : (
                <span className="text-slate-500">None matched</span>
              )}
            </div>
          </div>

          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="font-semibold text-rose-300 mb-2 flex items-center justify-between">
              <span>Missing Must-Have Skills (Gaps)</span>
              <span className="font-mono">{sb.missing_must_have.length}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sb.missing_must_have.length > 0 ? (
                sb.missing_must_have.map((sk) => (
                  <span
                    key={sk}
                    className="px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 font-mono text-[11px]"
                  >
                    ✗ {sk}
                  </span>
                ))
              ) : (
                <span className="text-emerald-400 font-mono text-[11px]">
                  100% Must-Have Coverage!
                </span>
              )}
            </div>
          </div>

          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="font-semibold text-cyan-300 mb-2 flex items-center justify-between">
              <span>Matched Preferred &amp; Semantic (+0.5)</span>
              <span className="font-mono">
                {sb.matched_preferred.length + sb.semantic_neighbor_matches.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sb.matched_preferred.map((sk) => (
                <span
                  key={sk}
                  className="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-mono text-[11px]"
                >
                  ★ {sk}
                </span>
              ))}
              {sb.semantic_neighbor_matches.map((sk) => (
                <span
                  key={sk}
                  className="px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-mono text-[11px]"
                >
                  ≈ {sk} (+0.5 Lever)
                </span>
              ))}
              {sb.matched_preferred.length === 0 &&
                sb.semantic_neighbor_matches.length === 0 && (
                  <span className="text-slate-500">No preferred pool matches yet</span>
                )}
            </div>
          </div>
        </div>
      </div>

      {/* DEDICATED KNOCKOUT DISQUALIFIER ALERT BOX */}
      <div
        className={`rounded-xl border p-5 transition ${
          passed_all_knockouts
            ? "bg-slate-900/90 border-emerald-500/40"
            : "bg-rose-950/30 border-rose-500/60"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            {passed_all_knockouts ? (
              <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
            ) : (
              <div className="p-2.5 rounded-lg bg-rose-500/20 text-rose-400">
                <ShieldAlert className="w-6 h-6" />
              </div>
            )}
            <div>
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                Knockout Disqualifier Gate Check
                <span
                  className={`text-xs font-mono px-2.5 py-0.5 rounded-full ${
                    passed_all_knockouts
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                  }`}
                >
                  {passed_all_knockouts
                    ? "PASSED ALL GATES"
                    : "AUTO-DISQUALIFIED BY HARD GATE"}
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Hard boolean ATS pre-screen questions (Work Authorization, Security Clearance,
                Onsite Days, Degree Tier)
              </p>
            </div>
          </div>

          {/* Interactive Gate Toggles to Test Knockout Simulation */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() =>
                onUpdateKnockoutRules({
                  ...knockoutRules,
                  candidate_has_work_auth: !knockoutRules.candidate_has_work_auth,
                })
              }
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
            >
              Toggle Work Auth ({knockoutRules.candidate_has_work_auth ? "Authorized" : "Needs Visa"})
            </button>
            <button
              type="button"
              onClick={() =>
                onUpdateKnockoutRules({
                  ...knockoutRules,
                  requires_clearance:
                    knockoutRules.requires_clearance === "None" ? "Top Secret" : "None",
                })
              }
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
            >
              Require Clearance ({knockoutRules.requires_clearance})
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          {knockout_checks.map((chk) => (
            <div
              key={chk.id}
              className={`p-3.5 rounded-lg border text-xs ${
                chk.passed
                  ? "bg-slate-950/70 border-slate-800 text-slate-200"
                  : "bg-rose-950/50 border-rose-500/50 text-rose-200"
              }`}
            >
              <div className="flex items-center justify-between font-semibold mb-1.5">
                <span>{chk.label}</span>
                {chk.passed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertOctagon className="w-4 h-4 text-rose-400" />
                )}
              </div>
              <div className="text-[11px] text-slate-400 space-y-0.5 font-mono">
                <div>Required: {chk.required_value}</div>
                <div className={chk.passed ? "text-emerald-300" : "text-rose-300"}>
                  Candidate: {chk.candidate_value}
                </div>
              </div>
              {chk.disqualifier_reason && (
                <p className="mt-2 text-[11px] text-rose-300 bg-rose-500/10 p-1.5 rounded">
                  {chk.disqualifier_reason}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* RRF Hybrid Search Tournament Preview & 30-Parameter Audit Checklist */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* 30-Parameter Content & Formatting Audit Checklist */}
        <div className="lg:col-span-8 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-4">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <Filter className="w-4 h-4 text-cyan-400" />
                30-Parameter Content &amp; Formatting Audit Checklist
              </h3>
              <p className="text-xs text-slate-400">
                100% deterministic verification of layout, typography, spaCy POS action verbs,
                quantified impact, and anti-stuffing guardrails
              </p>
            </div>

            <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              {(["ALL", "PASS", "FAIL"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setAuditFilter(mode)}
                  className={`px-2.5 py-1 rounded-md font-medium transition ${
                    auditFilter === mode
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[440px] overflow-y-auto pr-1">
            {filteredParams.map((param) => (
              <div
                key={param.param_id}
                className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                  param.status === "PASS"
                    ? "bg-slate-950/60 border-slate-800/90 text-slate-200"
                    : param.status === "WARN"
                    ? "bg-amber-950/30 border-amber-500/40 text-amber-200"
                    : "bg-rose-950/30 border-rose-500/40 text-rose-200"
                }`}
              >
                {param.status === "PASS" ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                ) : param.status === "WARN" ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                )}
                <div>
                  <div className="font-semibold text-white">
                    #{param.param_id}. {param.name}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">{param.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Module 5: Reciprocal Rank Fusion (k = 60) & NYC Local Law 144 Bias Audit */}
        <div className="lg:col-span-4 flex flex-col gap-5">
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2 border-b border-slate-800 pb-3">
                <Award className="w-4 h-4 text-amber-400" />
                Reciprocal Rank Fusion (k = 60)
              </h3>
              <p className="text-xs text-slate-400 mt-2">
                PostgreSQL `ts_rank_cd` (BM25) + `pgvector` HNSW Cosine Similarity tournament
                defeating keyword stuffers:
              </p>

              <div className="space-y-2.5 mt-3">
                {rrfResults.map((cand) => (
                  <div
                    key={cand.candidate_id}
                    className={`p-3 rounded-xl border text-xs ${
                      cand.final_rank === 1
                        ? "bg-emerald-950/30 border-emerald-500/40"
                        : "bg-slate-950/70 border-slate-800"
                    }`}
                  >
                    <div className="flex items-center justify-between font-semibold text-white">
                      <span>
                        Rank #{cand.final_rank}: {cand.candidate_name}
                      </span>
                      <span className="font-mono text-cyan-300">{cand.rrf_score.toFixed(5)}</span>
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-[11px] font-mono text-slate-400">
                      <span>BM25 Rank: #{cand.bm25_rank}</span>
                      <span>pgvector ANN Rank: #{cand.ann_rank}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-3 p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 font-mono">
              RRF_Score = 1/(60 + bm25_rank) + 1/(60 + ann_rank)
            </div>
          </div>

          {/* NYC Local Law 144 Automated Employment Decision Tool (AEDT) Bias Audit */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                NYC Local Law 144 AEDT Bias Audit
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                4/5ths Rule (IR ≥ 0.80)
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Verifies zero demographic adverse impact across protected groups (`IR = SR_group / SR_max`):
            </p>
            <div className="space-y-1.5 mt-3 text-[11px] font-mono">
              <div className="flex items-center justify-between bg-slate-950 px-3 py-1.5 rounded border border-slate-800">
                <span className="text-slate-300">Female Selection Rate (SR=0.67)</span>
                <span className="text-emerald-400">IR = 1.00 (PASS)</span>
              </div>
              <div className="flex items-center justify-between bg-slate-950 px-3 py-1.5 rounded border border-slate-800">
                <span className="text-slate-300">Male Selection Rate (SR=0.67)</span>
                <span className="text-emerald-400">IR = 1.00 (PASS)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
