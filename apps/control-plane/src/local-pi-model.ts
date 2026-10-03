import {
  fauxAssistantMessage,
  fauxToolCall,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import type { Context } from "@earendil-works/pi-ai";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";


const LOCAL_PI_PROVIDER = "oqs-local-faux";
const LOCAL_PI_RESPONSE = "Pi local demo is connected to the current research Activity.";
const TOOL_TRACER_MARKER = "OQS_TOOL_TRACER";
const TOOL_TRACER_REVISION = "30303030-3030-4030-8030-303030303030";
const TOOL_TRACER_VARIANT = "40404040-4040-4040-8040-404040404040";
const TOOL_TRACER_BASE = "10101010-1010-4010-8010-101010101010";

export async function createLocalPiModel(
  authPath: string,
  options: { toolTracer?: boolean } = {},
) {
  const faux = registerFauxProvider({
    provider: LOCAL_PI_PROVIDER,
    models: [{
      id: "oqs-local-demo",
      name: "OQS local deterministic demo",
      reasoning: false,
      input: ["text"],
    }],
  });
  let tracerStep = 0;
  const response = (context: Context) => {
    faux.appendResponses([response]);
    const tracerRequested = context.messages.some((message: Context["messages"][number]) =>
      message.role === "user"
      && JSON.stringify(message.content).includes(TOOL_TRACER_MARKER));
    if (
      options.toolTracer === true
      && (tracerRequested || tracerStep === 1)
    ) {
      if (tracerStep === 0) {
        tracerStep = 1;
        return fauxAssistantMessage(
          fauxToolCall("strategy_variant_create", {
            base_revision_id: TOOL_TRACER_BASE,
            variant_id: TOOL_TRACER_VARIANT,
          }),
          { stopReason: "toolUse" },
        );
      }
      if (tracerStep === 1) {
        tracerStep = 2;
        return fauxAssistantMessage(
          fauxToolCall("revision_create_child", {
            base_revision_id: TOOL_TRACER_BASE,
            variant_id: TOOL_TRACER_VARIANT,
            message: "Pi tool tracer child revision",
            revision_id: TOOL_TRACER_REVISION,
            files: [{
              path: "strategy.py",
              body: "def on_bar(bar):\n    return []\n# pi-tool-tracer\n",
            }],
          }),
          { stopReason: "toolUse" },
        );
      }
    }
    return fauxAssistantMessage(LOCAL_PI_RESPONSE);
  };
  faux.setResponses([response]);

  const modelRuntime = await ModelRuntime.create({
    authPath,
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = faux.getModel();
  modelRuntime.registerProvider(LOCAL_PI_PROVIDER, {
    baseUrl: "http://localhost:0",
    api: faux.api,
    apiKey: "oqs-local-demo",
    models: [{
      id: model.id,
      name: model.name,
      api: model.api,
      reasoning: model.reasoning,
      input: model.input,
      cost: model.cost,
      contextWindow: model.contextWindow,
      maxTokens: model.maxTokens,
    }],
    streamSimple,
  });
  return {
    model,
    modelRuntime,
    dispose: faux.unregister,
  };
}

export { LOCAL_PI_RESPONSE, TOOL_TRACER_MARKER };
