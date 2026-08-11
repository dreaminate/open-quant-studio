import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import type {
  FetchQuantDomainRevisionClient,
  RevisionFileInput,
} from "./domain-revision-client.js";
import { stableIdentityUuid } from "./domain-session-client.js";

export interface RevisionToolBinding {
  projectId: string;
  activityId: string;
  sessionId: string;
  workbenchId: string | (() => string);
}

export type RevisionToolClient = Pick<
  FetchQuantDomainRevisionClient,
  | "createRevisionRoot"
  | "createStrategyVariant"
  | "createRevisionChild"
  | "compareRevisions"
  | "promoteRevision"
>;

const uuid = Type.String({
  pattern: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
});
const revisionId = uuid;
const file = Type.Object({
  path: Type.String({ minLength: 1, maxLength: 240 }),
  body: Type.String({ maxLength: 65536 }),
}, { additionalProperties: false });
const files = Type.Array(file, { minItems: 1, maxItems: 32 });

export function createRevisionTools(
  client: RevisionToolClient,
  binding: RevisionToolBinding,
): Array<ReturnType<typeof defineTool>> {
  return [
    defineTool({
      name: "revision_create_root",
      label: "revision_create_root",
      description: "Create an immutable root workspace revision from bounded text files.",
      parameters: Type.Object({
        message: Type.String({ minLength: 1, maxLength: 256 }),
        files,
        revision_id: Type.Optional(revisionId),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.createRevisionRoot({
          ...actor(binding),
          message: params.message,
          files: params.files as RevisionFileInput[],
          revisionId: params.revision_id,
          commandId: params.command_id ?? toolCommandId(binding, "revision_create_root", toolCallId),
        }));
      },
    }),
    defineTool({
      name: "strategy_variant_create",
      label: "strategy_variant_create",
      description: "Fork an independent strategy variant from a revision base.",
      parameters: Type.Object({
        base_revision_id: revisionId,
        variant_id: Type.Optional(uuid),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.createStrategyVariant({
          ...actor(binding),
          baseRevisionId: params.base_revision_id,
          variantId: params.variant_id,
          commandId: params.command_id ?? toolCommandId(binding, "strategy_variant_create", toolCallId),
        }));
      },
    }),
    defineTool({
      name: "revision_create_child",
      label: "revision_create_child",
      description: "Create an immutable child revision on one strategy variant head.",
      parameters: Type.Object({
        base_revision_id: revisionId,
        variant_id: revisionId,
        message: Type.String({ minLength: 1, maxLength: 256 }),
        files,
        revision_id: Type.Optional(revisionId),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.createRevisionChild({
          ...actor(binding),
          baseRevisionId: params.base_revision_id,
          variantId: params.variant_id,
          message: params.message,
          files: params.files as RevisionFileInput[],
          revisionId: params.revision_id,
          commandId: params.command_id ?? toolCommandId(binding, "revision_create_child", toolCallId),
        }));
      },
    }),
    defineTool({
      name: "revision_compare",
      label: "revision_compare",
      description: "Compare two immutable revisions by bounded artifact metadata.",
      parameters: Type.Object({
        left_revision_id: revisionId,
        right_revision_id: revisionId,
      }, { additionalProperties: false }),
      async execute(_toolCallId, params) {
        return textResult(await client.compareRevisions(
          binding.projectId,
          params.left_revision_id,
          params.right_revision_id,
        ));
      },
    }),
    defineTool({
      name: "revision_promote",
      label: "revision_promote",
      description: "Promote a candidate revision with compare-and-set against the project head.",
      parameters: Type.Object({
        expected_revision_id: revisionId,
        variant_id: revisionId,
        candidate_revision_id: revisionId,
        base_revision_id: Type.Optional(revisionId),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.promoteRevision({
          ...actor(binding),
          expectedRevisionId: params.expected_revision_id,
          variantId: params.variant_id,
          candidateRevisionId: params.candidate_revision_id,
          baseRevisionId: params.base_revision_id,
          commandId: params.command_id ?? toolCommandId(binding, "revision_promote", toolCallId),
        }));
      },
    }),
  ];
}

function toolCommandId(
  binding: RevisionToolBinding,
  toolName: string,
  toolCallId: string,
): string {
  return stableIdentityUuid([
    "pi-tool",
    binding.projectId,
    binding.activityId,
    binding.sessionId,
    toolName,
    toolCallId,
  ].join(":"));
}

function actor(binding: RevisionToolBinding) {
  return {
    projectId: binding.projectId,
    activityId: binding.activityId,
    sessionId: binding.sessionId,
    workbenchId: typeof binding.workbenchId === "function"
      ? binding.workbenchId()
      : binding.workbenchId,
  };
}

function textResult(value: unknown) {
  const serialized = JSON.stringify(value);
  const bounded = serialized.length <= 16_384
    ? serialized
    : `${serialized.slice(0, 16_384)}…[bounded]`;
  return { content: [{ type: "text" as const, text: bounded }], details: null };
}
