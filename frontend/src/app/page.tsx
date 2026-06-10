import { Bot, FileCode2, History, PanelRightOpen, Sparkles, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const sessions = [
  {
    id: "session-alpha",
    title: "Agent bootstrap",
    time: "2m ago",
    active: true,
  },
  {
    id: "session-beta",
    title: "Memory review",
    time: "21m ago",
    active: false,
  },
  {
    id: "session-gamma",
    title: "Skill tuning",
    time: "Yesterday",
    active: false,
  },
];

const inspectorNotes = [
  "System prompt files remain editable and visible to the operator.",
  "Streaming traces and skill files will land in this panel in later stories.",
  "The inspector collapses below desktop width to keep the chat stage readable.",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(29,78,216,0.12),_transparent_34%),radial-gradient(circle_at_bottom_right,_rgba(245,158,11,0.12),_transparent_28%),#fafafa] px-4 pb-4 pt-24 text-foreground sm:px-6 sm:pt-28 lg:px-8">
      <div className="fixed inset-x-4 top-4 z-20 sm:inset-x-6 lg:inset-x-8">
        <div className="mx-auto flex h-16 w-full max-w-[1600px] items-center justify-between rounded-[24px] border border-white/80 bg-white/65 px-5 shadow-[0_18px_60px_rgba(15,23,42,0.10)] backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-primary/15 bg-primary/[0.08] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-primary/70">
              IDE
            </span>
            <span className="text-lg font-semibold tracking-tight text-[#002FA7] sm:text-xl">mini OpenClaw</span>
          </div>
          <a
            className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-950"
            href="https://fufan.ai"
            rel="noreferrer"
            target="_blank"
          >
            赋范空间
          </a>
        </div>
      </div>

      <div className="mx-auto flex min-h-[calc(100vh-7rem)] w-full max-w-[1600px] flex-col rounded-[30px] border border-white/80 bg-white/55 p-3 shadow-[0_28px_120px_rgba(15,23,42,0.10)] backdrop-blur-xl sm:min-h-[calc(100vh-8rem)] sm:p-4">
        <section className="grid min-h-[calc(100vh-9rem)] gap-3 sm:min-h-[calc(100vh-10rem)] lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_420px]">
          <aside className="rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(248,250,252,0.72))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
            <div className="space-y-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-primary/60">Workspace</p>
                <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">mini OpenClaw</h1>
                <p className="mt-2 text-sm leading-6 text-slate-600">IDE-style agent shell with live sessions, staged reasoning, and file-first inspection.</p>
              </div>

              <nav className="space-y-2">
                <button className="flex w-full items-center gap-3 rounded-2xl border border-primary/15 bg-primary/[0.08] px-4 py-3 text-left text-sm font-medium text-slate-950 shadow-sm">
                  <Bot className="h-4 w-4 text-primary" />
                  Chat
                </button>
                <button className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm text-slate-600 transition-colors hover:bg-white/70 hover:text-slate-950">
                  <History className="h-4 w-4 text-slate-400" />
                  Memory
                </button>
                <button className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm text-slate-600 transition-colors hover:bg-white/70 hover:text-slate-950">
                  <Sparkles className="h-4 w-4 text-slate-400" />
                  Skills
                </button>
              </nav>

              <div className="rounded-[24px] border border-slate-200/80 bg-white/80 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">Sessions</p>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-500">3</span>
                </div>
                <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                  {sessions.map((session) => (
                    <button
                      key={session.id}
                      className={[
                        "w-full rounded-2xl border px-4 py-3 text-left transition-all",
                        session.active
                          ? "border-primary/20 bg-[linear-gradient(135deg,rgba(37,99,235,0.10),rgba(255,255,255,0.92))] shadow-sm"
                          : "border-transparent bg-transparent hover:border-slate-200 hover:bg-white/70",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-medium text-slate-900">{session.title}</span>
                        <span className="text-xs text-slate-500">{session.time}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">session_id: {session.id}</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </aside>

          <div className="grid min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
            <section className="flex min-h-[640px] flex-col rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,247,251,0.78))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] sm:p-6">
              <div className="flex flex-col gap-4 border-b border-slate-200/80 pb-5 sm:flex-row sm:items-end sm:justify-between">
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.32em] text-primary/60">Stage</p>
                  <h2 className="text-3xl font-semibold tracking-tight text-slate-950">Transparent agent session</h2>
                  <p className="max-w-2xl text-sm leading-6 text-slate-600">This center column stays dominant while the right inspector hides below desktop width.</p>
                </div>
                <div className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white/90 px-3 py-3 shadow-sm">
                  <WandSparkles className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium text-slate-700">Ready for streaming chat UI</span>
                </div>
              </div>

              <div className="flex flex-1 flex-col justify-between gap-6 pt-6">
                <div className="space-y-4">
                  <article className="max-w-[82%] rounded-[24px] border border-slate-200/80 bg-white/90 p-5 shadow-sm">
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">User</p>
                    <p className="mt-3 text-sm leading-7 text-slate-700">Map the next UI milestones and keep the reasoning visible without turning the stage into clutter.</p>
                  </article>

                  <article className="ml-auto max-w-[88%] rounded-[24px] border border-primary/15 bg-[linear-gradient(135deg,rgba(255,255,255,0.94),rgba(219,234,254,0.92))] p-5 shadow-[0_20px_50px_rgba(37,99,235,0.10)]">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-primary/70">
                      <Bot className="h-4 w-4" />
                      Assistant
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-700">The shell is in place: a fixed-width sidebar, a flexible stage, and an inspector rail reserved for editable prompt files and skill docs.</p>
                    <div className="mt-4 rounded-2xl border border-primary/10 bg-white/75 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Upcoming streamed block</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">Thoughts, tool calls, and tool results will stack here as a collapsible trace in the next story.</p>
                    </div>
                  </article>
                </div>

                <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-4 shadow-sm">
                  <div className="flex flex-col gap-3 lg:flex-row">
                    <Input
                      aria-label="Chat composer"
                      className="h-14 rounded-2xl border-slate-200 bg-slate-50/80 px-4 text-base"
                      defaultValue="Ask the agent to inspect a skill, fetch a file, or explain the current session."
                      readOnly
                    />
                    <Button className="h-14 rounded-2xl px-6 text-base lg:min-w-36">Send</Button>
                  </div>
                </div>
              </div>
            </section>

            <section className="hidden min-h-[640px] flex-col rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.84),rgba(247,248,252,0.80))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] xl:flex">
              <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 pb-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.32em] text-primary/60">Inspector</p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Prompt and skill surfaces</h2>
                </div>
                <div className="rounded-2xl border border-slate-200/80 bg-white/85 p-3 text-slate-500">
                  <PanelRightOpen className="h-5 w-5" />
                </div>
              </div>

              <div className="mt-6 flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white/85 px-4 py-3 shadow-sm">
                <FileCode2 className="h-4 w-4 text-primary" />
                <div>
                  <p className="text-sm font-medium text-slate-900">memory/MEMORY.md</p>
                  <p className="text-xs text-slate-500">File picker and Monaco editor land in US-023.</p>
                </div>
              </div>

              <div className="mt-4 flex-1 rounded-[24px] border border-dashed border-slate-200 bg-[linear-gradient(180deg,rgba(241,245,249,0.55),rgba(255,255,255,0.82))] p-5">
                <div className="space-y-4">
                  {inspectorNotes.map((note) => (
                    <article key={note} className="rounded-2xl border border-white/80 bg-white/85 p-4 shadow-sm">
                      <p className="text-sm leading-6 text-slate-600">{note}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
