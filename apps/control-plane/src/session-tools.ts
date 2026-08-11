import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import type { SessionFabric } from "./session-fabric.js";

export interface SessionFabricToolBinding {
  sessionId: string;
  workbenchId: string | (() => string);
}

const empty = Type.Object({});
const sessionId = Type.String({ minLength: 1, maxLength: 128 });
const sourceRef = Type.Object({
  session_id: sessionId,
  entry_id: sessionId,
  leaf_id: sessionId,
  sha256: Type.String({ pattern: "^[a-f0-9]{64}$" }),
  source_uri: Type.String({
    pattern: "^pi-jsonl://session/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?#entry=[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?$",
  }),
}, { additionalProperties: false });
const sourceRefs = Type.Array(sourceRef, { maxItems: 16 });

export function createSessionFabricTools(fabric: Pick<SessionFabric,
  "list" | "status" | "search" | "context" | "send" | "ask" | "reply" | "pull" | "acknowledge"
>, binding: SessionFabricToolBinding): Array<ReturnType<typeof defineTool>> {
  return [
    defineTool({
      name: "session_list",
      label: "session_list",
      description: "List bounded durable research sessions in the current project.",
      parameters: empty,
      async execute() {
        return textResult(await fabric.list());
      },
    }),
    defineTool({
      name: "session_status",
      label: "session_status",
      description: "Read one durable or active research session status.",
      parameters: Type.Object({ session_id: sessionId }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.status(params.session_id));
      },
    }),
    defineTool({
      name: "session_search",
      label: "session_search",
      description: "Search bounded same-project Pi JSONL evidence.",
      parameters: Type.Object({
        query: Type.String({ minLength: 1, maxLength: 256 }),
        top_k: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })),
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.search(params.query, params.top_k));
      },
    }),
    defineTool({
      name: "session_context",
      label: "session_context",
      description: "Read a bounded anchored Pi JSONL context window as quoted data.",
      parameters: Type.Object({
        session_id: sessionId,
        entry_id: sessionId,
        leaf_id: Type.Optional(sessionId),
        before: Type.Optional(Type.Integer({ minimum: 0, maximum: 10 })),
        after: Type.Optional(Type.Integer({ minimum: 0, maximum: 10 })),
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.context(
          params.session_id,
          params.entry_id,
          params.before,
          params.after,
          params.leaf_id,
        ));
      },
    }),
    defineTool({
      name: "session_send",
      label: "session_send",
      description: "Send a bounded research message through the durable inbox.",
      parameters: Type.Object({
        recipient_session_id: sessionId,
        body: Type.String({ maxLength: 65536 }),
        source_refs: Type.Optional(sourceRefs),
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.send({
          sessionId: binding.sessionId,
          recipientSessionId: params.recipient_session_id,
          body: params.body,
          sourceRefs: params.source_refs,
          workbenchId: resolveWorkbench(binding),
        }));
      },
    }),
    defineTool({
      name: "session_ask",
      label: "session_ask",
      description: "Ask another research session through the durable inbox.",
      parameters: Type.Object({
        recipient_session_id: sessionId,
        body: Type.String({ maxLength: 65536 }),
        source_refs: Type.Optional(sourceRefs),
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.ask({
          sessionId: binding.sessionId,
          recipientSessionId: params.recipient_session_id,
          body: params.body,
          sourceRefs: params.source_refs,
          workbenchId: resolveWorkbench(binding),
        }));
      },
    }),
    defineTool({
      name: "session_reply",
      label: "session_reply",
      description: "Reply to an ask with at least one verified Pi source reference.",
      parameters: Type.Object({
        recipient_session_id: sessionId,
        reply_to: sessionId,
        body: Type.String({ maxLength: 65536 }),
        source_refs: sourceRefs,
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.reply({
          sessionId: binding.sessionId,
          recipientSessionId: params.recipient_session_id,
          replyTo: params.reply_to,
          body: params.body,
          sourceRefs: params.source_refs,
          workbenchId: resolveWorkbench(binding),
        }));
      },
    }),
    defineTool({
      name: "inbox_pull",
      label: "inbox_pull",
      description: "Read the bounded inbox; delivery is explicit and wake is opt-in.",
      parameters: Type.Object({
        after: Type.Optional(Type.Integer({ minimum: 0 })),
        limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })),
        deliver: Type.Optional(Type.Boolean()),
        wake: Type.Optional(Type.Boolean()),
      }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.pull(binding.sessionId, {
          after: params.after,
          limit: params.limit,
          deliver: params.deliver,
          wake: params.wake,
          workbenchId: resolveWorkbench(binding),
        }));
      },
    }),
    defineTool({
      name: "inbox_ack",
      label: "inbox_ack",
      description: "Acknowledge one already injected durable inbox message.",
      parameters: Type.Object({ message_id: sessionId }),
      async execute(_toolCallId, params) {
        return textResult(await fabric.acknowledge(binding.sessionId, params.message_id));
      },
    }),
  ];
}

function resolveWorkbench(binding: SessionFabricToolBinding): string {
  return typeof binding.workbenchId === "function"
    ? binding.workbenchId()
    : binding.workbenchId;
}

function textResult(value: unknown) {
  const serialized = JSON.stringify(value);
  const bounded = serialized.length <= 16_384
    ? serialized
    : `${serialized.slice(0, 16_384)}…[bounded]`;
  return { content: [{ type: "text" as const, text: bounded }], details: null };
}
