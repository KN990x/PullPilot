export const API_URL = "/api";
// Internal sentinels: handleAuthError throws one so `catch` blocks know the redirect is
// already under way and do not stack an error on top. Deliberately not human text — they
// used to be the Spanish strings the backend sends, compared with `===` at nine call
// sites, so rewording a message silently broke every one of them.
export const SESSION_EXPIRED_ERROR = "__pullpilot_session_expired__";
export const SETUP_REQUIRED_ERROR = "__pullpilot_setup_required__";

/** True for the two sentinels above: the app is already navigating, stay quiet. */
export function isAuthRedirectError(error) {
  return (
    error?.message === SESSION_EXPIRED_ERROR || error?.message === SETUP_REQUIRED_ERROR
  );
}

/** Normalise to es | en, matching the backend. */
export function normalizeUiLocale(lang) {
  if (lang == null || typeof lang !== "string") {
    return "es";
  }
  const base = lang.split("-")[0].toLowerCase();
  return base === "en" ? "en" : "es";
}

/** True when we gave up waiting, not when the TCP connection itself failed. */
export function isTimeoutError(error) {
  return Boolean(error) && (error.name === "TimeoutError" || error.name === "AbortError");
}

export function isBackendUnreachableError(error) {
  if (!error) {
    return false;
  }
  if (error instanceof TypeError) {
    return true;
  }
  // A request we gave up on is a backend that is not answering, which is the case the
  // offline card exists for. AbortSignal.timeout rejects with a DOMException named
  // "TimeoutError"; `name` is checked rather than `instanceof` so it also holds for the
  // plain object shapes the tests use.
  if (isTimeoutError(error)) {
    return true;
  }
  const msg = typeof error.message === "string" ? error.message : "";
  return /failed to fetch|networkerror|load failed|network request failed/i.test(msg);
}

function projectSegment(name) {
  return encodeURIComponent(name);
}

/** Read a 401's `code` without consuming the caller's body. */
async function peekErrorCode(response) {
  try {
    const data = await response.clone().json();
    return data && typeof data === "object" ? data.code : undefined;
  } catch {
    return undefined;
  }
}

export async function handleAuthError(response, options = {}) {
  if (response.status === 401) {
    const code = await peekErrorCode(response);
    // The database was emptied with the tab open: back to the wizard, not to login.
    if (code === "setup_required") {
      if (typeof options.onSetupRequired === "function") {
        options.onSetupRequired();
      }
      throw new Error(SETUP_REQUIRED_ERROR);
    }
    if (typeof options.onUnauthorized === "function") {
      options.onUnauthorized();
    }
    throw new Error(SESSION_EXPIRED_ERROR);
  }
  return response;
}

function buildHeaders(options, context) {
  const headers = new Headers(options.headers ?? undefined);
  if (context.locale) {
    headers.set("Accept-Language", context.locale);
  }
  return headers;
}

// A hung backend is not hypothetical here: it is what PullPilot looks like from the
// browser while it recreates its own container. Without a deadline the promise never
// settles, usePolling's in-flight guard never clears and the progress bar freezes
// forever instead of falling through to the offline card.
const DEFAULT_TIMEOUT_MS = 30000;

function withTimeout(options) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = options;
  // Callers never pass their own signal today; if one ever does, it wins and owns the
  // deadline itself.
  return rest.signal ? rest : { ...rest, signal: AbortSignal.timeout(timeoutMs) };
}

async function doFetch(path, options, context) {
  return fetch(`${API_URL}${path}`, {
    ...withTimeout(options),
    headers: buildHeaders(options, context),
  });
}

async function request(path, options = {}, context = {}) {
  const response = await doFetch(path, options, context);
  await handleAuthError(response, context);
  return response;
}

/**
 * Like `request` but without the global 401 handler: on the auth endpoints a 401 means
 * "wrong credentials", not "session expired".
 */
async function publicRequestJson(path, options = {}, context = {}) {
  const response = await doFetch(path, options, context);
  await assertOk(response);
  return readJsonBody(response);
}

/**
 * For endpoints that answer 401 for both reasons. `/api/auth/credentials` is behind the
 * session middleware, so an expired cookie 401s there before the handler runs — treating
 * that like a wrong password left the dialog showing "session expired" with no way out.
 * Only the middleware's own codes trigger the redirect; the rest stay form errors.
 */
async function sessionAwareRequestJson(path, options = {}, context = {}) {
  const response = await doFetch(path, options, context);
  if (response.status === 401) {
    const code = await peekErrorCode(response);
    if (code === "session_expired" || code === "setup_required") {
      await handleAuthError(response, context);
    }
  }
  await assertOk(response);
  return readJsonBody(response);
}

function jsonBody(payload) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

async function readJsonBody(response) {
  const text = await response.text();
  if (!text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    const preview = text.length > 200 ? `${text.slice(0, 200)}…` : text;
    const error = new Error(`Non-JSON response (${response.status}): ${preview}`);
    // Carried so callers can still branch on the status. A reverse proxy answering 502
    // with an HTML page used to produce an error with no `status` at all, so the 409
    // check in the update flow missed it.
    error.status = response.status;
    throw error;
  }
}

function errorMessageFromBody(data, status) {
  if (data && typeof data === "object") {
    const detail = data.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) {
      return detail.map((d) => d.msg).join("; ");
    }
  }
  // English, like every other developer-facing string here. These reach the console and
  // curl; what the user reads comes from the i18n key picked by `error.code`.
  return `Request failed (${status})`;
}

async function assertOk(response) {
  if (!response.ok) {
    let data;
    try {
      data = await readJsonBody(response);
    } catch (err) {
      // readJsonBody already stamped `status` on it.
      throw err instanceof Error ? err : new Error(String(err));
    }
    const error = new Error(errorMessageFromBody(data, response.status));
    // `code` is the backend's stable slug and picks the i18n key in the auth forms.
    // The message is for curl and the console.
    error.status = response.status;
    if (data && typeof data === "object") {
      error.code = data.code;
      error.retryAfter = data.retry_after;
    }
    throw error;
  }
}

async function requestJson(path, options = {}, context = {}) {
  const response = await request(path, options, context);
  await assertOk(response);
  return readJsonBody(response);
}

export function fetchProjects(context = {}) {
  return requestJson("/projects", {}, context);
}

/**
 * `limit`/`offset` exist so the UI can reach past the newest 20. HISTORY_RETENTION keeps
 * 200 rows and the endpoint has always paged; nothing ever asked it to.
 */
export function fetchHistory(context = {}, { limit, offset } = {}) {
  const params = new URLSearchParams();
  if (limit != null) {
    params.set("limit", String(limit));
  }
  if (offset) {
    params.set("offset", String(offset));
  }
  const query = params.toString();
  return requestJson(`/history${query ? `?${query}` : ""}`, {}, context);
}

export function fetchSchedules(context = {}) {
  return requestJson("/schedules", {}, context);
}

export function fetchUpdateStatus(context = {}) {
  return requestJson("/update-status", {}, context);
}

export async function triggerUpdateAll(context = {}) {
  const response = await request("/update-all", { method: "POST" }, context);
  await assertOk(response);
}

/**
 * Starts the deploy; it does not wait for it. The answer is a 202 acknowledgement and the
 * outcome arrives through fetchUpdateStatus's `projects` map.
 *
 * It used to hold the request open for the whole thing — up to 300 s per command plus the
 * healthcheck — which any reverse proxy with a 60 s read timeout turned into a reported
 * failure for a deploy that had worked.
 */
export async function updateProject(name, context = {}) {
  const response = await request(
    `/projects/${projectSegment(name)}/update`,
    { method: "POST" },
    context
  );
  await assertOk(response);
  return readJsonBody(response);
}

export async function toggleProjectSetting(name, setting, context = {}) {
  const response = await request(
    `/projects/${projectSegment(name)}/toggle_${setting}`,
    { method: "POST" },
    context
  );
  await assertOk(response);
}

export async function createSchedule(payload, context = {}) {
  const response = await request(
    "/schedules",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    context
  );
  await assertOk(response);
  return readJsonBody(response);
}

export async function deleteSchedule(id, context = {}) {
  const response = await request(`/schedules/${id}`, { method: "DELETE" }, context);
  await assertOk(response);
}

export function fetchAuthStatus(context = {}) {
  return publicRequestJson("/auth/status", {}, context);
}

export function setupCredentials(payload, context = {}) {
  return publicRequestJson("/auth/setup", jsonBody(payload), context);
}

export function login(payload, context = {}) {
  return publicRequestJson("/auth/login", jsonBody(payload), context);
}

export function logout(context = {}) {
  return publicRequestJson("/auth/logout", { method: "POST" }, context);
}

export function changeCredentials(payload, context = {}) {
  return sessionAwareRequestJson("/auth/credentials", jsonBody(payload), context);
}
