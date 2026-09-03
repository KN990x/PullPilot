import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchProjects,
  handleAuthError,
  isBackendUnreachableError,
  isTimeoutError,
  login,
  normalizeUiLocale,
  SESSION_EXPIRED_ERROR,
  SETUP_REQUIRED_ERROR,
  updateProject,
} from "./api";

/** Minimal stand-in for fetch's Response: only what the module actually touches. */
function jsonResponse(status, body, { ok } = {}) {
  const text = body === undefined ? "" : JSON.stringify(body);
  const response = {
    status,
    ok: ok ?? (status >= 200 && status < 300),
    headers: new Headers(),
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(body),
  };
  response.clone = () => ({ ...response, clone: response.clone });
  return response;
}

describe("normalizeUiLocale", () => {
  it("collapses regional tags to the two the backend knows", () => {
    expect(normalizeUiLocale("en-US")).toBe("en");
    expect(normalizeUiLocale("es-ES")).toBe("es");
  });

  it("falls back to Spanish for anything else", () => {
    // The browser detector returns "es-ES", which is why the language toggle compared
    // normalised values: raw, the first click after a clean load did nothing.
    expect(normalizeUiLocale("fr")).toBe("es");
    expect(normalizeUiLocale(null)).toBe("es");
    expect(normalizeUiLocale(undefined)).toBe("es");
    expect(normalizeUiLocale(42)).toBe("es");
  });
});

describe("isBackendUnreachableError", () => {
  it("recognises the shapes fetch uses when there is no server", () => {
    expect(isBackendUnreachableError(new TypeError("Failed to fetch"))).toBe(true);
    expect(isBackendUnreachableError(new Error("NetworkError when attempting"))).toBe(true);
    expect(isBackendUnreachableError(new Error("Load failed"))).toBe(true);
  });

  it("does not mistake an application error for a dead backend", () => {
    // This distinction is what decides between the offline card and a real error: it
    // used to fire on any network error and show invented projects instead.
    expect(isBackendUnreachableError(new Error("Request failed (500)"))).toBe(false);
    expect(isBackendUnreachableError(null)).toBe(false);
  });
});

describe("isTimeoutError", () => {
  it("recognises the abort the scan uses when Docker is slow", () => {
    expect(isTimeoutError(Object.assign(new Error("timeout"), { name: "TimeoutError" }))).toBe(
      true
    );
    expect(isTimeoutError(Object.assign(new Error("aborted"), { name: "AbortError" }))).toBe(true);
    expect(isTimeoutError(new TypeError("Failed to fetch"))).toBe(false);
  });
});

describe("handleAuthError", () => {
  it("routes an empty database back to the wizard, not to login", async () => {
    const onSetupRequired = vi.fn();
    const onUnauthorized = vi.fn();

    await expect(
      handleAuthError(jsonResponse(401, { code: "setup_required" }), {
        onSetupRequired,
        onUnauthorized,
      })
    ).rejects.toThrow(SETUP_REQUIRED_ERROR);

    expect(onSetupRequired).toHaveBeenCalledOnce();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("treats any other 401 as an expired session", async () => {
    const onUnauthorized = vi.fn();

    await expect(
      handleAuthError(jsonResponse(401, { code: "session_expired" }), { onUnauthorized })
    ).rejects.toThrow(SESSION_EXPIRED_ERROR);

    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("lets anything that is not a 401 through untouched", async () => {
    const response = jsonResponse(200, { ok: true });

    await expect(handleAuthError(response, {})).resolves.toBe(response);
  });
});

describe("request helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the caller's locale as Accept-Language", async () => {
    fetch.mockResolvedValue(jsonResponse(200, []));

    await fetchProjects({ locale: "en" });

    const [, options] = fetch.mock.calls[0];
    expect(options.headers.get("Accept-Language")).toBe("en");
  });

  it("carries the backend's status and code onto the thrown error", async () => {
    fetch.mockResolvedValue(
      jsonResponse(429, { detail: "too many", code: "rate_limited", retry_after: 42 })
    );

    // The auth forms pick their i18n key from `code`, so it has to survive the throw.
    await expect(login({ username: "a", password: "b" })).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
      retryAfter: 42,
    });
  });

  it("reports an HTML answer instead of failing on JSON.parse", async () => {
    // What the SPA fallback used to return for an API call: index.html with status 200.
    const html = {
      status: 200,
      ok: true,
      headers: new Headers(),
      text: () => Promise.resolve("<!doctype html><div id=root></div>"),
    };
    html.clone = () => html;
    fetch.mockResolvedValue(html);

    await expect(updateProject("plex")).rejects.toThrow(/Non-JSON response/);
  });

  it("joins pydantic's validation messages into one readable string", async () => {
    fetch.mockResolvedValue(
      jsonResponse(422, { detail: [{ msg: "too short" }, { msg: "bad chars" }] })
    );

    await expect(login({ username: "a", password: "b" })).rejects.toThrow(
      "too short; bad chars"
    );
  });

  it("gives every request a deadline so a hung backend cannot pin it forever", async () => {
    // The case this exists for: PullPilot recreating its own container. Without a signal
    // the promise never settles and usePolling's in-flight guard never clears.
    fetch.mockResolvedValue(jsonResponse(200, []));

    await fetchProjects({});

    const [, options] = fetch.mock.calls[0];
    expect(options.signal).toBeInstanceOf(AbortSignal);
  });

  it("treats a timed-out request as an unreachable backend", () => {
    // AbortSignal.timeout rejects with a DOMException named TimeoutError; the offline
    // card is the right answer for it, not a red "server error" toast.
    expect(isBackendUnreachableError(new DOMException("timed out", "TimeoutError"))).toBe(
      true
    );
    expect(isBackendUnreachableError(new DOMException("aborted", "AbortError"))).toBe(true);
  });
});
