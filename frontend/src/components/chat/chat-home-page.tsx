"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Bot, Loader2, MessageSquareText, ShieldCheck, Sparkles } from "lucide-react";
import { Toaster, toast } from "sonner";

import { MemoryApprovalCard } from "@/components/chat/memory-approval-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  approveMemoryProposal,
  getSession,
  listMemoryProposals,
  listSessions,
  rejectMemoryProposal,
  streamChat,
  type ChatEvent,
  type MemoryProposal,
  type SessionSummary,
} from "@/lib/api";

type TraceItem =
  | { kind: "thought"; content: string }
  | { kind: "tool_call"; name: string; input?: unknown }
  | { kind: "tool_result"; name: string; content: string };

type ChatMessage =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; trace: TraceItem[] };

function createMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createSessionId(): string {
  return `session-${Date.now()}`;
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

const starterMessages: ChatMessage[] = [
  {
    id: "starter-assistant",
    role: "assistant",
    content:
      "Hi, I am Mini-OpenClaw. Ask me to inspect the project, explain the agent design, or help shape an interview-ready answer. For traces, files, settings, and Graph RAG diagnostics, open the Workbench.",
    trace: [],
  },
];

const quickPrompts = [
  "Summarize Mini-OpenClaw as an AI agent project in 4 bullets.",
  "Explain the difference between the chat home and the workbench.",
  "Give me a 90-second interview pitch for this project.",
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

  const sessionLabel = useMemo(() => activeSessionId || "new session", [activeSessionId]);
  const activeProposal = pendingProposals[0] ?? null;

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
    };

    setDraft("");
    setStreamError(null);
    setIsStreaming(true);
    setMessages((current) => [...current, userMessage, assistantSeed]);

    try {
      for await (const chatEvent of streamChat(trimmed, activeSessionId)) {
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
    }
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dff7ef_0,#f8fafc_34%,#f6efe3_100%)] px-5 py-6 text-slate-950">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col gap-5">
          <header className="flex flex-col gap-4 rounded-[28px] border border-white/70 bg-white/75 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur md:flex-row md:items-center md:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
                <Sparkles className="h-3.5 w-3.5" />
                Chat Home
              </div>
              <h1 className="mt-4 max-w-2xl text-3xl font-semibold tracking-[-0.04em] text-slate-950 md:text-5xl">
                Ask Mini-OpenClaw without the control-panel clutter.
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 md:text-base">
                Use this page for the main conversation flow. Open the Workbench only when you need files, traces, settings, or demo diagnostics.
              </p>
            </div>
            <Link href="/workbench">
              <Button className="h-12 rounded-2xl bg-slate-950 px-5 text-white hover:bg-slate-800">
                Open Workbench
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </header>

          <section className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
            <aside className="rounded-[26px] border border-white/70 bg-white/70 p-4 shadow-sm backdrop-blur">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <MessageSquareText className="h-4 w-4 text-emerald-600" />
                Sessions
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">Pick a recent chat, or continue the generated local session.</p>
              <div className="mt-4 space-y-2">
                {sessions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-3 text-sm text-slate-500">No saved sessions yet.</div>
                ) : (
                  sessions.slice(0, 8).map((session) => {
                    const active = session.name === activeSessionId;
                    return (
                      <button
                        key={session.name}
                        className={[
                          "w-full rounded-2xl border px-3 py-3 text-left transition",
                          active ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white/75 text-slate-700 hover:border-emerald-200 hover:bg-emerald-50",
                        ].join(" ")}
                        onClick={() => setActiveSessionId(session.name)}
                        type="button"
                      >
                        <p className="truncate text-sm font-medium">{session.name}</p>
                        <p className={["mt-1 text-xs", active ? "text-white/60" : "text-slate-400"].join(" ")}>
                          {session.message_count} messages
                        </p>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            <section className="flex min-h-[640px] flex-col overflow-hidden rounded-[30px] border border-white/70 bg-white/80 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur">
              <div className="flex flex-col gap-3 border-b border-slate-200/80 px-5 py-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                    <Bot className="h-4 w-4 text-emerald-600" />
                    Current chat
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{sessionLabel}</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {pendingProposals.length > 0 ? (
                    <button className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 transition hover:border-amber-300 hover:bg-amber-100" onClick={() => setIsApprovalOpen(true)} type="button">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      {pendingProposals.length} memory review{pendingProposals.length === 1 ? "" : "s"}
                    </button>
                  ) : null}
                  <Link className="text-sm font-medium text-emerald-700 hover:text-emerald-900" href="/workbench">
                    Need internals? Open Workbench
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
                    {messages.map((message) => {
                      if (message.role === "user") {
                        return (
                          <article key={message.id} className="max-w-[86%] rounded-[22px] border border-slate-200 bg-slate-50 px-5 py-4">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">You</p>
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700">{message.content}</p>
                          </article>
                        );
                      }

                      return (
                        <article key={message.id} className="ml-auto max-w-[88%] rounded-[22px] border border-emerald-200 bg-[linear-gradient(135deg,#ecfdf5,#ffffff)] px-5 py-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">Mini-OpenClaw</p>
                          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                            {message.content || (isStreaming ? "Thinking..." : "Waiting for response...")}
                          </p>
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="border-t border-slate-200/80 bg-white/90 px-5 py-4">
                <div className="mb-3 flex flex-wrap gap-2">
                  {quickPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-800"
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
                    className="h-13 min-h-13 rounded-2xl border-slate-200 bg-slate-50 px-4 text-base"
                    disabled={isStreaming || isLoadingSession}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Ask Mini-OpenClaw..."
                    ref={composerRef}
                    value={draft}
                  />
                  <Button className="h-13 rounded-2xl bg-emerald-600 px-6 text-white hover:bg-emerald-700" disabled={isStreaming || isLoadingSession || !draft.trim()} type="submit">
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
