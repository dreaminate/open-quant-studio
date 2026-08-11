import { PiSessionAdapter } from "./pi-session-adapter.js";


export interface SessionRegistration {
  adapter: PiSessionAdapter;
  projectId: string;
  activityId: string;
  workbenchId: string;
}

export interface SessionRegistryStatus {
  sessionId: string;
  piSessionId: string;
  projectId: string;
  activityId: string;
  workbenchIds: string[];
  activeWorkbenchId: string;
  isStreaming: boolean;
}

interface ActiveSession {
  adapter: PiSessionAdapter;
  projectId: string;
  activityId: string;
  workbenchIds: Set<string>;
  activeWorkbenchId: string;
}

/** In-memory active routing only; Python owns the durable catalog and Pi owns conversation JSONL. */
export class SessionRegistry {
  readonly #sessions = new Map<string, ActiveSession>();

  register(registration: SessionRegistration): PiSessionAdapter {
    const sessionId = registration.adapter.sessionId;
    const existing = this.#sessions.get(sessionId);
    if (existing !== undefined) {
      if (existing.adapter !== registration.adapter) {
        throw new Error(`domain session ${sessionId} is already bound to a different Pi adapter`);
      }
      if (existing.adapter.piSessionId !== registration.adapter.piSessionId) {
        throw new Error(`domain session ${sessionId} cannot be remapped to a different Pi session`);
      }
      if (existing.projectId !== registration.projectId) {
        throw new Error(`domain session ${sessionId} cannot be remapped to a different project`);
      }
      if (existing.activityId !== registration.activityId) {
        throw new Error(`domain session ${sessionId} cannot be remapped to a different activity`);
      }
      existing.workbenchIds.add(registration.workbenchId);
      return existing.adapter;
    }
    if (registration.adapter.projectId !== registration.projectId) {
      throw new Error(`Pi adapter project does not match domain session ${sessionId}`);
    }
    if (registration.adapter.activityId !== registration.activityId) {
      throw new Error(`Pi adapter activity does not match domain session ${sessionId}`);
    }
    this.#sessions.set(sessionId, {
      adapter: registration.adapter,
      projectId: registration.projectId,
      activityId: registration.activityId,
      workbenchIds: new Set([registration.workbenchId]),
      activeWorkbenchId: registration.workbenchId,
    });
    return registration.adapter;
  }

  bindWorkbench(sessionId: string, workbenchId: string): PiSessionAdapter {
    const active = this.#sessions.get(sessionId);
    if (active === undefined) {
      throw new Error(`domain session ${sessionId} is not registered`);
    }
    active.workbenchIds.add(workbenchId);
    return active.adapter;
  }

  activateWorkbench(sessionId: string, workbenchId: string): PiSessionAdapter {
    const active = this.#sessions.get(sessionId);
    if (active === undefined) {
      throw new Error(`domain session ${sessionId} is not registered`);
    }
    if (!active.workbenchIds.has(workbenchId)) {
      throw new Error(`workbench ${workbenchId} is not bound to session ${sessionId}`);
    }
    active.activeWorkbenchId = workbenchId;
    return active.adapter;
  }

  get(sessionId: string): PiSessionAdapter | undefined {
    return this.#sessions.get(sessionId)?.adapter;
  }

  status(sessionId: string): SessionRegistryStatus | undefined {
    const active = this.#sessions.get(sessionId);
    if (active === undefined) {
      return undefined;
    }
    return {
      sessionId,
      piSessionId: active.adapter.piSessionId,
      projectId: active.projectId,
      activityId: active.activityId,
      workbenchIds: [...active.workbenchIds].sort(),
      activeWorkbenchId: active.activeWorkbenchId,
      isStreaming: active.adapter.isStreaming,
    };
  }

  list(): SessionRegistryStatus[] {
    return [...this.#sessions.keys()]
      .sort()
      .map((sessionId) => this.status(sessionId))
      .filter((status): status is SessionRegistryStatus => status !== undefined);
  }

  unregister(sessionId: string): boolean {
    const active = this.#sessions.get(sessionId);
    if (active === undefined) {
      return false;
    }
    this.#sessions.delete(sessionId);
    active.adapter.dispose();
    return true;
  }

  dispose(): void {
    for (const sessionId of this.#sessions.keys()) {
      this.unregister(sessionId);
    }
  }
}
