import { describe, expect, it, vi } from "vitest";

describe("static site mode", () => {
  it("stays in replay even at the last step, so nothing calls an API", async () => {
    vi.stubEnv("VITE_STATIC", "1");
    vi.resetModules();
    const replay = await import("./replay");
    expect(replay.STATIC).toBe(true);
    expect(replay.inReplay()).toBe(true); // the page opens on the last step
    expect(replay.modeKey()).not.toBe("live");
    vi.unstubAllEnvs();
  });
});
