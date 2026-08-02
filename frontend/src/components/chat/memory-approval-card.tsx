"use client";

import { Check, Clock3, FileText, ShieldCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { MemoryProposal } from "@/lib/api";

type MemoryApprovalCardProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  pendingCount: number;
  proposal: MemoryProposal | null;
  onApprove: () => void;
  onClose: () => void;
  onReject: () => void;
};

const targetLabels: Record<MemoryProposal["target"], string> = {
  agent_behavior: "Agent persona",
  user_capsule: "User profile",
  project_memory: "Project memory",
  relationship_memory: "Relationship primer",
};

function formatProposalTime(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? "just now"
    : new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function MemoryApprovalCard({
  isOpen,
  isSubmitting,
  pendingCount,
  proposal,
  onApprove,
  onClose,
  onReject,
}: MemoryApprovalCardProps) {
  if (!isOpen || !proposal) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-slate-950/30 p-4 backdrop-blur-[2px] sm:items-center sm:justify-center" role="presentation">
      <section aria-labelledby="memory-approval-title" aria-modal="true" className="w-full max-w-xl overflow-hidden rounded-[28px] border border-emerald-100 bg-[#fffdf8] shadow-[0_30px_100px_rgba(15,23,42,0.28)]" role="dialog">
        <div className="border-b border-emerald-100 bg-[linear-gradient(135deg,#ecfdf5,#fefce8)] px-5 py-4 sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-2xl bg-emerald-600 p-2 text-white shadow-sm">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">Memory review</p>
                <h2 className="mt-1 text-xl font-semibold tracking-[-0.03em] text-slate-950" id="memory-approval-title">Keep this for future chats?</h2>
              </div>
            </div>
            <button aria-label="Review later" className="rounded-xl p-2 text-slate-400 transition hover:bg-white/70 hover:text-slate-700" disabled={isSubmitting} onClick={onClose} type="button">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="space-y-5 px-5 py-5 sm:px-6">
          <blockquote className="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm leading-6 text-slate-700 shadow-sm">
            {proposal.content}
          </blockquote>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-emerald-50 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-700">Layer</p>
              <p className="mt-1 text-sm font-medium text-emerald-950">{targetLabels[proposal.target]}</p>
            </div>
            <div className="rounded-2xl bg-amber-50 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-700">Confidence</p>
              <p className="mt-1 text-sm font-medium capitalize text-amber-950">{proposal.confidence}</p>
            </div>
            <div className="rounded-2xl bg-slate-100 px-3 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Scope</p>
              <p className="mt-1 text-sm font-medium capitalize text-slate-800">{proposal.scope.replace("_", " ")}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white/70 p-4">
            <div className="flex gap-2 text-sm font-semibold text-slate-800">
              <FileText className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              Why the agent proposed it
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{proposal.rationale}</p>
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
              <Clock3 className="h-3.5 w-3.5" />
              {proposal.session_id || "current session"} · {formatProposalTime(proposal.created_at)}
            </div>
          </div>

          <p className="text-xs leading-5 text-slate-500">Approval writes a provenance-preserving Markdown projection and loads this memory only in a future chat bootstrap.</p>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-slate-200 bg-white/80 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <Button className="rounded-xl text-slate-600" disabled={isSubmitting} onClick={onClose} type="button" variant="ghost">Review later</Button>
          <div className="flex gap-2">
            <Button className="rounded-xl border-rose-200 text-rose-700 hover:bg-rose-50 hover:text-rose-800" disabled={isSubmitting} onClick={onReject} type="button" variant="outline">
              <X className="mr-1.5 h-4 w-4" />
              Reject
            </Button>
            <Button className="rounded-xl bg-emerald-600 text-white hover:bg-emerald-700" disabled={isSubmitting} onClick={onApprove} type="button">
              <Check className="mr-1.5 h-4 w-4" />
              {isSubmitting ? "Saving..." : "Approve"}
            </Button>
          </div>
        </div>
        {pendingCount > 1 ? <p className="border-t border-slate-100 bg-white px-6 py-2 text-center text-xs text-slate-400">{pendingCount - 1} more proposal{pendingCount === 2 ? "" : "s"} waiting after this review.</p> : null}
      </section>
    </div>
  );
}
