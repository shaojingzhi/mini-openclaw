const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8002";

export type ModelSettings = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export type ChatEventType = "thought" | "tool_call" | "tool_result" | "final";

export type ThoughtEvent = {
  type: "thought";
  content: string;
};

export type ToolCallEvent = {
  type: "tool_call";
  name: string;
  input?: unknown;
};

export type ToolResultEvent = {
  type: "tool_result";
  name: string;
  content: string;
};

export type FinalEvent = {
  type: "final";
  content: string;
};

export type ChatEvent = ThoughtEvent | ToolCallEvent | ToolResultEvent | FinalEvent;

export type SessionSummary = {
  name: string;
  last_modified: string;
  message_count: number;
};

export type SessionMessage = {
  role: string;
  content: string;
};

export type MemoryProposalStatus = "pending" | "approved" | "rejected";

export type MemoryProposal = {
  proposal_id: string;
  status: MemoryProposalStatus;
  session_id: string | null;
  target: "user_capsule" | "project_memory" | "agent_behavior" | "relationship_memory";
  memory_type: "user_preference" | "project_convention" | "task_state" | "behavior_preference";
  content: string;
  rationale: string;
  confidence: "low" | "medium" | "high";
  signal_kind: "user_instructed" | "explicit_preference" | "repeated_feedback" | "project_decision";
  scope: "global" | "project" | "task" | "interview_prep";
  source_message_id: string | null;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
};

export type TraceSummary = {
  trace_id: string;
  session_id: string;
  latency_ms: number | null;
  final_status: string;
  error_category: string | null;
  created_at: string | null;
};

export type TraceDetail = {
  trace_id: string;
  session_id: string;
  user_id: string | null;
  start_time: string;
  end_time: string | null;
  latency_ms: number | null;
  model_name: string;
  tool_calls: unknown[];
  tool_failures: unknown[];
  final_status: string;
  token_usage: unknown;
  error_category: string | null;
  error_message: string | null;
  friendly_message: string | null;
  recoverable: boolean | null;
  retry_count: number;
  graph_retrieval?: GraphRetrievalMetadata | null;
  events: Array<{ timestamp: string; kind: string; payload: Record<string, unknown> }>;
};

export type GraphRetrievalMetadata = {
  direct_node_ids: string[];
  expanded_node_ids: string[];
  edge_types: string[];
  evidence_count: number;
};

export type GraphSummary = {
  schema_version: number | null;
  node_count: number;
  edge_count: number;
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  sources: Record<string, string>;
};

export type GraphNodeDetail = {
  node: Record<string, unknown>;
  edges: Array<Record<string, unknown>>;
};

export type EvalJobStatus = "queued" | "running" | "completed" | "failed";

export type EvalJobResult = {
  output: string;
  markdown_output: string;
  dataset_size: number;
  profiles: string[];
  langsmith_sync: unknown;
};

export type EvalJobResponse = {
  job_id: string;
  status: EvalJobStatus;
  created_at: string;
  updated_at: string;
  request: {
    dataset_path: string;
    profiles_path: string;
    profile_ids: string[] | null;
    sync_langsmith: boolean;
  };
  result: EvalJobResult | null;
  error: string | null;
};

export type FilePayload = {
  path: string;
  content: string;
};

type ChatEventPayload = {
  content?: unknown;
  error_category?: unknown;
  input?: unknown;
  name?: unknown;
};

type ApiErrorBody = {
  detail?: unknown;
  error_category?: unknown;
  error_message?: unknown;
  friendly_message?: unknown;
  recoverable?: unknown;
  trace_id?: unknown;
};

function buildApiUrl(path: string): string {
  return new URL(path, API_BASE_URL).toString();
}

async function assertResponseOk(response: Response, action: string): Promise<Response> {
  if (!response.ok) {
    let message = `${action} failed with status ${response.status}`;

    try {
      const payload = (await response.clone().json()) as ApiErrorBody;
      if (typeof payload.friendly_message === "string" && payload.friendly_message.trim()) {
        message = payload.friendly_message;
      } else if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail;
      }
    } catch {
      try {
        const text = await response.clone().text();
        if (text.trim()) {
          message = text.trim();
        }
      } catch {
        message = `${action} failed with status ${response.status}`;
      }
    }

    throw new Error(message);
  }

  return response;
}

function toChatEvent(type: string, payload: ChatEventPayload): ChatEvent | null {
  if (type === "thought") {
    return {
      type,
      content: typeof payload.content === "string" ? payload.content : "",
    };
  }

  if (type === "tool_call") {
    return {
      type,
      name: typeof payload.name === "string" ? payload.name : "tool",
      input: payload.input,
    };
  }

  if (type === "tool_result") {
    return {
      type,
      name: typeof payload.name === "string" ? payload.name : "tool",
      content: typeof payload.content === "string" ? payload.content : "",
    };
  }

  if (type === "final") {
    return {
      type,
      content: typeof payload.content === "string" ? payload.content : "",
    };
  }

  return null;
}

function parseSseBlock(block: string): ChatEvent | null {
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const payload = JSON.parse(dataLines.join("\n")) as ChatEventPayload;
  return toChatEvent(eventType, payload);
}

export async function* streamChat(
  message: string,
  sessionId: string,
  settings?: Partial<ModelSettings>,
): AsyncGenerator<ChatEvent, void, undefined> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/chat"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        stream: true,
        api_key: settings?.apiKey?.trim() || undefined,
        base_url: settings?.baseUrl?.trim() || undefined,
        model: settings?.model?.trim() || undefined,
      }),
    }),
    "streamChat",
  );

  if (!response.body) {
    throw new Error("streamChat response body is missing");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) {
        yield event;
      }
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const event = parseSseBlock(buffer);
    if (event) {
      yield event;
    }
  }
}

export async function getFile(path: string): Promise<FilePayload> {
  const response = await assertResponseOk(
    await fetch(`${buildApiUrl("/api/files")}?path=${encodeURIComponent(path)}`, {
      cache: "no-store",
    }),
    "getFile",
  );

  return (await response.json()) as FilePayload;
}

export async function saveFile(path: string, content: string): Promise<FilePayload> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/files"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ path, content }),
    }),
    "saveFile",
  );

  return (await response.json()) as FilePayload;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/sessions"), {
      cache: "no-store",
    }),
    "listSessions",
  );

  const body = (await response.json()) as { sessions: SessionSummary[] };
  return body.sessions;
}

export async function getSession(sessionId: string): Promise<SessionMessage[]> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}`), {
      cache: "no-store",
    }),
    "getSession",
  );

  const body = (await response.json()) as { session_id: string; messages: SessionMessage[] };
  return body.messages;
}

export async function listMemoryProposals(
  status?: MemoryProposalStatus,
): Promise<MemoryProposal[]> {
  const url = new URL(buildApiUrl("/api/memory/proposals"));
  if (status) {
    url.searchParams.set("status", status);
  }
  const response = await assertResponseOk(
    await fetch(url, { cache: "no-store" }),
    "listMemoryProposals",
  );

  const body = (await response.json()) as { proposals: MemoryProposal[] };
  return body.proposals;
}

async function decideMemoryProposal(
  proposalId: string,
  decision: "approve" | "reject",
  reason?: string,
): Promise<MemoryProposal> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl(`/api/memory/proposals/${encodeURIComponent(proposalId)}/${decision}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason?.trim() || undefined }),
    }),
    `${decision}MemoryProposal`,
  );

  const body = (await response.json()) as { proposal: MemoryProposal };
  return body.proposal;
}

export function approveMemoryProposal(proposalId: string, reason?: string): Promise<MemoryProposal> {
  return decideMemoryProposal(proposalId, "approve", reason);
}

export function rejectMemoryProposal(proposalId: string, reason?: string): Promise<MemoryProposal> {
  return decideMemoryProposal(proposalId, "reject", reason);
}

export async function listTraces(): Promise<TraceSummary[]> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/traces"), {
      cache: "no-store",
    }),
    "listTraces",
  );

  const body = (await response.json()) as { traces: TraceSummary[] };
  return body.traces;
}

export async function getTrace(traceId: string): Promise<TraceDetail> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl(`/api/traces/${encodeURIComponent(traceId)}`), {
      cache: "no-store",
    }),
    "getTrace",
  );

  return (await response.json()) as TraceDetail;
}

export async function getGraphSummary(): Promise<{ available: boolean; summary: GraphSummary }> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/graph"), {
      cache: "no-store",
    }),
    "getGraphSummary",
  );

  return (await response.json()) as { available: boolean; summary: GraphSummary };
}

export async function getGraphNode(nodeId: string): Promise<GraphNodeDetail> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl(`/api/graph/nodes/${encodeURIComponent(nodeId)}`), {
      cache: "no-store",
    }),
    "getGraphNode",
  );

  return (await response.json()) as GraphNodeDetail;
}

export async function runGraphDemo(
  message: string,
  sessionId: string,
): Promise<{ reply: string; trace_id: string }> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/graph/demo"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
    }),
    "runGraphDemo",
  );

  return (await response.json()) as { reply: string; trace_id: string };
}

export async function runEval(options?: {
  sync_langsmith?: boolean;
  dataset_path?: string;
  profiles_path?: string;
  profile_ids?: string[];
}): Promise<EvalJobResponse> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl("/api/evals/run"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sync_langsmith: options?.sync_langsmith ?? false,
        dataset_path: options?.dataset_path,
        profiles_path: options?.profiles_path,
        profile_ids: options?.profile_ids,
      }),
    }),
    "runEval",
  );

  return (await response.json()) as EvalJobResponse;
}

export async function getEvalJob(jobId: string): Promise<EvalJobResponse> {
  const response = await assertResponseOk(
    await fetch(buildApiUrl(`/api/evals/jobs/${encodeURIComponent(jobId)}`), {
      cache: "no-store",
    }),
    "getEvalJob",
  );

  return (await response.json()) as EvalJobResponse;
}
