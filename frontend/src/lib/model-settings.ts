export type ModelSettings = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export const MODEL_SETTINGS_STORAGE_KEY = "mini-openclaw-model-settings";

export const defaultModelSettings: ModelSettings = {
  apiKey: "",
  baseUrl: "https://api.codexzh.com/v1",
  model: "cc-gpt-5.6-terra",
};

const LEGACY_DEFAULT_MODEL = "gpt-5.4";

export type ModelSettingsStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function normalizeModelSettings(raw: unknown): ModelSettings {
  if (!raw || typeof raw !== "object") {
    return defaultModelSettings;
  }

  const candidate = raw as Partial<Record<keyof ModelSettings, unknown>>;
  const baseUrl = typeof candidate.baseUrl === "string" && candidate.baseUrl.trim()
    ? candidate.baseUrl
    : defaultModelSettings.baseUrl;
  const model = typeof candidate.model === "string" && candidate.model.trim()
    ? candidate.model
    : defaultModelSettings.model;
  const isLegacyDefault = baseUrl === defaultModelSettings.baseUrl && model === LEGACY_DEFAULT_MODEL;

  return {
    // Only migrate the prior built-in provider/model pair; custom providers remain untouched.
    apiKey: isLegacyDefault
      ? defaultModelSettings.apiKey
      : typeof candidate.apiKey === "string"
        ? candidate.apiKey
        : defaultModelSettings.apiKey,
    baseUrl,
    model: isLegacyDefault ? defaultModelSettings.model : model,
  };
}

export function hydrateModelSettings(storage: Pick<ModelSettingsStorage, "getItem" | "removeItem"> | null | undefined): ModelSettings {
  if (!storage) {
    return defaultModelSettings;
  }

  const raw = storage.getItem(MODEL_SETTINGS_STORAGE_KEY);
  if (!raw) {
    return defaultModelSettings;
  }

  try {
    return normalizeModelSettings(JSON.parse(raw));
  } catch {
    storage.removeItem(MODEL_SETTINGS_STORAGE_KEY);
    return defaultModelSettings;
  }
}

export function loadModelSettings(): ModelSettings {
  return hydrateModelSettings(typeof window === "undefined" ? null : window.localStorage);
}

export function shouldPersistModelSettings(hasHydrated: boolean): boolean {
  return hasHydrated;
}

export function saveModelSettings(settings: ModelSettings): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(MODEL_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}
