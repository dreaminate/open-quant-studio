import {
  type DomainEvent,
  validateDomainEvent,
} from "@open-quant-studio/contracts";


export interface DomainEventStreamClient {
  read(request: {
    projectId: string;
    lastAcknowledgedStreamSeq: number;
    signal: AbortSignal;
    onEvent(event: DomainEvent): Promise<void> | void;
  }): Promise<number>;
}

type FetchImplementation = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;


export class FetchDomainEventStreamClient implements DomainEventStreamClient {
  readonly #baseUrl: string;
  readonly #fetch: FetchImplementation;

  constructor(baseUrl: string, fetchImplementation: FetchImplementation = fetch) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#fetch = fetchImplementation;
  }

  async read(request: {
    projectId: string;
    lastAcknowledgedStreamSeq: number;
    signal: AbortSignal;
    onEvent(event: DomainEvent): Promise<void> | void;
  }): Promise<number> {
    const headers = new Headers({ Accept: "text/event-stream" });
    if (request.lastAcknowledgedStreamSeq > 0) {
      headers.set(
        "Last-Event-ID",
        request.lastAcknowledgedStreamSeq.toString(),
      );
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/v1/events?project_id=${encodeURIComponent(request.projectId)}`,
      { headers, signal: request.signal },
    );
    if (!response.ok) {
      throw new Error(`domain event stream returned HTTP ${response.status}`);
    }
    if (!response.headers.get("content-type")?.startsWith("text/event-stream")) {
      throw new Error("domain event stream returned the wrong content type");
    }
    if (response.body === null) {
      throw new Error("domain event stream response has no body");
    }

    let acknowledged = request.lastAcknowledgedStreamSeq;
    let buffer = "";
    const decoder = new TextDecoder();
    const reader = response.body.getReader();

    const dispatch = async (frame: string): Promise<void> => {
      let eventName = "message";
      let id: string | undefined;
      const dataLines: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line === "" || line.startsWith(":")) {
          continue;
        }
        const separator = line.indexOf(":");
        const field = separator === -1 ? line : line.slice(0, separator);
        const rawValue = separator === -1 ? "" : line.slice(separator + 1);
        const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
        if (field === "event") {
          eventName = value;
        } else if (field === "id") {
          id = value;
        } else if (field === "data") {
          dataLines.push(value);
        }
      }
      if (eventName !== "domain.event") {
        throw new Error(`unexpected SSE event type ${eventName}`);
      }
      if (id === undefined || !/^(0|[1-9][0-9]*)$/.test(id)) {
        throw new Error("domain event SSE frame has an invalid id");
      }
      const parsed: unknown = JSON.parse(dataLines.join("\n"));
      const validation = validateDomainEvent(parsed);
      if (!validation.valid) {
        throw new Error(
          `domain event contract violation: ${validation.errors.join("; ")}`,
        );
      }
      const streamSeq = Number(id);
      if (streamSeq !== validation.value.stream_seq) {
        throw new Error("SSE id does not match event stream_seq");
      }
      if (streamSeq <= acknowledged) {
        throw new Error("domain event stream sequence did not advance");
      }
      await request.onEvent(validation.value);
      acknowledged = streamSeq;
    };

    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) {
          break;
        }
        buffer += decoder.decode(chunk.value, { stream: true });
        let boundary = buffer.match(/\r?\n\r?\n/);
        while (boundary?.index !== undefined) {
          const frame = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary[0].length);
          await dispatch(frame);
          boundary = buffer.match(/\r?\n\r?\n/);
        }
      }
      buffer += decoder.decode();
      if (buffer.trim() !== "") {
        await dispatch(buffer);
      }
    } finally {
      reader.releaseLock();
    }
    return acknowledged;
  }
}
