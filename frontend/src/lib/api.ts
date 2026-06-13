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

export type FilePayload = {
  path: string;
  content: string;
};

type ChatEventPayload = {
  content?: unknown;
  input?: unknown;
  name?: unknown;
};

function buildApiUrl(path: string): string {
  return new URL(path, API_BASE_URL).toString();
}

function assertResponseOk(response: Response, action: string): Response {
  if (!response.ok) {
    throw new Error(`${action} failed with status ${response.status}`);
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
  const response = assertResponseOk(
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
  const response = assertResponseOk(
    await fetch(`${buildApiUrl("/api/files")}?path=${encodeURIComponent(path)}`, {
      cache: "no-store",
    }),
    "getFile",
  );

  return (await response.json()) as FilePayload;
}

export async function saveFile(path: string, content: string): Promise<FilePayload> {
  const response = assertResponseOk(
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
  const response = assertResponseOk(
    await fetch(buildApiUrl("/api/sessions"), {
      cache: "no-store",
    }),
    "listSessions",
  );

  const body = (await response.json()) as { sessions: SessionSummary[] };
  return body.sessions;
}
