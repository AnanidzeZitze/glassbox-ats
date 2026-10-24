"use client";

import React, { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  Building2,
  Calendar,
  Plus,
  Trash2,
} from "lucide-react";
import { ATSPlatform } from "@/services/api";

export type KanbanStage = "Applied" | "Screening" | "Interview" | "Offer";

export interface KanbanApplicationCard {
  id: string;
  roleTitle: string;
  company: string;
  platform: ATSPlatform;
  atsScore: number;
  jdMatchPct: number;
  stage: KanbanStage;
  appliedDate: string;
  resumeVersion: string;
}

const STAGES: KanbanStage[] = ["Applied", "Screening", "Interview", "Offer"];

const INITIAL_CARDS: KanbanApplicationCard[] = [];

interface KanbanBoardProps {
  currentScore: number | null;
  currentJdMatchPct?: number;
  currentPlatform: ATSPlatform;
  currentRoleTitle: string;
}

const STORAGE_KEY = "glassbox_ats_kanban_cards_v2";

export default function KanbanBoard({
  currentScore,
  currentJdMatchPct = 0.0,
  currentPlatform,
  currentRoleTitle,
}: KanbanBoardProps) {
  const [cards, setCards] = useState<KanbanApplicationCard[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved) return JSON.parse(saved) as KanbanApplicationCard[];
      } catch {
        // Fallback to initial cards
      }
    }
    return INITIAL_CARDS;
  });
  const [newCompany, setNewCompany] = useState("");
  const [newRole, setNewRole] = useState(currentRoleTitle);
  const [draggedId, setDraggedId] = useState<string | null>(null);

  const updateAndPersistCards = (
    updater: (prev: KanbanApplicationCard[]) => KanbanApplicationCard[]
  ) => {
    setCards((prev) => {
      const next = updater(prev);
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Ignore quota errors
        }
      }
      return next;
    });
  };

  const handleAddCard = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompany.trim()) return;
    const card: KanbanApplicationCard = {
      id: `app-${Date.now()}`,
      roleTitle: newRole.trim() || currentRoleTitle,
      company: newCompany.trim(),
      platform: currentPlatform,
      atsScore: currentScore ?? 85.0,
      jdMatchPct: currentJdMatchPct,
      stage: "Applied",
      appliedDate: new Date().toISOString().slice(0, 10),
      resumeVersion: `ats_safe_${currentPlatform.toLowerCase()}.pdf`,
    };
    updateAndPersistCards((prev) => [card, ...prev]);
    setNewCompany("");
  };

  const moveStage = (id: string, dir: -1 | 1) => {
    updateAndPersistCards((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        const idx = STAGES.indexOf(c.stage);
        const nextIdx = Math.max(0, Math.min(STAGES.length - 1, idx + dir));
        return { ...c, stage: STAGES[nextIdx] };
      })
    );
  };

  const deleteCard = (id: string) => {
    updateAndPersistCards((prev) => prev.filter((c) => c.id !== id));
  };

  const handleDropToStage = (targetStage: KanbanStage) => {
    if (!draggedId) return;
    updateAndPersistCards((prev) =>
      prev.map((c) => (c.id === draggedId ? { ...c, stage: targetStage } : c))
    );
    setDraggedId(null);
  };

  return (
    <div className="space-y-6">
      {/* Add New Tailored Application Bar */}
      <form
        onSubmit={handleAddCard}
        className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-xl flex flex-wrap items-center justify-between gap-3"
      >
        <div className="flex items-center gap-2.5">
          <Briefcase className="w-5 h-5 text-cyan-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">
              Tailored Application Pipeline Tracker
            </h2>
            <p className="text-xs text-slate-400">
              Drag cards across stages or log your current tailored resume snapshot
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <input
            type="text"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            placeholder="Role Title..."
            className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
          />
          <input
            type="text"
            value={newCompany}
            onChange={(e) => setNewCompany(e.target.value)}
            placeholder="Company Name (e.g. Databricks)..."
            className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
          />
          <button
            type="submit"
            className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Plus className="w-4 h-4" />
            Log Tailored Application ({currentPlatform})
          </button>
        </div>
      </form>

      {/* 4-Column Kanban Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {STAGES.map((stage) => {
          const stageCards = cards.filter((c) => c.stage === stage);
          return (
            <div
              key={stage}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => handleDropToStage(stage)}
              className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-col gap-3 min-h-[460px]"
            >
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <span className="text-sm font-semibold text-white">{stage}</span>
                <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-cyan-300">
                  {stageCards.length}
                </span>
              </div>

              <div className="space-y-3 flex-1">
                {stageCards.map((card) => (
                  <div
                    key={card.id}
                    draggable
                    onDragStart={() => setDraggedId(card.id)}
                    className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 shadow-md cursor-grab active:cursor-grabbing transition space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-xs font-semibold text-white">
                          {card.roleTitle}
                        </h4>
                        <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                          <Building2 className="w-3 h-3 text-indigo-400" />
                          {card.company}
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {card.platform}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] font-mono bg-slate-900/90 px-2.5 py-1.5 rounded-lg border border-slate-800">
                      <span className="text-emerald-400">
                        ATS Score: {card.atsScore.toFixed(1)}
                      </span>
                      <span className="text-cyan-300">
                        JD Match: {card.jdMatchPct.toFixed(0)}%
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono pt-1 border-t border-slate-900">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {card.appliedDate}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => moveStage(card.id, -1)}
                          disabled={stage === "Applied"}
                          className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 text-slate-300"
                          title="Move Left"
                        >
                          <ArrowLeft className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveStage(card.id, 1)}
                          disabled={stage === "Offer"}
                          className="p-1 rounded hover:bg-slate-800 disabled:opacity-30 text-slate-300"
                          title="Move Right"
                        >
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteCard(card.id)}
                          className="p-1 rounded hover:bg-rose-950 text-slate-400 hover:text-rose-300"
                          title="Delete Card"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
