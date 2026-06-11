"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronDown,
  FileCode2,
  History,
  Loader2,
  PanelRightOpen,
  Save,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getFile, listSessions, saveFile, streamChat, type ChatEvent, type SessionSummary } from "@/lib/api";

const MonacoEditor = dynamic(() => import("@/components/monaco-markdown-editor").then((module) => module.MonacoMarkdownEditor), {
  ssr: false,
});

type NavId = "chat" | "memory" | "skills";

type InspectorFile = {
  label: string;
  path: string;
};

type TraceItem =
  | { kind: "thought"; content: string }
  | { kind: "tool_call"; name: string; input?: unknown }
  | { kind: "tool_result"; name: string; content: string };

type ChatMessage =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; trace: TraceItem[] };

const navItems: Array<{ id: NavId; label: string; icon: typeof Bot }> = [
  { id: "chat", label: "Chat", icon: Bot },
  { id: "memory", label: "Memory", icon: History },
  { id: "skills", label: "Skills", icon: Sparkles },
];

const inspectorFiles: InspectorFile[] = [
  { label: "Memory", path: "backend/memory/MEMORY.md" },
  { label: "Agents", path: "backend/workspace/AGENTS.md" },
  { label: "Weather Skill", path: "backend/skills/get_weather/SKILL.md" },
];

const starterMessages: ChatMessage[] = [
  {
    id: "starter-user",
    role: "user",
    content: "Map the next UI milestones and keep the reasoning visible without turning the stage into clutter.",
  },
  {
    id: "starter-assistant",
    role: "assistant",
    content:
      "The shell is in place: a fixed-width sidebar, a flexible stage, and an inspector rail reserved for editable prompt files and skill docs.",
    trace: [
      {
        kind: "thought",
        content: "The chat stage should show the work without making the final answer harder to scan.",
      },
      {
        kind: "tool_call",
        name: "listSessions",
        input: { source: "sidebar bootstrap" },
      },
      {
        kind: "tool_result",
        name: "listSessions",
        content: "Session metadata is available for the active conversation context.",
      },
    ],
  },
];

function createSessionId(): string {
  return `session-${Date.now()}`;
}

function createMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function formatTimestamp(value: string): string {
  if (!value) {
    return "No activity yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function stringifyToolInput(input: unknown): string {
  if (typeof input === "string") {
    return input;
  }

  if (input == null) {
    return "{}";
  }

  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

function appendEvent(message: Extract<ChatMessage, { role: "assistant" }>, event: ChatEvent): Extract<ChatMessage, { role: "assistant" }> {
  if (event.type === "final") {
    return { ...message, content: message.content + event.content };
  }

  if (event.type === "thought") {
    return {
      ...message,
      trace: [...message.trace, { kind: "thought", content: event.content }],
    };
  }

  if (event.type === "tool_call") {
    return {
      ...message,
      trace: [...message.trace, { kind: "tool_call", name: event.name, input: event.input }],
    };
  }

  return {
    ...message,
    trace: [...message.trace, { kind: "tool_result", name: event.name, content: event.content }],
  };
}

function TraceBlock({ messageId, trace }: { messageId: string; trace: TraceItem[] }) {
  if (trace.length === 0) {
    return null;
  }

  return (
    <details className="mt-4 rounded-2xl border border-primary/10 bg-white/75" id={`${messageId}-trace`}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-slate-700 marker:content-none">
        <span>Reasoning trace</span>
        <span className="flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-500">
          {trace.length} events
          <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <div className="space-y-3 border-t border-slate-200/80 px-4 py-4">
        {trace.map((item, index) => {
          if (item.kind === "thought") {
            return (
              <article key={`${messageId}-thought-${index}`} className="rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Thought</p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{item.content}</p>
              </article>
            );
          }

          if (item.kind === "tool_call") {
            return (
              <article key={`${messageId}-tool-call-${index}`} className="rounded-2xl border border-amber-200/80 bg-amber-50/70 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-700">Tool Call</p>
                <p className="mt-2 text-sm font-medium text-slate-900">{item.name}</p>
                <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-white/85 p-3 text-xs leading-6 text-slate-600">
                  {stringifyToolInput(item.input)}
                </pre>
              </article>
            );
          }

          return (
            <article key={`${messageId}-tool-result-${index}`} className="rounded-2xl border border-emerald-200/80 bg-emerald-50/70 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700">Tool Result</p>
              <p className="mt-2 text-sm font-medium text-slate-900">{item.name}</p>
              <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-white/85 p-3 text-xs leading-6 text-slate-600">
                {item.content}
              </pre>
            </article>
          );
        })}
      </div>
    </details>
  );
}

export default function Home() {
  const [activeNav, setActiveNav] = useState<NavId>("chat");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messages, setMessages] = useState<Record<string, ChatMessage[]>>({});
  const [draft, setDraft] = useState("Ask the agent to inspect a skill, fetch a file, or explain the current session.");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [selectedInspectorPath, setSelectedInspectorPath] = useState<string>(inspectorFiles[0]?.path ?? "");
  const [editorValue, setEditorValue] = useState("");
  const [loadedFilePath, setLoadedFilePath] = useState("");
  const [isInspectorLoading, setIsInspectorLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const initialInspectorLoad = useRef(false);

  useEffect(() => {
    let mounted = true;

    void listSessions()
      .then((items) => {
        if (!mounted) {
          return;
        }

        setSessions(items);
        setActiveSessionId((current) => current || items[0]?.name || createSessionId());
      })
      .catch(() => {
        if (!mounted) {
          return;
        }

        setSessions([]);
        setActiveSessionId((current) => current || createSessionId());
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedInspectorPath) {
      return;
    }

    let mounted = true;
    setIsInspectorLoading(true);
    setInspectorError(null);

    void getFile(selectedInspectorPath)
      .then((payload) => {
        if (!mounted) {
          return;
        }

        setEditorValue(payload.content);
        setLoadedFilePath(payload.path);
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load file";
        setInspectorError(message);
        toast.error("Failed to load file", { description: message });
      })
      .finally(() => {
        if (mounted) {
          setIsInspectorLoading(false);
          initialInspectorLoad.current = true;
        }
      });

    return () => {
      mounted = false;
    };
  }, [selectedInspectorPath]);

  const activeSession = sessions.find((session) => session.name === activeSessionId) ?? null;
  const activeNavLabel = navItems.find((item) => item.id === activeNav)?.label ?? "Chat";
  const selectedInspectorLabel = inspectorFiles.find((item) => item.path === selectedInspectorPath)?.label ?? selectedInspectorPath;
  const sessionMessages = useMemo(() => {
    if (!activeSessionId) {
      return starterMessages;
    }

    return messages[activeSessionId] ?? starterMessages;
  }, [activeSessionId, messages]);
  const isDirty = initialInspectorLoad.current && loadedFilePath === selectedInspectorPath && editorValue !== "";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = draft.trim();
    if (!trimmed || isStreaming || !activeSessionId) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createMessageId("user"),
      role: "user",
      content: trimmed,
    };
    const assistantId = createMessageId("assistant");
    const assistantSeed: Extract<ChatMessage, { role: "assistant" }> = {
      id: assistantId,
      role: "assistant",
      content: "",
      trace: [],
    };

    setDraft("");
    setStreamError(null);
    setIsStreaming(true);
    setMessages((current) => ({
      ...current,
      [activeSessionId]: [...(current[activeSessionId] ?? []), userMessage, assistantSeed],
    }));

    try {
      for await (const chatEvent of streamChat(trimmed, activeSessionId)) {
        setMessages((current) => {
          const nextMessages = [...(current[activeSessionId] ?? [])];
          const index = nextMessages.findIndex((message) => message.id === assistantId && message.role === "assistant");

          if (index === -1) {
            return current;
          }

          const currentAssistant = nextMessages[index] as Extract<ChatMessage, { role: "assistant" }>;
          nextMessages[index] = appendEvent(currentAssistant, chatEvent);

          return {
            ...current,
            [activeSessionId]: nextMessages,
          };
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Streaming failed";
      setStreamError(message);
      setMessages((current) => {
        const nextMessages = [...(current[activeSessionId] ?? [])];
        const index = nextMessages.findIndex((item) => item.id === assistantId && item.role === "assistant");

        if (index === -1) {
          return current;
        }

        const failedAssistant = nextMessages[index] as Extract<ChatMessage, { role: "assistant" }>;
        nextMessages[index] = {
          ...failedAssistant,
          content: failedAssistant.content || "The stream ended before the assistant returned a final reply.",
          trace: [
            ...failedAssistant.trace,
            {
              kind: "tool_result",
              name: "stream_error",
              content: message,
            },
          ],
        };

        return {
          ...current,
          [activeSessionId]: nextMessages,
        };
      });
    } finally {
      setIsStreaming(false);
    }
  }

  async function handleSaveInspector() {
    if (!selectedInspectorPath || isSaving) {
      return;
    }

    setIsSaving(true);
    setInspectorError(null);

    try {
      const payload = await saveFile(selectedInspectorPath, editorValue);
      setEditorValue(payload.content);
      setLoadedFilePath(payload.path);
      toast.success("Saved file", { description: payload.path });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save file";
      setInspectorError(message);
      toast.error("Failed to save file", { description: message });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <>
      <Toaster position="top-right" richColors />
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

                <nav className="space-y-2" aria-label="Primary">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === activeNav;

                    return (
                      <button
                        key={item.id}
                        className={[
                          "flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition-all",
                          active
                            ? "border-primary/20 bg-primary/[0.08] font-medium text-slate-950 shadow-sm"
                            : "border-transparent bg-transparent text-slate-600 hover:border-slate-200 hover:bg-white/70 hover:text-slate-950",
                        ].join(" ")}
                        onClick={() => setActiveNav(item.id)}
                        type="button"
                      >
                        <Icon className={["h-4 w-4", active ? "text-primary" : "text-slate-400"].join(" ")} />
                        {item.label}
                      </button>
                    );
                  })}
                </nav>

                <div className="rounded-[24px] border border-slate-200/80 bg-white/80 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">Sessions</p>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-500">{sessions.length}</span>
                  </div>
                  <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                    {sessions.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-500">
                        <p>No sessions yet.</p>
                        <p className="mt-1 text-xs">The chat stage will keep working with a local draft session.</p>
                      </div>
                    ) : (
                      sessions.map((session) => {
                        const active = session.name === activeSessionId;

                        return (
                          <button
                            key={session.name}
                            className={[
                              "w-full rounded-2xl border px-4 py-3 text-left transition-all",
                              active
                                ? "border-primary/20 bg-[linear-gradient(135deg,rgba(37,99,235,0.10),rgba(255,255,255,0.92))] shadow-sm"
                                : "border-transparent bg-transparent hover:border-slate-200 hover:bg-white/70",
                            ].join(" ")}
                            onClick={() => setActiveSessionId(session.name)}
                            type="button"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="truncate text-sm font-medium text-slate-900">{session.name}</span>
                              <span className="text-xs text-slate-500">{session.message_count} msgs</span>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">{formatTimestamp(session.last_modified)}</p>
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </aside>

            <div className="grid min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
              <section className="flex min-h-[640px] flex-col rounded-[26px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,247,251,0.78))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] sm:p-6">
                <div className="flex flex-col gap-4 border-b border-slate-200/80 pb-5 sm:flex-row sm:items-end sm:justify-between">
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.32em] text-primary/60">Stage</p>
                    <h2 className="text-3xl font-semibold tracking-tight text-slate-950">{activeNavLabel} workspace</h2>
                    <p className="max-w-2xl text-sm leading-6 text-slate-600">The stage now streams agent events live and tucks thought traces behind a collapsible block on every assistant reply.</p>
                  </div>
                  <div className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white/90 px-3 py-3 shadow-sm">
                    {isStreaming ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : <WandSparkles className="h-4 w-4 text-primary" />}
                    <span className="text-sm font-medium text-slate-700">Session {activeSession?.name ?? activeSessionId ?? "draft"}</span>
                  </div>
                </div>

                <div className="flex flex-1 flex-col justify-between gap-6 pt-6">
                  <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
                    {sessionMessages.map((message) => {
                      if (message.role === "user") {
                        return (
                          <article key={message.id} className="max-w-[82%] rounded-[24px] border border-slate-200/80 bg-white/90 p-5 shadow-sm">
                            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">User</p>
                            <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{message.content}</p>
                          </article>
                        );
                      }

                      return (
                        <article key={message.id} className="ml-auto max-w-[88%] rounded-[24px] border border-primary/15 bg-[linear-gradient(135deg,rgba(255,255,255,0.94),rgba(219,234,254,0.92))] p-5 shadow-[0_20px_50px_rgba(37,99,235,0.10)]">
                          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-primary/70">
                            <Bot className="h-4 w-4" />
                            Assistant
                          </div>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                            {message.content || (isStreaming ? "Streaming response..." : "Waiting for assistant output.")}
                          </p>
                          <TraceBlock messageId={message.id} trace={message.trace} />
                        </article>
                      );
                    })}
                  </div>

                  <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-4 shadow-sm">
                    <form className="flex flex-col gap-3 lg:flex-row" onSubmit={handleSubmit}>
                      <Input
                        aria-label="Chat composer"
                        className="h-14 rounded-2xl border-slate-200 bg-slate-50/80 px-4 text-base"
                        onChange={(event) => setDraft(event.target.value)}
                        placeholder="Ask the agent to inspect a skill, fetch a file, or explain the current session."
                        value={draft}
                      />
                      <Button className="h-14 rounded-2xl px-6 text-base lg:min-w-36" disabled={isStreaming || !draft.trim()} type="submit">
                        {isStreaming ? "Streaming..." : "Send"}
                      </Button>
                    </form>
                    {streamError ? <p className="mt-3 text-sm text-rose-600">{streamError}</p> : null}
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
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-900">{selectedInspectorLabel}</p>
                    <p className="truncate text-xs text-slate-500">{selectedInspectorPath}</p>
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-3">
                  <select
                    className="h-11 flex-1 rounded-2xl border border-slate-200/80 bg-white/90 px-4 text-sm text-slate-700 shadow-sm outline-none transition focus:border-primary/30"
                    onChange={(event) => setSelectedInspectorPath(event.target.value)}
                    value={selectedInspectorPath}
                  >
                    {inspectorFiles.map((file) => (
                      <option key={file.path} value={file.path}>
                        {file.label}
                      </option>
                    ))}
                  </select>
                  <Button className="h-11 rounded-2xl px-4" disabled={isInspectorLoading || isSaving} onClick={handleSaveInspector} type="button">
                    {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                    Save
                  </Button>
                </div>

                <div className="mt-4 flex-1 overflow-hidden rounded-[24px] border border-slate-200 bg-white/90 shadow-sm">
                  {isInspectorLoading ? (
                    <div className="flex h-full items-center justify-center gap-3 text-sm text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      Loading file...
                    </div>
                  ) : (
                    <MonacoEditor height="100%" onChange={setEditorValue} onSave={handleSaveInspector} value={editorValue} />
                  )}
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 text-sm text-slate-600 shadow-sm">
                  <p>{isSaving ? "Saving changes..." : inspectorError ? `Save error: ${inspectorError}` : "Cmd/Ctrl+S saves the current file."}</p>
                </div>
              </section>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
