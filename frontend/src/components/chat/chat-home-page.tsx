"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Bot, Compass, Lightbulb, Loader2, LockKeyhole, MessageSquareText, Plus, Scale, ShieldCheck, Share2, Sparkles } from "lucide-react";
import { Toaster, toast } from "sonner";

import { MemoryApprovalCard } from "@/components/chat/memory-approval-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loadModelSettings } from "@/lib/model-settings";
import {
  approveMemoryProposal,
  getSession,
  listMemoryProposals,
  listSessions,
  rejectMemoryProposal,
  streamChat,
  type AgentId,
  type AgentIdentity,
  type ChatEvent,
  type MemoryProposal,
  type SessionMessage,
  type SessionSummary,
} from "@/lib/api";

type TraceItem =
  | { kind: "thought"; agentId: AgentId; content: string }
  | { kind: "tool_call"; agentId: AgentId; name: string; input?: unknown }
  | { kind: "tool_result"; agentId: AgentId; name: string; content: string };

type ChatMessage =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      content: string;
      trace: TraceItem[];
      agent: AgentIdentity;
      routeReason?: "default_host" | "explicit_mention";
      matchedMention?: string | null;
      handoff?: { handoffId: string; fromAgentId: AgentId; fromDisplayName: string; reason: string; task?: string; evidenceCount?: number };
    };

const agentDirectory: Record<AgentId, AgentIdentity> = {
  lighthouse: { agent_id: "lighthouse", display_name: "灯塔", english_name: "Lighthouse", accent: "emerald" },
  spark: { agent_id: "spark", display_name: "火花", english_name: "Spark", accent: "amber" },
  whetstone: { agent_id: "whetstone", display_name: "砥石", english_name: "Whetstone", accent: "sky" },
};

const agentStyles: Record<AgentId, { article: string; badge: string; avatar: string; dot: string; icon: typeof Bot; role: string; boundary: string }> = {
  lighthouse: {
    article: "border-emerald-200 bg-[linear-gradient(135deg,#effaf2,#fffdf8)]",
    badge: "bg-emerald-100 text-emerald-900",
    avatar: "border-emerald-200 bg-emerald-100 text-emerald-800",
    dot: "bg-emerald-500",
    icon: Compass,
    role: "主持与上下文",
    boundary: "私有会话线索 · 共享任务摘要",
  },
  spark: {
    article: "border-amber-200 bg-[linear-gradient(135deg,#fff8e8,#fffdf8)]",
    badge: "bg-amber-100 text-amber-900",
    avatar: "border-amber-200 bg-amber-100 text-amber-800",
    dot: "bg-amber-500",
    icon: Lightbulb,
    role: "发散与方案",
    boundary: "私有探索笔记 · 共享可用证据",
  },
  whetstone: {
    article: "border-sky-200 bg-[linear-gradient(135deg,#f0f9ff,#fffdf8)]",
    badge: "bg-sky-100 text-sky-900",
    avatar: "border-sky-200 bg-sky-100 text-sky-800",
    dot: "bg-sky-500",
    icon: Scale,
    role: "审查与校验",
    boundary: "私有审查草稿 · 共享风险与依据",
  },
};

function createMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createSessionId(): string {
  const uniqueId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return `session-${uniqueId}`;
}

function toChatMessages(items: SessionMessage[]): ChatMessage[] {
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

      const agentId = item.author_agent_id && item.author_agent_id in agentDirectory ? item.author_agent_id : "lighthouse";
      const agent = {
        ...agentDirectory[agentId],
        display_name: item.author_agent_name || agentDirectory[agentId].display_name,
        accent: item.author_agent_accent || agentDirectory[agentId].accent,
      };
      const handoffFrom = item.handoff_from_agent_id ? agentDirectory[item.handoff_from_agent_id] : null;
      return {
        id: `session-assistant-${index}`,
        role: "assistant",
        content: item.content,
        trace: [],
        agent,
        routeReason: item.route_reason || undefined,
        handoff: handoffFrom
          ? {
              handoffId: item.handoff_id || "handoff_legacy",
              fromAgentId: handoffFrom.agent_id,
              fromDisplayName: handoffFrom.display_name,
              reason: item.handoff_reason || "历史记录未保存交接原因。",
              task: item.handoff_task || undefined,
              evidenceCount: typeof item.handoff_evidence_count === "number" ? item.handoff_evidence_count : undefined,
            }
          : undefined,
      } satisfies ChatMessage;
    });
}

function appendEvent(message: Extract<ChatMessage, { role: "assistant" }>, event: ChatEvent): Extract<ChatMessage, { role: "assistant" }> {
  if (event.type === "agent_route") {
    return {
      ...message,
      agent: {
        agent_id: event.agent_id,
        display_name: event.display_name,
        english_name: event.english_name,
        accent: event.accent,
      },
      routeReason: event.route_reason,
      matchedMention: event.matched_mention,
    };
  }

  if (event.type === "handoff") {
    return {
      ...message,
      agent: agentDirectory[event.to_agent_id],
      handoff: {
        handoffId: event.handoff_id,
        fromAgentId: event.from_agent_id,
        fromDisplayName: event.from_display_name,
        reason: event.reason,
        task: event.task,
        evidenceCount: event.evidence_count,
      },
    };
  }

  if (event.type === "final") {
    return { ...message, content: message.content + event.content };
  }

  if (event.type === "thought") {
    return {
      ...message,
      trace: [...message.trace, { kind: "thought", agentId: event.agent_id, content: event.content }],
    };
  }

  if (event.type === "tool_call") {
    return {
      ...message,
      trace: [...message.trace, { kind: "tool_call", agentId: event.agent_id, name: event.name, input: event.input }],
    };
  }

  return {
    ...message,
    trace: [...message.trace, { kind: "tool_result", agentId: event.agent_id, name: event.name, content: event.content }],
  };
}

function traceSummary(item: TraceItem): string {
  if (item.kind === "thought") {
    return item.content;
  }
  if (item.kind === "tool_call") {
    return `Called ${item.name}`;
  }
  return `${item.name}: ${item.content}`;
}

const starterMessages: ChatMessage[] = [
  {
    id: "starter-assistant",
    role: "assistant",
    content:
      "我是灯塔，默认陪你维护上下文和推进任务。需要发散时可以 @火花，需要严格校验时可以 @砥石；我也会在确有必要时显式转交一次。",
    trace: [],
    agent: agentDirectory.lighthouse,
    routeReason: "default_host",
  },
];

const quickPrompts = [
  "Summarize Mini-OpenClaw as an AI agent project in 4 bullets.",
  "@火花 找出这个项目还能体现哪些 AI Agent 能力。",
  "@砥石 严格评审我的 90 秒项目介绍。",
] as const;

export function ChatHomePage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages);
  const [draft, setDraft] = useState("Summarize Mini-OpenClaw as an AI agent project in 4 bullets.");
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [pendingProposals, setPendingProposals] = useState<MemoryProposal[]>([]);
  const [isApprovalOpen, setIsApprovalOpen] = useState(false);
  const [isReviewingProposal, setIsReviewingProposal] = useState(false);
  const composerRef = useRef<HTMLInputElement | null>(null);
  const freshSessionIds = useRef(new Set<string>());

  const sessionLabel = useMemo(() => activeSessionId || "new session", [activeSessionId]);
  const activeProposal = pendingProposals[0] ?? null;
  const activeAgent = useMemo(
    () => [...messages].reverse().find((message): message is Extract<ChatMessage, { role: "assistant" }> => message.role === "assistant")?.agent ?? agentDirectory.lighthouse,
    [messages],
  );

  useEffect(() => {
    let mounted = true;

    void listSessions()
      .then((items) => {
        if (!mounted) {
          return;
        }

        setSessions(items);
        setActiveSessionId(items[0]?.name || createSessionId());
      })
      .catch(() => {
        if (!mounted) {
          return;
        }

        setSessions([]);
        setActiveSessionId(createSessionId());
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    void refreshPendingProposals(true);
  }, []);

  useEffect(() => {
    if (!activeSessionId) {
      return;
    }

    if (freshSessionIds.current.delete(activeSessionId)) {
      setMessages([]);
      setIsLoadingSession(false);
      return;
    }

    let mounted = true;
    setIsLoadingSession(true);

    void getSession(activeSessionId)
      .then((items) => {
        if (!mounted) {
          return;
        }

        setMessages(items.length > 0 ? toChatMessages(items) : starterMessages);
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load session";
        setMessages(starterMessages);
        toast.error("Failed to load session", { description: message });
      })
      .finally(() => {
        if (mounted) {
          setIsLoadingSession(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [activeSessionId]);

  function handlePromptSelect(prompt: string) {
    setDraft(prompt);
    composerRef.current?.focus();
  }

  function handleCreateSession() {
    if (isStreaming) {
      return;
    }

    const nextSessionId = createSessionId();
    freshSessionIds.current.add(nextSessionId);
    setActiveSessionId(nextSessionId);
    setMessages([]);
    setDraft("");
    setStreamError(null);
    setIsLoadingSession(false);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }

  function handleAgentMention(agent: AgentIdentity) {
    setDraft((current) => {
      const mention = `@${agent.display_name}`;
      return current.includes(mention) ? current : `${current.trimEnd()}${current.trim() ? " " : ""}${mention} `;
    });
    composerRef.current?.focus();
  }

  async function refreshPendingProposals(openWhenAvailable = false) {
    try {
      const proposals = await listMemoryProposals("pending");
      setPendingProposals(proposals);
      if (openWhenAvailable && proposals.length > 0) {
        setIsApprovalOpen(true);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load memory proposals";
      toast.error("Memory review is unavailable", { description: message });
    }
  }

  async function handleProposalDecision(decision: "approve" | "reject") {
    if (!activeProposal || isReviewingProposal) {
      return;
    }

    setIsReviewingProposal(true);
    try {
      if (decision === "approve") {
        await approveMemoryProposal(activeProposal.proposal_id);
      } else {
        await rejectMemoryProposal(activeProposal.proposal_id);
      }

      const remaining = await listMemoryProposals("pending");
      setPendingProposals(remaining);
      setIsApprovalOpen(remaining.length > 0);
      toast.success(decision === "approve" ? "Memory approved" : "Memory rejected", {
        description: decision === "approve" ? "It will be loaded in a future chat." : "It will not enter long-term memory.",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save memory decision";
      toast.error("Memory review failed", { description: message });
      void refreshPendingProposals(true);
    } finally {
      setIsReviewingProposal(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = draft.trim();
    if (!trimmed || !activeSessionId || isStreaming) {
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
      agent: agentDirectory.lighthouse,
    };

    setDraft("");
    setStreamError(null);
    setIsStreaming(true);
    setMessages((current) => [...current, userMessage, assistantSeed]);

    try {
      for await (const chatEvent of streamChat(trimmed, activeSessionId, loadModelSettings())) {
        setMessages((current) => {
          const nextMessages = [...current];
          const index = nextMessages.findIndex((message) => message.id === assistantId && message.role === "assistant");
          if (index === -1) {
            return current;
          }

          nextMessages[index] = appendEvent(nextMessages[index] as Extract<ChatMessage, { role: "assistant" }>, chatEvent);
          return nextMessages;
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Streaming failed";
      setStreamError(message);
      setMessages((current) =>
        current.map((item) => {
          if (item.id !== assistantId || item.role !== "assistant") {
            return item;
          }
          return {
            ...item,
            content: item.content || "The assistant could not complete this request.",
          };
        }),
      );
    } finally {
      setIsStreaming(false);
      void refreshPendingProposals(true);
      void listSessions().then(setSessions).catch(() => undefined);
    }
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      <main className="min-h-screen px-4 py-4 text-stone-900 sm:px-5 sm:py-6">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col gap-5">
          <header className="overflow-hidden rounded-[30px] border border-[#ead9c5] bg-[#fffaf4]/90 shadow-[0_24px_70px_rgba(90,59,46,0.12)] backdrop-blur">
            <div className="flex flex-col gap-5 p-5 md:flex-row md:items-center md:justify-between md:p-6">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[#e7c4ad] bg-[#fff1e6] px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-[#a34f32]">
                <Sparkles className="h-3.5 w-3.5" />
                  Memory Harbor
                </div>
                <h1 className="mt-3 max-w-2xl text-3xl font-semibold tracking-[-0.045em] text-[#34231d] md:text-4xl">三位 Agent，共同守护一段可追溯的对话。</h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-600 md:text-base">对话留在这里；记忆审批、运行 trace 与图检索证据进入独立工作视图，不打断思路。</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 md:justify-end">
                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800"><span className="h-2 w-2 rounded-full bg-emerald-500" />已配置 3 位 Agent</span>
                <Link href="/workbench">
                  <Button className="h-11 rounded-2xl bg-[#5a3b2e] px-5 text-white hover:bg-[#432a20]">
                    打开工作台
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </div>
            <div className="grid border-t border-[#ead9c5] bg-[#f8eee1]/70 sm:grid-cols-3">
              {(Object.keys(agentDirectory) as AgentId[]).map((agentId) => {
                const agent = agentDirectory[agentId];
                const presentation = agentStyles[agentId];
                const AgentIcon = presentation.icon;
                const isActive = activeAgent.agent_id === agentId;
                return (
                  <button className="group flex min-w-0 items-start gap-3 border-b border-[#ead9c5] px-4 py-4 text-left transition hover:bg-white/55 sm:border-b-0 sm:border-r sm:last:border-r-0" key={agentId} onClick={() => handleAgentMention(agent)} type="button">
                    <span className={`relative mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border ${presentation.avatar}`}><AgentIcon className="h-5 w-5" /><span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-[#f8eee1] ${isActive && isStreaming ? "animate-pulse" : ""} ${presentation.dot}`} /></span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2"><span className="font-semibold text-[#34231d]">{agent.display_name}</span><span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-400">{agent.english_name}</span>{isActive ? <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${presentation.badge}`}>{isStreaming ? "thinking" : "host"}</span> : null}</span>
                      <span className="mt-1 block text-xs font-medium text-stone-700">{presentation.role}</span>
                      <span className="mt-1 flex items-center gap-1 text-[11px] leading-4 text-stone-500"><LockKeyhole className="h-3 w-3 shrink-0 text-[#b16848]" />{presentation.boundary}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </header>

          <section className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[250px_minmax(0,1fr)]">
            <aside className="rounded-[26px] border border-[#ead9c5] bg-[#fffaf4]/80 p-4 shadow-[0_12px_30px_rgba(90,59,46,0.08)] backdrop-blur">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#34231d]">
                <MessageSquareText className="h-4 w-4 text-[#c96f4a]" />
                Sessions
              </div>
              <p className="mt-2 text-xs leading-5 text-stone-500">选择一段对话，继续这座 Memory Harbor 的上下文。</p>
              <Button className="mt-4 h-10 w-full rounded-xl border-[#dcae91] bg-[#fff1e6] text-[#79371f] hover:bg-[#fee3d0]" disabled={isStreaming} onClick={handleCreateSession} type="button" variant="outline">
                <Plus className="mr-2 h-4 w-4" />
                新建 Session
              </Button>
              <div className="mt-4 max-h-[28rem] space-y-2 overflow-y-auto pr-1">
                {sessions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-[#dfcbb5] bg-white/70 p-3 text-sm text-stone-500">还没有保存的会话。</div>
                ) : (
                  sessions.map((session) => {
                    const active = session.name === activeSessionId;
                    return (
                      <button
                        key={session.name}
                        className={[
                          "w-full rounded-2xl border px-3 py-3 text-left transition",
                          active ? "border-[#5a3b2e] bg-[#5a3b2e] text-white" : "border-[#ead9c5] bg-white/75 text-stone-700 hover:border-[#dcae91] hover:bg-[#fff1e6]",
                        ].join(" ")}
                        onClick={() => setActiveSessionId(session.name)}
                        type="button"
                      >
                        <p className="truncate text-sm font-medium">{session.name}</p>
                        <p className={["mt-1 text-xs", active ? "text-white/60" : "text-slate-400"].join(" ")}>
                          {session.message_count} messages
                        </p>
                        {session.preview ? <p className={["mt-1 line-clamp-2 text-xs leading-5", active ? "text-white/75" : "text-stone-500"].join(" ")}>{session.preview}</p> : null}
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            <section className="flex min-h-[640px] flex-col overflow-hidden rounded-[30px] border border-[#ead9c5] bg-[#fffdf9]/85 shadow-[0_24px_70px_rgba(90,59,46,0.11)] backdrop-blur">
              <div className="flex flex-col gap-3 border-b border-[#ead9c5] px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#34231d]">
                    <span className={`inline-flex h-7 w-7 items-center justify-center rounded-xl ${agentStyles[activeAgent.agent_id].avatar}`}><Bot className="h-4 w-4" /></span>
                    当前对话 · {activeAgent.display_name}
                  </div>
                  <p className="mt-1 break-all text-xs text-stone-500">{sessionLabel} · {isStreaming ? "正在组织回应" : "等待下一条消息"}</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {pendingProposals.length > 0 ? (
                    <button className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 transition hover:border-amber-300 hover:bg-amber-100" onClick={() => setIsApprovalOpen(true)} type="button">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      {pendingProposals.length} memory review{pendingProposals.length === 1 ? "" : "s"}
                    </button>
                  ) : null}
                  <Link className="text-sm font-medium text-[#a34f32] hover:text-[#79371f]" href="/workbench">
                    Trace 与图检索
                  </Link>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                {isLoadingSession ? (
                  <div className="flex h-full items-center justify-center text-sm text-slate-500">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Loading chat...
                  </div>
                ) : (
                  <div className="space-y-4">
                    {messages.length === 0 ? (
                      <div className="rounded-[22px] border border-dashed border-[#dfcbb5] bg-[#fffaf4]/80 px-5 py-6 text-sm leading-6 text-stone-600">
                        <p className="font-semibold text-[#5a3b2e]">新的 Session 已就绪</p>
                        <p className="mt-2">首条消息会带着新的 session_id 发往后端，并在该会话的 Agent bootstrap 中加载已批准记忆。</p>
                      </div>
                    ) : messages.map((message) => {
                      if (message.role === "user") {
                        return (
                          <article key={message.id} className="ml-auto max-w-[86%] rounded-[22px] border border-[#e7c4ad] bg-[#fff1e6] px-5 py-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#b16848]">You</p>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-stone-700">{message.content}</p>
                          </article>
                        );
                      }

                      const presentation = agentStyles[message.agent.agent_id];
                      const AgentIcon = presentation.icon;
                      return (
                        <article key={message.id} className={`max-w-[92%] rounded-[22px] border px-5 py-4 ${presentation.article}`}>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`inline-flex h-7 w-7 items-center justify-center rounded-xl border ${presentation.avatar}`}><AgentIcon className="h-3.5 w-3.5" /></span>
                            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${presentation.badge}`}>
                              <AgentIcon className="h-3.5 w-3.5" />
                              {message.agent.display_name}
                            </span>
                            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-stone-400">{presentation.role}</span>
                          </div>
                          {message.handoff ? (
                            <div className="mt-3 rounded-2xl border border-[#e6c9b2] bg-white/80 px-3 py-3 text-xs leading-5 text-stone-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                              <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-[#5a3b2e]">交接链路</span><span className="rounded-full bg-[#f8eee1] px-2 py-0.5 font-semibold text-[#5a3b2e]">{message.handoff.fromDisplayName} → {message.agent.display_name}</span><span className="font-mono text-[10px] text-stone-400">#{message.handoff.handoffId.slice(-8)}</span></div>
                              <p className="mt-2 text-stone-700">{message.handoff.reason}</p>
                              {message.handoff.task ? <p className="mt-1 text-stone-500">任务：{message.handoff.task}</p> : null}
                              {typeof message.handoff.evidenceCount === "number" ? <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-stone-500"><Share2 className="h-3.5 w-3.5 text-[#c96f4a]" />共享 {message.handoff.evidenceCount} 条证据；两侧私有记忆不会随交接暴露。</p> : null}
                            </div>
                          ) : null}
                          {!message.handoff && message.routeReason === "explicit_mention" ? (
                            <div className="mt-3 rounded-2xl border border-[#e6c9b2] bg-white/70 px-3 py-3 text-xs leading-5 text-stone-600">
                              <p className="font-semibold text-[#5a3b2e]">路由与上下文</p>
                              <p className="mt-1">路由方式：explicit_mention</p>
                              <p>当前 Agent：{message.agent.display_name}</p>
                              <p>共享证据：无</p>
                              <p className="mt-1">原因：本次为直接路由，未发生 handoff，也未发生证据共享。</p>
                            </div>
                          ) : null}
                          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-stone-700">
                            {message.content || (isStreaming ? "Thinking..." : "Waiting for response...")}
                          </p>
                          {message.trace.length > 0 ? (
                            <details className="mt-3 border-t border-white/80 pt-3 text-xs text-stone-500">
                              <summary className="cursor-pointer font-semibold text-stone-500 hover:text-[#a34f32]">查看本次运行事件 · {message.trace.length}</summary>
                              <div className="mt-2 space-y-1.5">
                              {message.trace.map((item, index) => (
                                <p key={`${message.id}-trace-${index}`} className="flex gap-2 leading-5">
                                  <span className={`shrink-0 font-semibold ${agentStyles[item.agentId].badge}`}>{agentDirectory[item.agentId].display_name}</span>
                                  <span className="break-words">{traceSummary(item)}</span>
                                </p>
                              ))}
                              </div>
                            </details>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="border-t border-[#ead9c5] bg-[#fffaf4]/90 px-5 py-4">
                <div className="mb-3 flex flex-wrap gap-2">
                  {quickPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      className="rounded-full border border-[#ead9c5] bg-white px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-[#dcae91] hover:bg-[#fff1e6] hover:text-[#79371f]"
                      onClick={() => handlePromptSelect(prompt)}
                      type="button"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
                <form className="flex flex-col gap-3 md:flex-row" onSubmit={handleSubmit}>
                  <Input
                    aria-label="Chat message"
                    className="h-13 min-h-13 rounded-2xl border-[#e3cdb8] bg-white px-4 text-base"
                    disabled={isStreaming || isLoadingSession}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="问灯塔，或使用 @火花 / @砥石 定向提问..."
                    ref={composerRef}
                    value={draft}
                  />
                  <Button className="h-13 rounded-2xl bg-[#c96f4a] px-6 text-white hover:bg-[#ad5938]" disabled={isStreaming || isLoadingSession || !draft.trim()} type="submit">
                    {isStreaming ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Sending
                      </>
                    ) : (
                      "Send"
                    )}
                  </Button>
                </form>
                {streamError ? <p className="mt-3 text-sm text-rose-600">{streamError}</p> : null}
              </div>
            </section>
          </section>
        </div>
      </main>
      <MemoryApprovalCard
        isOpen={isApprovalOpen}
        isSubmitting={isReviewingProposal}
        onApprove={() => void handleProposalDecision("approve")}
        onClose={() => setIsApprovalOpen(false)}
        onReject={() => void handleProposalDecision("reject")}
        pendingCount={pendingProposals.length}
        proposal={activeProposal}
      />
    </>
  );
}
