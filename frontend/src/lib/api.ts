const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

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
  events: Array<{ timestamp: string; kind: string; payload: Record<string, unknown> }>;
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
