export const API_URL = "/api";
// Centinela interno del frontend: lo lanza handleAuthError para que los `catch` sepan
// que la redirección ya está en marcha y no muestren un error encima.
export const SESSION_EXPIRED_ERROR = "Sesión expirada";
export const SETUP_REQUIRED_ERROR = "Configuración inicial pendiente";

/** Normaliza a es | en (alineado con el backend). */
export function normalizeUiLocale(lang) {
  if (lang == null || typeof lang !== "string") {
    return "es";
  }
  const base = lang.split("-")[0].toLowerCase();
  return base === "en" ? "en" : "es";
}

export function isBackendUnreachableError(error) {
  if (!error) {
    return false;
  }
  if (error instanceof TypeError) {
    return true;
  }
  const msg = typeof error.message === "string" ? error.message : "";
  return /failed to fetch|networkerror|load failed|network request failed/i.test(msg);
}

function projectSegment(name) {
  return encodeURIComponent(name);
}

/** Lee el `code` del cuerpo de un 401 sin consumir el body original del llamador. */
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
    // Alguien vació la base de datos con la pestaña abierta: hay que volver al
    // asistente, no a la pantalla de login.
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

async function request(path, options = {}, context = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: buildHeaders(options, context),
  });
  await handleAuthError(response, context);
  return response;
}

/**
 * Igual que `request` pero sin el manejador global de 401: en los endpoints de
 * autenticación un 401 significa "credenciales incorrectas", no "sesión caducada".
 */
async function publicRequestJson(path, options = {}, context = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: buildHeaders(options, context),
  });
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
    throw new Error(`Respuesta no JSON (${response.status}): ${preview}`);
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
  return `Request failed (${status})`;
}

async function assertOk(response) {
  if (!response.ok) {
    let data;
    try {
      data = await readJsonBody(response);
    } catch (err) {
      throw err instanceof Error ? err : new Error(String(err));
    }
    const error = new Error(errorMessageFromBody(data, response.status));
    // `code` es el slug estable del backend; es lo que elige la clave de i18n en los
    // formularios de autenticación. El mensaje queda para curl y para la consola.
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

export function fetchHistory(context = {}) {
  return requestJson("/history", {}, context);
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
  return publicRequestJson("/auth/credentials", jsonBody(payload), context);
}
