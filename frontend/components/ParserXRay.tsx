"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  FileCode2,
  FileUp,
  Layers,
  Scissors,
  Sparkles,
} from "lucide-react";
import {
  ATSPlatform,
  ParseXRayResponse,
  parseResumeXRay,
} from "@/services/api";

interface ParserXRayProps {
  xrayData: ParseXRayResponse;
  selectedPlatform: ATSPlatform;
  onSelectPlatform: (platform: ATSPlatform) => void;
  onUpdateXRayData: (data: ParseXRayResponse) => void;
}

const PLATFORMS: {
  id: ATSPlatform;
  label: string;
  engineProfile: string;
  quirkSummary: string;
}[] = [
  {
    id: "WORKDAY",
    label: "Workday",
    engineProfile: "Enterprise ASCII Profile",
    quirkSummary:
      "ISO-8601 dates, collapses bullets into single paragraph, collapses degrees to Master's/Bachelor's, drops multi-word soft skills & OKRs.",
  },
  {
    id: "GREENHOUSE",
    label: "Greenhouse",
    engineProfile: "Sovren Engine Profile",
    quirkSummary:
      "Splits first/last name, integer month/year dates, preserves bullet arrays, retains both technical and soft skills.",
  },
  {
    id: "LEVER",
    label: "Lever",
    engineProfile: "NLP Pattern & Tag-Truncated",
    quirkSummary:
      "YYYY-MM dates, newline-joined summary, concatenates degree+major, truncates skills tags to first 4 tokens (tags[:4]).",
  },
  {
    id: "TALEO",
    label: "Taleo",
    engineProfile: "Strict Verbatim Legacy",
    quirkSummary:
      "55% verbatim keyword weight, zero semantic neighbor credit, strips headers/footers within 1-inch margins.",
  },
  {
    id: "ICIMS",
    label: "iCIMS",
    engineProfile: "Boolean-Weighted Hybrid",
    quirkSummary:
      "45% keyword weight + 10% relevance boost, clusters skills into weighted boolean frequency buckets.",
  },
];

export default function ParserXRay({
  xrayData,
  selectedPlatform,
  onSelectPlatform,
  onUpdateXRayData,
}: ParserXRayProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [streamTab, setStreamTab] = useState<"BBOX" | "STREAM_A" | "STREAM_B">(
    "BBOX"
  );

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    try {
      const result = await parseResumeXRay(file, true);
      onUpdateXRayData(result);
    } finally {
      setIsUploading(false);
    }
  };

  const extraction = xrayData.extraction;
  const canonical = xrayData.canonical;
  const interleavedCount = extraction.interleaved_lines.length;
  const droppedCount = extraction.dropped_header_footer_text.length;
  const activePlatformMeta =
    PLATFORMS.find((p) => p.id === selectedPlatform) || PLATFORMS[0];
  const emulatedPayload = xrayData.emulators[selectedPlatform] || {};

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* LEFT PANEL: Document Preview, Dropzone & XY-Cut++ Spatial Inspector */}
      <div className="lg:col-span-6 flex flex-col gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Eye className="w-5 h-5 text-cyan-400" />
              Dual-Stream Document X-Ray
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Stream A (`pdfminer.six` Linear) vs. Stream B (`PyMuPDF` + Recursive `XY-Cut++`)
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border ${
                interleavedCount === 0
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-300 border-rose-500/40"
              }`}
            >
              {interleavedCount === 0
                ? "Single-Column Layout Verified"
                : `${interleavedCount} Interleaved Line Hazard(s)`}
            </span>
          </div>
        </div>

        {/* File Upload Dropzone */}
        <label className="group relative flex flex-col items-center justify-center border-2 border-dashed border-slate-700 hover:border-cyan-400/70 rounded-xl p-4 cursor-pointer bg-slate-950/50 transition">
          <input
            type="file"
            accept=".pdf,.docx"
            onChange={handleFileChange}
            className="hidden"
          />
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-cyan-500/10 text-cyan-400 group-hover:scale-105 transition">
              <FileUp className="w-5 h-5" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-200">
                {isUploading
                  ? "Running Stage 0 OCR & Stage 1 Dual-Stream Extraction..."
                  : `Active File: ${xrayData.filename}`}
              </p>
              <p className="text-xs text-slate-400">
                Drop any `.pdf` or `.docx` resume to inspect bounding boxes, `&lt;w:tbl&gt;` XML, and header clipping
              </p>
            </div>
          </div>
        </label>

        {/* Stream Mode Selector */}
        <div className="flex items-center justify-between bg-slate-950 p-1.5 rounded-lg border border-slate-800">
          <button
            type="button"
            onClick={() => setStreamTab("BBOX")}
            className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition ${
              streamTab === "BBOX"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Visual Bounding Boxes ({extraction.blocks.length})
          </button>
          <button
            type="button"
            onClick={() => setStreamTab("STREAM_A")}
            className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition ${
              streamTab === "STREAM_A"
                ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Stream A: Naive Linear
          </button>
          <button
            type="button"
            onClick={() => setStreamTab("STREAM_B")}
            className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition ${
              streamTab === "STREAM_B"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Stream B: XY-Cut++ Sorted
          </button>
        </div>

        {/* Visual Document Canvas / Stream Output */}
        <div className="flex-1 bg-slate-950 border border-slate-800 rounded-xl p-4 overflow-y-auto max-h-[500px]">
          {streamTab === "BBOX" && (
            <div className="space-y-3">
              {/* Top 1.0-inch Header Clipping Zone Indicator */}
              <div className="border border-dashed border-rose-500/40 bg-rose-950/20 rounded-lg p-2.5 flex items-center justify-between">
                <span className="text-[11px] font-mono text-rose-300 flex items-center gap-1.5">
                  <Scissors className="w-3.5 h-3.5" />
                  TOP 1.0-INCH HEADER CLIPPING ZONE (y0 &lt; 72pt)
                </span>
                <span className="text-[11px] font-mono text-rose-400">
                  {droppedCount > 0 ? `${droppedCount} items dropped` : "0 contact leaks"}
                </span>
              </div>

              {/* Spatial Blocks List */}
              <div className="space-y-2">
                {extraction.blocks.map((blk) => {
                  const isClipped = blk.y0 < 72;
                  const isRightColumn = blk.x0 >= 300;
                  return (
                    <div
                      key={`${blk.page_no}-${blk.block_no}-${blk.x0}-${blk.y0}`}
                      className={`p-2.5 rounded-lg border text-xs transition ${
                        isClipped
                          ? "bg-rose-950/30 border-rose-500/50 text-rose-200"
                          : isRightColumn
                          ? "bg-amber-950/30 border-amber-500/40 text-amber-200 ml-12"
                          : "bg-slate-900/90 border-slate-800 text-slate-200"
                      }`}
                    >
                      <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-1">
                        <span>
                          Block #{blk.block_no} • bbox=({blk.x0}pt, {blk.y0}pt → {blk.x1}pt,{" "}
                          {blk.y1}pt)
                        </span>
                        <span className="text-cyan-400">
                          {blk.font_name || "Calibri"} {blk.font_size || 11}pt
                        </span>
                      </div>
                      <p className="font-mono text-xs break-words">{blk.text}</p>
                    </div>
                  );
                })}
              </div>

              {/* Bottom 1.0-inch Footer Clipping Zone Indicator */}
              <div className="border border-dashed border-rose-500/40 bg-rose-950/20 rounded-lg p-2.5 flex items-center justify-between">
                <span className="text-[11px] font-mono text-rose-300 flex items-center gap-1.5">
                  <Scissors className="w-3.5 h-3.5" />
                  BOTTOM 1.0-INCH FOOTER CLIPPING ZONE (y1 &gt; page_height - 72pt)
                </span>
                <span className="text-[11px] font-mono text-slate-400">Greenhouse / Taleo Blind Zone</span>
              </div>
            </div>
          )}

          {streamTab === "STREAM_A" && (
            <pre className="text-xs font-mono text-amber-200/90 whitespace-pre-wrap leading-relaxed">
              {extraction.linear_stream_text}
            </pre>
          )}

          {streamTab === "STREAM_B" && (
            <pre className="text-xs font-mono text-emerald-200/90 whitespace-pre-wrap leading-relaxed">
              {extraction.layout_sorted_text}
            </pre>
          )}
        </div>
      </div>

      {/* RIGHT PANEL: Interactive ATS Platform Switcher, Corruption Alerts & Emulated JSON */}
      <div className="lg:col-span-6 flex flex-col gap-4 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="border-b border-slate-800 pb-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-indigo-400" />
              Stage 5 ATS Platform Emulator
            </h2>
            <span className="px-2.5 py-1 rounded-full text-xs font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
              {activePlatformMeta.engineProfile}
            </span>
          </div>

          {/* 5-Platform Switcher Pills */}
          <div className="grid grid-cols-5 gap-2 mt-3">
            {PLATFORMS.map((p) => {
              const active = p.id === selectedPlatform;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onSelectPlatform(p.id)}
                  className={`py-2 px-3 rounded-lg text-xs font-semibold transition border ${
                    active
                      ? "bg-indigo-600 text-white border-indigo-400 shadow-lg shadow-indigo-600/25"
                      : "bg-slate-950 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-400 mt-2.5 bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5">
            <strong className="text-slate-200">{activePlatformMeta.label} Behavior:</strong>{" "}
            {activePlatformMeta.quirkSummary}
          </p>
        </div>

        {/* Corruption & Hazard Diagnostic Banners */}
        <div className="space-y-2.5">
          {interleavedCount > 0 ? (
            <div className="bg-rose-950/40 border border-rose-500/50 rounded-xl p-3.5 text-xs text-rose-200">
              <div className="flex items-center justify-between font-semibold text-rose-300 mb-1.5">
                <span className="flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                  CRITICAL: Two-Column X-Coordinate Interleaving Detected ({interleavedCount} lines)
                </span>
                <span className="font-mono bg-rose-500/20 px-2 py-0.5 rounded text-rose-300">
                  -39.5 pts Parse Penalty
                </span>
              </div>
              <div className="space-y-1.5 mt-2">
                {extraction.interleaved_lines.map((item, idx) => (
                  <div
                    key={idx}
                    className="bg-slate-950/80 border border-rose-500/30 rounded p-2 font-mono text-[11px]"
                  >
                    <div className="text-rose-300">{item.line_text}</div>
                    <div className="text-slate-400 mt-0.5">
                      Col 1: &quot;{item.left_block_text}&quot; ↔ Col 2: &quot;
                      {item.right_block_text}&quot; (Δx = {item.horizontal_gap_pt}pt &gt; 15pt)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-xl p-3 flex items-center justify-between text-xs text-emerald-200">
              <span className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Zero Multi-Column Interleaving — Reading Order Intact
              </span>
              <span className="font-mono text-emerald-400">100% Stream Alignment</span>
            </div>
          )}

          {/* Dropped Header/Footer Contact Alert */}
          {droppedCount > 0 && (
            <div className="bg-amber-950/40 border border-amber-500/50 rounded-xl p-3 text-xs text-amber-200">
              <div className="font-semibold text-amber-300 flex items-center gap-1.5 mb-1">
                <Scissors className="w-4 h-4 text-amber-400" />
                Dropped Header/Footer Contact Fields ({droppedCount} clipped regions)
              </div>
              <ul className="list-disc list-inside font-mono text-[11px] space-y-1 text-amber-100/90">
                {extraction.dropped_header_footer_text.map((txt, i) => (
                  <li key={i}>{txt}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Lever Tag Truncation & Non-Standard Header Alert */}
          {selectedPlatform === "LEVER" && (
            <div className="bg-indigo-950/40 border border-indigo-500/40 rounded-xl p-3 text-xs text-indigo-200 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-400 shrink-0" />
                <span>
                  <strong>Lever `tags[:4]` Truncation Active:</strong> Dropped{" "}
                  {Math.max(0, canonical.skills.length - 4)} of {canonical.skills.length} skills (
                  {canonical.skills.slice(4).join(", ")}).
                </span>
              </span>
            </div>
          )}
        </div>

        {/* Live Emulated JSON Payload Viewer */}
        <div className="flex-1 flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
          <div className="bg-slate-900/90 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-xs">
            <span className="font-mono text-slate-300 flex items-center gap-1.5">
              <FileCode2 className="w-4 h-4 text-cyan-400" />
              {selectedPlatform.toLowerCase()}_emulated_payload.json
            </span>
            <span className="text-[11px] text-slate-400">
              100% Deterministic Clean-Room Adapter
            </span>
          </div>
          <pre className="p-4 text-xs font-mono text-cyan-300/95 overflow-auto max-h-[380px] leading-relaxed">
            {JSON.stringify(emulatedPayload, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
