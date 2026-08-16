import assert from "node:assert/strict";
import test from "node:test";

import {
  MODEL_SETTINGS_STORAGE_KEY,
  hydrateModelSettings,
  shouldPersistModelSettings,
  type ModelSettingsStorage,
} from "./model-settings.ts";

function createStorage(initial: Record<string, string>): ModelSettingsStorage {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("hydration retains the saved model configuration before persistence is enabled", () => {
  const storage = createStorage({
    [MODEL_SETTINGS_STORAGE_KEY]: JSON.stringify({
      apiKey: "saved-demo-key",
      baseUrl: "https://provider.example/v1",
      model: "demo-model",
    }),
  });

  assert.equal(shouldPersistModelSettings(false), false);
  assert.deepEqual(hydrateModelSettings(storage), {
    apiKey: "saved-demo-key",
    baseUrl: "https://provider.example/v1",
    model: "demo-model",
  });
  assert.equal(shouldPersistModelSettings(true), true);
});
