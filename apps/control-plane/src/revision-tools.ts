import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { createHash } from "node:crypto";

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
  | "getProjectRevisionHead"
  | "listVariants"
  | "getRevision"
  | "getArtifact"
  | "getArtifactContent"
  | "compareRevisions"
  | "createMergeCandidate"
  | "requestFormalRun"
  | "listDataSnapshots"
  | "getDataSnapshot"
  | "getDataSnapshotMarketInput"
  | "promoteRevision"
>;

/** The bounded snapshot fields Pi needs to bind a Formal Run. */
interface SnapshotRunBinding {
  snapshot_id: string;
  market_input_artifact_id: string;
  market_input_sha256: string;
  sha256: string;
  price_basis: "raw" | "qfq" | "hfq";
  cutoff: string;
  timezone: string;
  sample_start: string;
  sample_end: string;
  schema_version: 1 | 2 | 3;
  execution_profile?: "legacy" | "a-share-v3";
}

const uuid = Type.String({
  pattern: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
});
const revisionId = uuid;
const sha256 = Type.String({ pattern: "^[a-f0-9]{64}$" });
const gitOid = Type.String({ pattern: "^[a-f0-9]{40}$" });
const file = Type.Object({
  path: Type.String({ minLength: 1, maxLength: 240 }),
  body: Type.String({ maxLength: 65536 }),
}, { additionalProperties: false });
const files = Type.Array(file, { minItems: 1, maxItems: 32 });
const DEFAULT_PARAMETERS_SHA256 = sha256Text("{}");
const DEFAULT_COST_MODEL_SHA256 = sha256Text("oqs-a-share-v3-default-costs");
const DEFAULT_ENVIRONMENT_LOCK_SHA256 = sha256Text("oqs-local-environment");
const reviewAttestation = Type.Object({
  attestation_id: Type.Optional(uuid),
  status: Type.Literal("approved"),
  candidate_revision_id: revisionId,
  strategy_tree_oid: gitOid,
  data_snapshot_sha256: sha256,
  parameters_sha256: sha256,
  cost_model_sha256: sha256,
  reviewer_id: Type.Optional(Type.String({ minLength: 1, maxLength: 256 })),
  reviewed_at: Type.Optional(Type.String({ minLength: 1, maxLength: 64 })),
}, { additionalProperties: false });

export function createRevisionTools(
  client: RevisionToolClient,
  binding: RevisionToolBinding,
): Array<ReturnType<typeof defineTool>> {
  return [
    defineTool({
      name: "strategy_workspace_read",
      label: "strategy_workspace_read",
      description: "Read the current OQS project head, immutable strategy variants, and available DataSnapshots before choosing revision or Run identities.",
      parameters: Type.Object({}, { additionalProperties: false }),
      async execute() {
        const [projectHead, variants, snapshots] = await Promise.all([
          client.getProjectRevisionHead(binding.projectId),
          client.listVariants(binding.projectId),
          client.listDataSnapshots(binding.projectId),
        ]);
        return textResult({ project_head: projectHead, variants, snapshots: snapshots.snapshots });
      },
    }),
    defineTool({
      name: "revision_file_read",
      label: "revision_file_read",
      description: "Read one verified UTF-8 source file from an immutable OQS revision before creating a child or merge candidate.",
      parameters: Type.Object({
        revision_id: revisionId,
        path: Type.String({ minLength: 1, maxLength: 240 }),
      }, { additionalProperties: false }),
      async execute(_toolCallId, params) {
        const revision = await client.getRevision(binding.projectId, params.revision_id);
        const fileMetadata = revision.files.find((file) => file.path === params.path);
        if (fileMetadata === undefined) {
          throw new Error("revision file is unavailable");
        }
        const artifact = await client.getArtifact(binding.projectId, fileMetadata.artifact_id);
        if (
          artifact.artifact_id !== fileMetadata.artifact_id
          || artifact.sha256 !== fileMetadata.sha256
          || artifact.byte_size !== fileMetadata.byte_size
          || artifact.media_type !== fileMetadata.media_type
        ) {
          throw new Error("revision file artifact identity changed");
        }
        const body = new TextDecoder("utf-8", { fatal: true }).decode(
          await client.getArtifactContent(binding.projectId, artifact),
        );
        return sourceResult({
          revision_id: revision.revision_id,
          git_tree_oid: revision.git_tree_oid,
          path: fileMetadata.path,
          sha256: fileMetadata.sha256,
          body,
        });
      },
    }),
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
      name: "merge_candidate_create",
      label: "merge_candidate_create",
      description: "Create an immutable ordered two-parent merge candidate without moving either head.",
      parameters: Type.Object({
        expected_revision_id: revisionId,
        variant_id: revisionId,
        base_revision_id: revisionId,
        message: Type.String({ minLength: 1, maxLength: 256 }),
        files,
        candidate_revision_id: Type.Optional(revisionId),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.createMergeCandidate({
          ...actor(binding),
          expectedRevisionId: params.expected_revision_id,
          variantId: params.variant_id,
          baseRevisionId: params.base_revision_id,
          message: params.message,
          files: params.files as RevisionFileInput[],
          candidateRevisionId: params.candidate_revision_id,
          commandId: params.command_id ??
            toolCommandId(binding, "merge_candidate_create", toolCallId),
        }));
      },
    }),
    defineTool({
      name: "formal_run_request",
      label: "formal_run_request",
      description: "Stage one exact market input and run the streamed strategy plus checkpointed PyO3 formal gates.",
      parameters: Type.Object({
        candidate_revision_id: revisionId,
        variant_id: revisionId,
        market_input_json: Type.String({ minLength: 2, maxLength: 5 * 1024 * 1024 }),
        data_snapshot_id: uuid,
        data_snapshot_sha256: sha256,
        strategy_tree_oid: gitOid,
        parameters_sha256: sha256,
        cost_model_sha256: sha256,
        environment_lock_sha256: sha256,
        price_basis: Type.Union([
          Type.Literal("raw"),
          Type.Literal("qfq"),
          Type.Literal("hfq"),
        ]),
        cutoff: Type.String({ minLength: 1, maxLength: 64 }),
        timezone: Type.String({ minLength: 1, maxLength: 64 }),
        sample_start: Type.String({ minLength: 1, maxLength: 64 }),
        sample_end: Type.String({ minLength: 1, maxLength: 64 }),
        random_seed: Type.Integer({ minimum: 0 }),
        checkpoint_batch_size: Type.Optional(Type.Integer({ minimum: 1, maximum: 250000 })),
        run_spec_id: Type.Optional(uuid),
        run_id: Type.Optional(uuid),
        validation_id: Type.Optional(uuid),
        review_attestation: Type.Optional(reviewAttestation),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.requestFormalRun({
          ...actor(binding),
          candidateRevisionId: params.candidate_revision_id,
          variantId: params.variant_id,
          marketInputJson: params.market_input_json,
          dataSnapshotId: params.data_snapshot_id,
          dataSnapshotSha256: params.data_snapshot_sha256,
          strategyTreeOid: params.strategy_tree_oid,
          parametersSha256: params.parameters_sha256,
          costModelSha256: params.cost_model_sha256,
          environmentLockSha256: params.environment_lock_sha256,
          priceBasis: params.price_basis,
          cutoff: params.cutoff,
          timezone: params.timezone,
          sampleStart: params.sample_start,
          sampleEnd: params.sample_end,
          randomSeed: params.random_seed,
          checkpointBatchSize: params.checkpoint_batch_size,
          runSpecId: params.run_spec_id,
          runId: params.run_id,
          validationId: params.validation_id,
          reviewAttestation: params.review_attestation,
          commandId: params.command_id ??
            toolCommandId(binding, "formal_run_request", toolCallId),
        }));
      },
    }),
    defineTool({
      name: "data_snapshot_list",
      label: "data_snapshot_list",
      description: "List immutable DataSnapshots available to this OQS project.",
      parameters: Type.Object({}, { additionalProperties: false }),
      async execute(_toolCallId) {
        return textResult(await client.listDataSnapshots(binding.projectId));
      },
    }),
    defineTool({
      name: "formal_run_snapshot",
      label: "formal_run_snapshot",
      description: "Request an OQS Formal Run from an existing immutable DataSnapshot after an explicit user review attestation. The tool fetches and verifies the snapshot market input and candidate revision identity; it never accepts caller-supplied fixture market data or self-approves a review.",
      parameters: Type.Object({
        candidate_revision_id: revisionId,
        variant_id: revisionId,
        data_snapshot_id: uuid,
        parameters_sha256: Type.Optional(sha256),
        cost_model_sha256: Type.Optional(sha256),
        environment_lock_sha256: Type.Optional(sha256),
        random_seed: Type.Optional(Type.Integer({ minimum: 0 })),
        checkpoint_batch_size: Type.Optional(Type.Integer({ minimum: 1, maximum: 250000 })),
        run_spec_id: Type.Optional(uuid),
        run_id: Type.Optional(uuid),
        validation_id: Type.Optional(uuid),
        review_attestation: reviewAttestation,
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        const snapshot = await client.getDataSnapshot(
          binding.projectId,
          params.data_snapshot_id,
        ) as SnapshotRunBinding;
        if (snapshot.snapshot_id !== params.data_snapshot_id) {
          throw new Error("DataSnapshot identity changed while preparing Formal Run");
        }
        if (snapshot.schema_version !== 3 || snapshot.execution_profile !== "a-share-v3") {
          throw new Error("formal_run_snapshot requires an A-share-v3 DataSnapshot");
        }
        const revision = await client.getRevision(
          binding.projectId,
          params.candidate_revision_id,
        );
        if (revision.variant_id !== params.variant_id) {
          throw new Error("candidate revision does not belong to the requested variant");
        }
        const marketInputJson = await client.getDataSnapshotMarketInput(
          binding.projectId,
          snapshot as never,
        );
        const parametersSha256 = params.parameters_sha256 ?? DEFAULT_PARAMETERS_SHA256;
        const costModelSha256 = params.cost_model_sha256 ?? DEFAULT_COST_MODEL_SHA256;
        const commandId = params.command_id ??
          toolCommandId(binding, "formal_run_snapshot", toolCallId);
        return textResult(await client.requestFormalRun({
          ...actor(binding),
          candidateRevisionId: params.candidate_revision_id,
          variantId: params.variant_id,
          marketInputJson,
          dataSnapshotId: snapshot.snapshot_id,
          dataSnapshotSha256: snapshot.sha256,
          strategyTreeOid: revision.git_tree_oid,
          parametersSha256,
          costModelSha256,
          environmentLockSha256: params.environment_lock_sha256 ?? DEFAULT_ENVIRONMENT_LOCK_SHA256,
          priceBasis: snapshot.price_basis,
          cutoff: snapshot.cutoff,
          timezone: snapshot.timezone,
          sampleStart: snapshot.sample_start,
          sampleEnd: snapshot.sample_end,
          randomSeed: params.random_seed ?? 0,
          checkpointBatchSize: params.checkpoint_batch_size,
          runSpecId: params.run_spec_id,
          runId: params.run_id,
          validationId: params.validation_id,
          commandId,
          reviewAttestation: params.review_attestation,
          marketInputOriginKind: "service_generated",
          marketInputSourceRef: snapshot.market_input_artifact_id,
        }));
      },
    }),
    defineTool({
      name: "revision_promote",
      label: "revision_promote",
      description: "Promote an exactly validated merge candidate with compare-and-set against both heads.",
      parameters: Type.Object({
        expected_revision_id: revisionId,
        variant_id: revisionId,
        candidate_revision_id: revisionId,
        validation_id: uuid,
        base_revision_id: Type.Optional(revisionId),
        command_id: Type.Optional(uuid),
      }, { additionalProperties: false }),
      async execute(toolCallId, params) {
        return textResult(await client.promoteRevision({
          ...actor(binding),
          expectedRevisionId: params.expected_revision_id,
          variantId: params.variant_id,
          candidateRevisionId: params.candidate_revision_id,
          validationId: params.validation_id,
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

function sourceResult(value: unknown) {
  const serialized = JSON.stringify(value);
  if (serialized.length > 65_536) {
    throw new Error("revision source exceeds the bounded Pi tool result");
  }
  return { content: [{ type: "text" as const, text: serialized }], details: null };
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
