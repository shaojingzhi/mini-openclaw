"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronDown,
  FileText,
  FileCode2,
  FolderTree,
  History,
  Loader2,
  PanelRightOpen,
  RotateCcw,
  Save,
  Sparkles,
  Settings2,
  WandSparkles,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getFile, getSession, getTrace, listSessions, listTraces, saveFile, streamChat, type ChatEvent, type ModelSettings, type SessionSummary, type TraceDetail, type TraceSummary } from "@/lib/api";

const MonacoEditor = dynamic(() => import("@/components/monaco-markdown-editor").then((module) => module.MonacoMarkdownEditor), {
  ssr: false,
});

type NavId = "chat" | "memory" | "skills";
type InspectorGroup = "workspace" | "memory" | "skills";

type InspectorFile = {
  label: string;
  path: string;
  group: InspectorGroup;
};

type TraceItem =
  | { kind: "thought"; content: string }
  | { kind: "tool_call"; name: string; input?: unknown }
  | { kind: "tool_result"; name: string; content: string };

type ChatMessage =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; trace: TraceItem[] };

type SessionStatus = "idle" | "loading" | "ready" | "error";
type TraceStatus = "idle" | "loading" | "ready" | "error";

const navItems: Array<{ id: NavId; label: string; icon: typeof Bot }> = [
  { id: "chat", label: "Chat", icon: Bot },
  { id: "memory", label: "Memory", icon: History },
  { id: "skills", label: "Skills", icon: Sparkles },
];

const inspectorFiles: InspectorFile[] = [
  { label: "MEMORY.md", path: "backend/memory/MEMORY.md", group: "memory" },
  { label: "SOUL.md", path: "backend/workspace/SOUL.md", group: "workspace" },
  { label: "IDENTITY.md", path: "backend/workspace/IDENTITY.md", group: "workspace" },
  { label: "USER.md", path: "backend/workspace/USER.md", group: "workspace" },
  { label: "AGENTS.md", path: "backend/workspace/AGENTS.md", group: "workspace" },
  { label: "SKILLS_SNAPSHOT.md", path: "backend/workspace/SKILLS_SNAPSHOT.md", group: "workspace" },
  { label: "get_weather / SKILL.md", path: "backend/skills/get_weather/SKILL.md", group: "skills" },
];

const MODEL_SETTINGS_STORAGE_KEY = "mini-openclaw-model-settings";
const defaultModelSettings: ModelSettings = {
  apiKey: "",
  baseUrl: "https://api.codexzh.com/v1",
  model: "gpt-5.4",
};

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

function getInspectorGroupLabel(group: InspectorGroup): string {
  if (group === "workspace") {
    return "Workspace";
  }

  if (group === "memory") {
    return "Memory";
  }

  return "Skills";
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

function toChatMessages(items: Array<{ role: string; content: string }>): ChatMessage[] {
  return items
    .filter((item) => item.role === "user" || item.role === "assistant")
    .map((item, index) => {
      if (item.role === "user") {
        return {
          id: `session-user-${index}`,
          role: "user",
          content: item.content,
        } satisfies ChatMessage;
      }

      return {
        id: `session-assistant-${index}`,
        role: "assistant",
        content: item.content,
        trace: [],
      } satisfies ChatMessage;
    });
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
  const [sessionStatus, setSessionStatus] = useState<Record<string, SessionStatus>>({});
  const [traceSummaries, setTraceSummaries] = useState<TraceSummary[]>([]);
  const [traceDetails, setTraceDetails] = useState<Record<string, TraceDetail>>({});
  const [traceStatus, setTraceStatus] = useState<TraceStatus>("idle");
  const [activeTraceId, setActiveTraceId] = useState<string>("");
  const [draft, setDraft] = useState("Ask the agent to inspect a skill, fetch a file, or explain the current session.");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [selectedInspectorPath, setSelectedInspectorPath] = useState<string>(inspectorFiles[0]?.path ?? "");
  const [editorValue, setEditorValue] = useState("");
  const [loadedFilePath, setLoadedFilePath] = useState("");
  const [isInspectorLoading, setIsInspectorLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const [modelSettings, setModelSettings] = useState<ModelSettings>(defaultModelSettings);
  const initialInspectorLoad = useRef(false);

  async function refreshTraces(preferredTraceId?: string) {
    try {
      setTraceStatus("loading");
      const items = await listTraces();
      setTraceSummaries(items);
      setActiveTraceId((current) => preferredTraceId || current || items[0]?.trace_id || "");
      setTraceStatus("ready");
    } catch {
      setTraceSummaries([]);
      setTraceStatus("error");
    }
  }
  const stageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const composerRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const raw = window.localStorage.getItem(MODEL_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as Partial<ModelSettings>;
      setModelSettings({
        apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : defaultModelSettings.apiKey,
        baseUrl: typeof parsed.baseUrl === "string" && parsed.baseUrl.trim() ? parsed.baseUrl : defaultModelSettings.baseUrl,
        model: typeof parsed.model === "string" && parsed.model.trim() ? parsed.model : defaultModelSettings.model,
      });
    } catch {
      window.localStorage.removeItem(MODEL_SETTINGS_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(MODEL_SETTINGS_STORAGE_KEY, JSON.stringify(modelSettings));
  }, [modelSettings]);

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

  useEffect(() => {
    if (activeNav === "memory") {
      setSelectedInspectorPath("backend/memory/MEMORY.md");
      return;
    }

    if (activeNav === "skills") {
      setSelectedInspectorPath("backend/skills/get_weather/SKILL.md");
      return;
    }

    setSelectedInspectorPath((current) => current || inspectorFiles[0]?.path || "");
  }, [activeNav]);

  useEffect(() => {
    void refreshTraces();
  }, []);

  useEffect(() => {
    if (!activeTraceId || traceDetails[activeTraceId]) {
      return;
    }

    let mounted = true;
    setTraceStatus("loading");

    void getTrace(activeTraceId)
      .then((detail) => {
        if (!mounted) {
          return;
        }

        setTraceDetails((current) => ({
          ...current,
          [activeTraceId]: detail,
        }));
        setTraceStatus("ready");
      })
      .catch(() => {
        if (!mounted) {
          return;
        }

        setTraceStatus("error");
      });

    return () => {
      mounted = false;
    };
  }, [activeTraceId, traceDetails]);

  useEffect(() => {
    if (!activeSessionId || messages[activeSessionId]) {
      return;
    }

    let mounted = true;
    setSessionStatus((current) => ({ ...current, [activeSessionId]: "loading" }));

    void getSession(activeSessionId)
      .then((payload) => {
        if (!mounted) {
          return;
        }

        setMessages((current) => ({
          ...current,
          [activeSessionId]: payload.length > 0 ? toChatMessages(payload) : starterMessages,
        }));
        setSessionStatus((current) => ({ ...current, [activeSessionId]: "ready" }));
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load session";
        setMessages((current) => ({
          ...current,
          [activeSessionId]: starterMessages,
        }));
        setSessionStatus((current) => ({ ...current, [activeSessionId]: "error" }));
        toast.error("Failed to load session", { description: message });
      });

    return () => {
      mounted = false;
    };
  }, [activeSessionId, messages]);

  const activeSession = sessions.find((session) => session.name === activeSessionId) ?? null;
  const activeNavLabel = navItems.find((item) => item.id === activeNav)?.label ?? "Chat";
  const selectedInspectorFile = inspectorFiles.find((item) => item.path === selectedInspectorPath) ?? null;
  const selectedInspectorLabel = selectedInspectorFile?.label ?? selectedInspectorPath;
  const currentSessionStatus = activeSessionId ? (sessionStatus[activeSessionId] ?? "idle") : "idle";
  const sessionMessages = useMemo(() => {
    if (!activeSessionId) {
      return starterMessages;
    }

    return messages[activeSessionId] ?? [];
  }, [activeSessionId, messages]);
  const isDirty = initialInspectorLoad.current && loadedFilePath === selectedInspectorPath && editorValue !== "";

  const activeViewDescription = "The chat stream stays centered while memory, skills, and prompt files live in the inspector rail.";
  const visibleInspectorGroups = useMemo<InspectorGroup[]>(() => {
    if (activeNav === "memory") {
      return ["memory"];
    }

    if (activeNav === "skills") {
      return ["skills"];
    }

    return ["workspace", "memory", "skills"];
  }, [activeNav]);
  const groupedInspectorFiles = useMemo(
    () =>
      visibleInspectorGroups.map((group) => ({
        group,
        files: inspectorFiles.filter((file) => file.group === group),
      })),
    [visibleInspectorGroups],
  );
  const inspectorTitle = activeNav === "chat" ? "Workspace surfaces" : `${activeNavLabel} surfaces`;
  const inspectorDescription =
    activeNav === "memory"
      ? "Review long-term memory on the right without replacing the live conversation."
      : activeNav === "skills"
        ? "Inspect skill definitions on the right while keeping the chat stage visible."
        : "Inspect and edit the workspace prompt files, memory, and local skills from one rail.";
  const selectedInspectorGroup = selectedInspectorFile?.group ?? "workspace";
  const visibleTraceSummaries = useMemo(() => {
    if (!activeSessionId) {
      return traceSummaries;
    }
    const sessionMatches = traceSummaries.filter((trace) => trace.session_id === activeSessionId);
    return sessionMatches.length > 0 ? sessionMatches : traceSummaries;
  }, [activeSessionId, traceSummaries]);
  const activeTrace = activeTraceId ? traceDetails[activeTraceId] ?? null : null;

  useEffect(() => {
    if (visibleTraceSummaries.length === 0) {
      return;
    }
    setActiveTraceId((current) => {
      if (current && visibleTraceSummaries.some((trace) => trace.trace_id === current)) {
        return current;
      }
      return visibleTraceSummaries[0]?.trace_id ?? current;
    });
  }, [visibleTraceSummaries]);

  function focusChatWorkspace() {
    stageHeadingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => {
      composerRef.current?.focus();
    }, 200);
  }

  function handleSessionSelect(sessionId: string) {
    setActiveSessionId(sessionId);
    setActiveNav("chat");
    focusChatWorkspace();
  }

  function handleTraceSelect(traceId: string) {
    setActiveTraceId(traceId);
    setActiveNav("chat");
  }

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
      for await (const chatEvent of streamChat(trimmed, activeSessionId, modelSettings)) {
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
      void refreshTraces();
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

  function handleModelSettingChange(field: keyof ModelSettings, value: string) {
    setModelSettings((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleResetModelSettings() {
    setModelSettings(defaultModelSettings);
    toast.success("Restored default model settings");
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      <main className="min-h-screen bg-[linear-gradient(180deg,#f8fafc_0%,#eef2ff_100%)] px-4 py-4 text-foreground sm:px-5 sm:py-5">
        <div className="mx-auto w-full max-w-[1800px]">
          <section className="flex flex-col gap-4 md:grid md:min-h-[calc(100vh-2.5rem)] md:grid-cols-[260px_minmax(0,1fr)] lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)]">
            <aside className="flex min-h-0 flex-col rounded-[20px] border border-slate-800/80 bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(15,23,42,0.92))] p-4 shadow-[0_18px_50px_rgba(15,23,42,0.22)] sm:p-5 md:sticky md:top-4 md:h-[calc(100vh-2.5rem)] md:overflow-hidden lg:rounded-[22px]">
              <div className="flex min-h-0 flex-1 flex-col gap-4 lg:gap-5">
                <div className="border-b border-white/10 pb-4 lg:pb-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-sky-300/70">Workspace</p>
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <h1 className="text-[1.4rem] font-semibold leading-tight tracking-tight text-white sm:text-[1.65rem] lg:text-2xl">mini OpenClaw</h1>
                    <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-slate-300 lg:hidden">Local</span>
                  </div>
                  <p className="mt-2 max-w-sm text-sm leading-6 text-slate-300 sm:block">Local agent workspace for sessions, memory, and skills.</p>
                </div>

                <nav className="grid grid-cols-3 gap-2 lg:space-y-2 lg:grid-cols-1 lg:gap-0" aria-label="Primary">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === activeNav;

                    return (
                      <button
                        key={item.id}
                        className={[
                          "flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-3 text-center text-sm transition-all duration-150 lg:justify-start lg:gap-3 lg:px-4 lg:text-left",
                          active
                            ? "border-sky-400/30 bg-sky-400/12 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                            : "border-transparent bg-transparent text-slate-300 hover:border-white/10 hover:bg-white/5 hover:text-white",
                        ].join(" ")}
                        onClick={() => setActiveNav(item.id)}
                        type="button"
                      >
                        <Icon className={["h-4 w-4", active ? "text-sky-300" : "text-slate-500"].join(" ")} />
                        {item.label}
                      </button>
                    );
                  })}
                </nav>

                <div className="flex min-h-0 flex-1 flex-col rounded-[18px] border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Sessions</p>
                    <span className="rounded-full bg-white/10 px-2 py-1 text-[11px] font-medium text-slate-300">{sessions.length}</span>
                  </div>
                  <div className="mt-3 max-h-40 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 sm:max-h-52 lg:mt-4 lg:max-h-none">
                    {sessions.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-white/10 px-4 py-3 text-sm text-slate-400">
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
                              "w-full rounded-lg border px-4 py-3 text-left transition-all duration-150",
                              active
                                ? "border-sky-400/25 bg-sky-400/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                                : "border-transparent bg-transparent hover:border-white/10 hover:bg-white/5",
                            ].join(" ")}
                            onClick={() => handleSessionSelect(session.name)}
                            type="button"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="truncate text-sm font-medium text-white">{session.name}</span>
                              <span className="text-xs text-slate-400">{session.message_count} msgs</span>
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

            <div className="flex min-h-0 flex-col gap-4">
              <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(420px,36vw)] xl:grid-cols-[minmax(0,1fr)_minmax(460px,38vw)] 2xl:grid-cols-[minmax(0,1fr)_minmax(560px,42vw)]">
                <section className="flex min-h-[60vh] min-w-0 flex-col rounded-[20px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_34px_rgba(15,23,42,0.06)] sm:p-6 lg:h-[calc(100vh-2.5rem)] lg:overflow-hidden lg:rounded-[22px]">
                <div className="flex flex-col gap-3 border-b border-slate-200/80 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Chat</p>
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        mini OpenClaw
                      </span>
                    </div>
                    <h2 className="text-[1.35rem] font-semibold tracking-tight text-slate-950 sm:text-[1.5rem]" ref={stageHeadingRef}>
                      Chat workspace
                    </h2>
                  </div>
                  <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 sm:self-start">
                    {isStreaming ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : <WandSparkles className="h-4 w-4 text-slate-400" />}
                    <span className="truncate text-sm font-medium text-slate-700">Session {activeSession?.name ?? activeSessionId ?? "draft"}</span>
                  </div>
                </div>

                <div className="flex min-h-0 flex-1 flex-col justify-between gap-6 pt-6">
                  <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                    <div className="space-y-4">
                      <div className="rounded-[16px] border border-slate-200 bg-slate-50/80 px-4 py-3">
                        <p className="text-sm text-slate-600">
                          Current session: <span className="font-semibold text-slate-950">{activeSession?.name ?? activeSessionId ?? "draft session"}</span>
                        </p>
                        {activeNav !== "chat" ? (
                          <p className="mt-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
                            Inspector focus is on <span className="font-semibold text-slate-700">{activeNavLabel}</span>. The conversation stays live here.
                          </p>
                        ) : null}
                      </div>
                      {currentSessionStatus === "loading" ? (
                        <div className="rounded-[24px] border border-dashed border-slate-200 bg-white/80 p-6 text-sm text-slate-500">
                          Loading session history...
                        </div>
                      ) : null}
                      {currentSessionStatus !== "loading" && sessionMessages.length === 0 ? (
                        <div className="rounded-[24px] border border-dashed border-slate-200 bg-white/80 p-6 text-sm text-slate-500">
                          No messages in this session yet. Send the first prompt to get started.
                        </div>
                      ) : null}
                      {sessionMessages.map((message) => {
                        if (message.role === "user") {
                          return (
                            <article key={message.id} className="max-w-[90%] rounded-[18px] border border-slate-200 bg-slate-50/80 p-5 xl:max-w-[82%]">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">User</p>
                              <p className="mt-3 whitespace-pre-wrap text-[15px] leading-7 text-slate-700">{message.content}</p>
                            </article>
                          );
                        }

                        return (
                          <article key={message.id} className="ml-auto max-w-[94%] rounded-[18px] border border-sky-200 bg-[linear-gradient(135deg,#eff6ff,#ffffff)] p-5 xl:max-w-[88%]">
                            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-700">
                              <Bot className="h-4 w-4" />
                              Assistant
                            </div>
                            <p className="mt-3 whitespace-pre-wrap text-[15px] leading-7 text-slate-700">
                              {message.content || (isStreaming ? "Streaming response..." : "Waiting for assistant output.")}
                            </p>
                            <TraceBlock messageId={message.id} trace={message.trace} />
                          </article>
                        );
                      })}
                    </div>
                  </div>

                  <div className="rounded-[18px] border border-slate-200 bg-slate-50/90 p-4 lg:rounded-[20px]">
                    <form className="flex flex-col gap-3 2xl:flex-row" onSubmit={handleSubmit}>
                      <Input
                        aria-label="Chat composer"
                        className="h-14 min-w-0 rounded-xl border-slate-200 bg-white px-4 text-base shadow-sm"
                        ref={composerRef}
                        onChange={(event) => setDraft(event.target.value)}
                        placeholder="Ask the agent to inspect a skill, fetch a file, or explain the current session."
                        value={draft}
                      />
                      <Button className="h-14 rounded-xl px-6 text-base xl:min-w-36" disabled={isStreaming || !draft.trim()} type="submit">
                        {isStreaming ? "Streaming..." : "Send"}
                      </Button>
                    </form>
                    <p className="mt-2 text-sm text-slate-500">Continue this session here.</p>
                    {streamError ? <p className="mt-3 text-sm text-rose-600">{streamError}</p> : null}
                  </div>
                </div>
              </section>

              <section className="flex min-h-[60vh] min-w-0 flex-col rounded-[20px] border border-slate-200/80 bg-[#f6f8fc] p-4 shadow-[0_12px_34px_rgba(15,23,42,0.05)] sm:p-5 lg:h-[calc(100vh-2.5rem)] lg:overflow-hidden lg:rounded-[22px]">
                <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 pb-5">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Traces</p>
                    <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Runtime diagnostics</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-500">Inspect chat runs, tool calls, failures, and latency without leaving the workspace.</p>
                  </div>
                  <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-500">
                    <span className={['h-2 w-2 rounded-full', traceStatus === 'error' ? 'bg-rose-500' : traceStatus === 'loading' ? 'bg-amber-500' : 'bg-emerald-500'].join(' ')} />
                    {visibleTraceSummaries.length} traces
                  </div>
                </div>

                <div className="mt-5 grid min-h-0 flex-1 gap-4 2xl:grid-cols-[240px_minmax(0,1fr)]">
                  <div className="flex min-h-[220px] max-h-[320px] flex-col rounded-[18px] border border-slate-200 bg-white p-3 shadow-sm 2xl:max-h-none">
                    <div className="flex items-center justify-between gap-2 px-2 pb-3">
                      <div className="flex items-center gap-2">
                        <History className="h-4 w-4 text-slate-400" />
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Runs</p>
                      </div>
                      <PanelRightOpen className="h-4 w-4 text-slate-300" />
                    </div>
                    <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
                      {visibleTraceSummaries.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">No traces yet.</div>
                      ) : (
                        visibleTraceSummaries.map((trace) => {
                          const active = trace.trace_id === activeTraceId;
                          return (
                            <button
                              key={trace.trace_id}
                              className={[
                                'w-full rounded-xl border px-3 py-2.5 text-left transition',
                                active ? 'border-slate-900 bg-slate-950 text-white' : 'border-transparent bg-slate-50 text-slate-700 hover:border-slate-200 hover:bg-slate-100',
                              ].join(' ')}
                              onClick={() => handleTraceSelect(trace.trace_id)}
                              type="button"
                            >
                              <div className="flex items-center justify-between gap-3">
                                <span className="truncate text-sm font-medium">{trace.trace_id}</span>
                                <span className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{trace.final_status}</span>
                              </div>
                              <p className={['mt-1 text-xs', active ? 'text-white/65' : 'text-slate-500'].join(' ')}>{trace.session_id}</p>
                              <p className={['mt-1 text-xs', active ? 'text-white/50' : 'text-slate-400'].join(' ')}>{trace.latency_ms ?? 0} ms</p>
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <div className="flex min-h-[440px] min-w-0 flex-col rounded-[18px] border border-slate-200 bg-white shadow-sm 2xl:min-h-[520px]">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <FileCode2 className="h-4 w-4 text-primary" />
                          <p className="truncate text-sm font-semibold text-slate-900">{activeTrace?.trace_id ?? activeTraceId ?? 'Select a trace'}</p>
                          <span className={["rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em]", activeTrace?.final_status === "error" ? "border-rose-200 bg-rose-50 text-rose-700" : activeTrace?.final_status === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-500"].join(" ")}>
                            {activeTrace?.final_status ?? traceStatus}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-xs text-slate-500">{activeTrace?.session_id ?? 'No trace selected'}</p>
                      </div>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto p-4">
                      {activeTrace ? (
                        <div className="space-y-3">
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                            <p>Model: {activeTrace.model_name}</p>
                            <p className="mt-1">Latency: {activeTrace.latency_ms ?? 0} ms</p>
                            <p className="mt-1">Started: {formatTimestamp(activeTrace.start_time)}</p>
                            {activeTrace.error_category ? <p className="mt-1">Error category: {activeTrace.error_category}</p> : null}
                            {activeTrace.retry_count > 0 ? <p className="mt-1">Retries: {activeTrace.retry_count}</p> : null}
                            {activeTrace.friendly_message ? <p className="mt-2 text-rose-700">{activeTrace.friendly_message}</p> : null}
                          </div>
                          {activeTrace.events.map((event, index) => (
                            <div key={`${activeTrace.trace_id}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{event.kind}</p>
                              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-600">{JSON.stringify(event.payload, null, 2)}</pre>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-2xl border border-dashed border-slate-200 p-6 text-sm text-slate-500">Pick a trace to inspect its events.</div>
                      )}
                    </div>
                  </div>
                </div>
              </section>

              <section className="flex min-h-[60vh] min-w-0 flex-col rounded-[20px] border border-slate-200/80 bg-[#f6f8fc] p-4 shadow-[0_12px_34px_rgba(15,23,42,0.05)] sm:p-5 lg:h-[calc(100vh-2.5rem)] lg:overflow-hidden lg:rounded-[22px]">
                <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 pb-5">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Inspector</p>
                    <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{inspectorTitle}</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-500">{inspectorDescription}</p>
                  </div>
                  <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-500">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    Local agent workspace
                  </div>
                </div>

                <div className="mt-5 flex flex-wrap items-center gap-2">
                  {visibleInspectorGroups.map((group) => (
                    <span
                      key={group}
                      className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500"
                    >
                      {getInspectorGroupLabel(group)}
                    </span>
                  ))}
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    {inspectorFiles.length} files
                  </span>
                </div>

                <div className="mt-4 grid min-h-0 flex-1 gap-4 2xl:grid-cols-[240px_minmax(0,1fr)]">
                  <div className="flex min-h-[220px] max-h-[320px] flex-col rounded-[18px] border border-slate-200 bg-white p-3 shadow-sm 2xl:max-h-none">
                    <div className="flex items-center justify-between gap-2 px-2 pb-3">
                      <div className="flex items-center gap-2">
                      <FolderTree className="h-4 w-4 text-slate-400" />
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Files</p>
                      </div>
                      <PanelRightOpen className="h-4 w-4 text-slate-300" />
                    </div>
                    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
                      {groupedInspectorFiles.map(({ group, files }) => (
                        <div key={group} className="space-y-1.5">
                          <p className="px-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{getInspectorGroupLabel(group)}</p>
                          <div className="space-y-1">
                            {files.map((file) => {
                              const active = file.path === selectedInspectorPath;

                              return (
                                <button
                                  key={file.path}
                                  className={[
                                    "flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition",
                                    active
                                      ? "border-slate-900 bg-slate-950 text-white shadow-[0_10px_25px_rgba(15,23,42,0.18)]"
                                      : "border-transparent bg-slate-50/80 text-slate-700 hover:border-slate-200 hover:bg-slate-100",
                                  ].join(" ")}
                                  onClick={() => setSelectedInspectorPath(file.path)}
                                  type="button"
                                >
                                  <FileText className={["mt-0.5 h-4 w-4 shrink-0", active ? "text-white/80" : "text-slate-400"].join(" ")} />
                                  <div className="min-w-0 flex-1">
                                    <p className="truncate text-sm font-medium">{file.label}</p>
                                    <p className={["mt-1 truncate text-[11px]", active ? "text-white/60" : "text-slate-400"].join(" ")}>
                                      {file.path}
                                    </p>
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex min-h-[440px] min-w-0 flex-col rounded-[18px] border border-slate-200 bg-white shadow-sm 2xl:min-h-[520px]">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <FileCode2 className="h-4 w-4 text-primary" />
                          <p className="truncate text-sm font-semibold text-slate-900">{selectedInspectorLabel}</p>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                            {getInspectorGroupLabel(selectedInspectorGroup)}
                          </span>
                          {isDirty ? (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700">
                              Unsaved
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 truncate text-xs text-slate-500">{selectedInspectorPath}</p>
                      </div>
                      <Button className="h-10 rounded-xl px-4 sm:shrink-0" disabled={isInspectorLoading || isSaving} onClick={handleSaveInspector} type="button">
                        {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                        Save
                      </Button>
                    </div>

                    <div className="min-h-[340px] flex-1 overflow-hidden 2xl:min-h-[420px]">
                      {isInspectorLoading ? (
                        <div className="flex h-full items-center justify-center gap-3 text-sm text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin text-primary" />
                          Loading file...
                        </div>
                      ) : (
                        <MonacoEditor height="100%" onChange={setEditorValue} onSave={handleSaveInspector} value={editorValue} />
                      )}
                    </div>

                    <div className="border-t border-slate-200 px-4 py-3">
                      <p className="text-sm text-slate-600">
                        {isSaving ? "Saving changes..." : inspectorError ? `Save error: ${inspectorError}` : "Cmd/Ctrl+S saves the current file."}
                      </p>
                    </div>
                  </div>
                </div>

                <details className="mt-4 rounded-[18px] border border-slate-200 bg-white">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-slate-700 marker:content-none">
                    <span className="flex items-center gap-2">
                      <Settings2 className="h-4 w-4 text-slate-400" />
                      Model Settings
                    </span>
                    <ChevronDown className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="border-t border-slate-200 px-4 py-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <p className="text-xs leading-5 text-slate-500">Sent with each chat request. Leave `API Key` empty to use the backend default.</p>
                      <Button className="h-9 rounded-2xl px-3" onClick={handleResetModelSettings} type="button" variant="outline">
                        <RotateCcw className="mr-2 h-4 w-4" />
                        Reset
                      </Button>
                    </div>

                    <div className="mt-4 grid gap-3">
                      <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Base URL</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("baseUrl", event.target.value)}
                          placeholder="https://api.codexzh.com/v1"
                          value={modelSettings.baseUrl}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Model</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("model", event.target.value)}
                          placeholder="gpt-5.4"
                          value={modelSettings.model}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">API Key</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("apiKey", event.target.value)}
                          placeholder="Leave empty to use backend default"
                          type="password"
                          value={modelSettings.apiKey}
                        />
                      </div>
                    </div>
                  </div>
                </details>
              </section>
            </div>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}
