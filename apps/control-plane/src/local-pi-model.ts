import {
  fauxAssistantMessage,
  registerFauxProvider,
  streamSimple,
} from "@earendil-works/pi-ai/compat";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";


const LOCAL_PI_PROVIDER = "oqs-local-faux";
const LOCAL_PI_RESPONSE = "Pi local demo is connected to the current research Activity.";

export async function createLocalPiModel(authPath: string) {
  const faux = registerFauxProvider({
    provider: LOCAL_PI_PROVIDER,
    models: [{
      id: "oqs-local-demo",
      name: "OQS local deterministic demo",
      reasoning: false,
      input: ["text"],
    }],
  });
  const response = () => {
    faux.appendResponses([response]);
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

export { LOCAL_PI_RESPONSE };
