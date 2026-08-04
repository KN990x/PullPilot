import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import AccountModal from "./components/AccountModal";
import AuthLayout from "./components/AuthLayout";
import ConfirmDialog from "./components/ConfirmDialog";
import Dashboard from "./components/Dashboard";
import Footer from "./components/Footer";
import Header from "./components/Header";
import HistoryView from "./components/HistoryView";
import LoginView from "./components/LoginView";
import LogModal from "./components/LogModal";
import OfflineView from "./components/OfflineView";
import ProgressBar from "./components/ProgressBar";
import ScheduleView from "./components/ScheduleView";
import SetupView from "./components/SetupView";
import Toaster from "./components/Toaster";
import { usePolling } from "./hooks/usePolling";
import { useToasts } from "./hooks/useToasts";
import {
  changeCredentials,
  createSchedule,
  deleteSchedule,
  fetchAuthStatus,
  fetchHistory,
  fetchProjects,
  fetchSchedules,
  fetchUpdateStatus,
  isAuthRedirectError,
  isBackendUnreachableError,
  login,
  logout,
  normalizeUiLocale,
  setupCredentials,
  toggleProjectSetting,
  triggerUpdateAll,
  updateProject,
} from "./lib/api";
import { MOCK_HISTORY, MOCK_PROJECTS } from "./lib/mockData";

const DEFAULT_PROGRESS = {
  is_running: false,
  current: 0,
  total: 0,
  current_project: "",
};

// Demo mode is a development tool. It used to be live in the published build and fired on
// ANY network error, so while PullPilot recreated its own container the user saw a panel
// full of invented projects. Vite resolves this at build time and drops everything behind
// it, mockData.js included, from the production bundle.
const MOCK_MODE_ALLOWED = import.meta.env.DEV;

/**
 * Pin the browser's UTC offset onto a `datetime-local` value.
 *
 * That input yields a bare wall-clock ("2026-08-01T03:00") with no zone, and the
 * scheduler read it in the *container's* timezone: pick 03:00 from a laptop two hours
 * ahead of the server and the task fired at 05:00. The offset makes both agree.
 */
function withLocalOffset(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const withSeconds = value.split(":").length === 2 ? `${value}:00` : value;
  // getTimezoneOffset() counts minutes *behind* UTC, so the sign is inverted.
  const minutes = -parsed.getTimezoneOffset();
  const sign = minutes >= 0 ? "+" : "-";
  const absolute = Math.abs(minutes);
  const hh = String(Math.floor(absolute / 60)).padStart(2, "0");
  const mm = String(absolute % 60).padStart(2, "0");
  return `${withSeconds}${sign}${hh}:${mm}`;
}

/** Maps the backend's stable `code` to an i18n key. */
const ERROR_KEYS = {
  invalid_credentials: "auth.invalid_credentials",
  invalid_current_password: "account.error_current_password",
  setup_already_completed: "setup.error_already_done",
  setup_disabled: "auth.generic_error",
  setup_required: "auth.generic_error",
  validation_error: "auth.validation_error",
};

function authErrorMessage(error, t) {
  if (isBackendUnreachableError(error)) {
    return t("auth.backend_unreachable");
  }
  if (error?.code === "rate_limited") {
    return t("auth.rate_limited", { seconds: error.retryAfter ?? 60 });
  }
  const key = ERROR_KEYS[error?.code];
  return key ? t(key) : t("auth.generic_error");
}

export default function App() {
  const { t, i18n } = useTranslation();

  const [projects, setProjects] = useState([]);
  const [history, setHistory] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [updatingProjects, setUpdatingProjects] = useState({});
  const [activeTab, setActiveTab] = useState("dashboard");
  const [selectedLog, setSelectedLog] = useState(null);
  const [isMockMode, setIsMockMode] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedFreq, setSelectedFreq] = useState("daily");
  const [progress, setProgress] = useState(DEFAULT_PROGRESS);
  // Without this the dashboard rendered `projects === []` while the very first scan was
  // still running, so the "no projects detected, check your STACKS_PATH" panel flashed on
  // every entry and told the user their setup was broken while the data was in flight.
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [pendingToggles, setPendingToggles] = useState({});
  const [confirmState, setConfirmState] = useState(null);

  // loading | setup | login | ready | offline. The SPA never redirects to authenticate:
  // it asks /api/auth/status and decides what to draw.
  const [authState, setAuthState] = useState("loading");
  const [authUsername, setAuthUsername] = useState(null);
  const [authError, setAuthError] = useState(null);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [retryingConnection, setRetryingConnection] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountError, setAccountError] = useState(null);
  const [accountSuccess, setAccountSuccess] = useState(false);

  const { startPolling, stopPolling } = usePolling();
  const { toasts, pushToast, dismissToast } = useToasts();

  // Read through a ref rather than closed over: `requestContext` and `t` both change
  // identity on a language switch, and the loaders below depend on them. One click on the
  // ES/EN pill used to tear down polling and re-run a full project scan — up to eight
  // `compose ps` subprocesses — plus /history and /schedules.
  const localeRef = useRef(normalizeUiLocale(i18n.language));

  useEffect(() => {
    const locale = normalizeUiLocale(i18n.language);
    localeRef.current = locale;
    // index.html hardcodes lang="es", so in English a screen reader applied Spanish
    // phonetics to the whole document.
    document.documentElement.lang = locale;
  }, [i18n.language]);

  const handleUnauthorized = useCallback(() => {
    stopPolling();
    setAuthUsername(null);
    setAuthState("login");
  }, [stopPolling]);

  const handleSetupRequired = useCallback(() => {
    stopPolling();
    setAuthUsername(null);
    setAuthState("setup");
  }, [stopPolling]);

  const requestContext = useMemo(
    () => ({
      onUnauthorized: handleUnauthorized,
      onSetupRequired: handleSetupRequired,
      // A getter, so the object identity stays stable across language switches while
      // every request still sends the current Accept-Language.
      get locale() {
        return localeRef.current;
      },
    }),
    [handleSetupRequired, handleUnauthorized]
  );

  // Newest response wins. loadProjects is called from the mount effect, from the poll on
  // the update-finished edge and from a manual update, so a slow earlier scan could land
  // last and clobber fresher data — including reverting an optimistic toggle.
  const projectsRequestId = useRef(0);

  const loadProjects = useCallback(async () => {
    const requestId = ++projectsRequestId.current;
    setProjectsLoading(true);
    try {
      const data = await fetchProjects(requestContext);
      if (requestId !== projectsRequestId.current) {
        return;
      }
      setProjects(data);
      setIsMockMode(false);
    } catch (error) {
      if (isAuthRedirectError(error) || requestId !== projectsRequestId.current) {
        return;
      }
      if (isBackendUnreachableError(error)) {
        if (MOCK_MODE_ALLOWED) {
          console.warn("Backend unreachable, loading mock data.", error);
          setProjects(MOCK_PROJECTS);
          setIsMockMode(true);
          return;
        }
        // Updating or down. A retry screen is honest; fake data is not.
        setAuthState("offline");
        return;
      }
      console.error("Error loading projects", error);
      setProjects([]);
      setIsMockMode(false);
      pushToast("alerts.projects_load_error");
    } finally {
      if (requestId === projectsRequestId.current) {
        setProjectsLoading(false);
      }
    }
  }, [pushToast, requestContext]);

  const loadHistory = useCallback(
    async (allowMockFallback = true) => {
      setHistoryLoading(true);
      try {
        const data = await fetchHistory(requestContext);
        setHistory(data);
      } catch (error) {
        if (isAuthRedirectError(error)) {
          return;
        }
        if (MOCK_MODE_ALLOWED && allowMockFallback && isBackendUnreachableError(error)) {
          setHistory(MOCK_HISTORY);
          return;
        }
        if (isBackendUnreachableError(error)) {
          setAuthState("offline");
          return;
        }
        console.error("Error loading history", error);
        setHistory([]);
        pushToast("alerts.history_load_error");
      } finally {
        setHistoryLoading(false);
      }
    },
    [pushToast, requestContext]
  );

  const loadSchedules = useCallback(async () => {
    if (isMockMode) {
      return;
    }
    try {
      const data = await fetchSchedules(requestContext);
      setSchedules(data);
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      console.error("Error fetching schedules", error);
      // Used to be console-only: the schedules tab silently showed a stale list.
      pushToast("alerts.schedules_load_error");
    }
  }, [isMockMode, pushToast, requestContext]);

  // Whether a global update was running last time we asked. Refreshing on every "not
  // running" answer meant the very first check, right after the mount had already
  // loaded everything, re-ran both loads: two full project scans (each up to eight
  // `compose ps` subprocesses) and two /history calls on every entry to the dashboard.
  const wasUpdatingRef = useRef(false);
  const accountCloseTimer = useRef(undefined);

  useEffect(() => () => clearTimeout(accountCloseTimer.current), []);

  const checkProgress = useCallback(async () => {
    try {
      const data = await fetchUpdateStatus(requestContext);
      if (data.is_running) {
        wasUpdatingRef.current = true;
        setProgress(data);
        startPolling(checkProgress, 1000);
        return;
      }

      stopPolling();
      setProgress(DEFAULT_PROGRESS);
      // Only on the running -> finished edge: that is when the data actually changed.
      if (wasUpdatingRef.current) {
        wasUpdatingRef.current = false;
        await loadProjects();
        await loadHistory(false);
      }
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      // The interval keeps firing regardless of what happens in here, so bailing out
      // without stopping it left the UI stuck: the progress bar never cleared, every card
      // stayed pointer-events-none and Update All stayed disabled, forever. That is
      // exactly the state PullPilot lands in while it updates its own container — the
      // case OfflineView exists for.
      stopPolling();
      setProgress(DEFAULT_PROGRESS);
      if (isBackendUnreachableError(error)) {
        wasUpdatingRef.current = true;
        setAuthState("offline");
        return;
      }
      console.error("Error checking progress", error);
      pushToast("alerts.progress_error");
    }
  }, [
    loadHistory,
    loadProjects,
    pushToast,
    requestContext,
    startPolling,
    stopPolling,
  ]);

  const bootstrap = useCallback(async () => {
    try {
      const status = await fetchAuthStatus({ locale: normalizeUiLocale(i18n.language) });
      setAuthUsername(status.username ?? null);
      if (!status.setup_complete) {
        setAuthState("setup");
        return;
      }
      setAuthState(status.authenticated ? "ready" : "login");
    } catch (error) {
      if (isBackendUnreachableError(error)) {
        if (MOCK_MODE_ALLOWED) {
          console.warn("Backend unreachable, loading mock data.", error);
          setIsMockMode(true);
          setAuthState("ready");
          return;
        }
        setAuthState("offline");
        return;
      }
      console.error("Error checking authentication status", error);
      setAuthState("login");
    }
    // i18n.language only feeds Accept-Language: no need to re-run bootstrap on a switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Stay on the offline card and spin its own button instead of flipping the whole
  // screen to the generic loader, which hid the retry the user just asked for.
  const handleRetryConnection = useCallback(async () => {
    setRetryingConnection(true);
    try {
      await bootstrap();
    } finally {
      setRetryingConnection(false);
    }
  }, [bootstrap]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    // No session, no data: these four calls used to fire always and 401 four times.
    if (authState !== "ready") {
      return undefined;
    }
    loadProjects();
    loadHistory();
    loadSchedules();
    checkProgress();
    return () => stopPolling();
  }, [authState, checkProgress, loadHistory, loadProjects, loadSchedules, stopPolling]);

  const handleLogout = async () => {
    try {
      await logout(requestContext);
    } catch (error) {
      console.error("Error logging out", error);
    }
    stopPolling();
    setProjects([]);
    setHistory([]);
    setSchedules([]);
    setProgress(DEFAULT_PROGRESS);
    setAuthUsername(null);
    setAuthError(null);
    setAuthState("login");
  };

  const handleSetupSubmit = async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const password = formData.get("password");
    const passwordConfirm = formData.get("password_confirm");

    if (password !== passwordConfirm) {
      setAuthError(t("setup.error_mismatch"));
      return;
    }

    setAuthSubmitting(true);
    setAuthError(null);
    try {
      const result = await setupCredentials(
        { username: formData.get("username"), password, password_confirm: passwordConfirm },
        requestContext
      );
      setAuthUsername(result.username);
      setAuthState("ready");
    } catch (error) {
      console.error("Error during initial setup", error);
      setAuthError(authErrorMessage(error, t));
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleLoginSubmit = async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);

    setAuthSubmitting(true);
    setAuthError(null);
    try {
      const result = await login(
        { username: formData.get("username"), password: formData.get("password") },
        requestContext
      );
      setAuthUsername(result.username);
      setAuthState("ready");
    } catch (error) {
      if (error?.code === "setup_required") {
        setAuthState("setup");
        setAuthError(null);
        return;
      }
      setAuthError(authErrorMessage(error, t));
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleChangeCredentials = async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const form = event.target;

    const newUsername = (formData.get("username") || "").trim();
    const newPassword = formData.get("new_password") || "";
    const newPasswordConfirm = formData.get("new_password_confirm") || "";

    if (newPassword && newPassword !== newPasswordConfirm) {
      setAccountError(t("account.error_mismatch"));
      return;
    }

    const payload = { current_password: formData.get("current_password") };
    if (newUsername && newUsername !== authUsername) {
      payload.username = newUsername;
    }
    if (newPassword) {
      payload.new_password = newPassword;
      payload.new_password_confirm = newPasswordConfirm;
    }
    if (!payload.username && !payload.new_password) {
      setAccountError(t("account.error_nothing_to_change"));
      return;
    }

    setAuthSubmitting(true);
    setAccountError(null);
    try {
      const result = await changeCredentials(payload, requestContext);
      setAuthUsername(result.username);
      setAccountSuccess(true);
      form.reset();
      // Kept in a ref and cleared on unmount: an uncancelled timer closed the dialog 2.5s
      // later even if the user had already cancelled and reopened it to change something
      // else, and set state on an unmounted component when the session expired meanwhile.
      clearTimeout(accountCloseTimer.current);
      accountCloseTimer.current = setTimeout(() => {
        setAccountOpen(false);
        setAccountSuccess(false);
      }, 2500);
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      console.error("Error changing credentials", error);
      setAccountError(authErrorMessage(error, t));
    } finally {
      setAuthSubmitting(false);
    }
  };

  // useCallback, not an inline arrow: both modals key their focus-trap effect on this
  // identity, and during a global update the app re-renders once a second.
  const handleCloseAccount = useCallback(() => {
    clearTimeout(accountCloseTimer.current);
    setAccountOpen(false);
    setAccountError(null);
    setAccountSuccess(false);
  }, []);

  const handleCloseLog = useCallback(() => setSelectedLog(null), []);

  const handleUpdateProject = async (name) => {
    setUpdatingProjects((prev) => ({ ...prev, [name]: true }));

    if (isMockMode) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    } else {
      try {
        await updateProject(name, requestContext);
        await loadProjects();
        pushToast("alerts.update_ok", "success", { name });
      } catch (error) {
        if (error?.status === 409) {
          pushToast("alerts.update_in_progress");
        } else if (!isAuthRedirectError(error)) {
          // "Error connecting to backend" was wrong here: the backend answered, the
          // update failed. Point at the history, which holds the logs that say why.
          pushToast(
            isBackendUnreachableError(error)
              ? "alerts.backend_error"
              : "alerts.update_failed",
            "error",
            { name }
          );
        }
      }
    }

    setUpdatingProjects((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const runUpdateAll = async () => {
    if (isMockMode) {
      pushToast("alerts.mock_global", "info");
      return;
    }

    try {
      await triggerUpdateAll(requestContext);
      // Marked here too, not only when a poll sees it running: a very short global
      // update could finish between this call and the first poll one second later.
      wasUpdatingRef.current = true;
      setProgress({
        is_running: true,
        current: 0,
        total: 1,
        current_project: t("status.starting"),
      });
      startPolling(checkProgress, 1000);
    } catch (error) {
      if (!isAuthRedirectError(error)) {
        pushToast("alerts.backend_error");
      }
    }
  };

  const handleUpdateAll = () => {
    const count = projects.filter((project) => !project.excluded).length;
    setConfirmState({
      titleKey: "confirm.update_all_title",
      messageKey: "confirm.update_all_message",
      options: { count },
      confirmKey: "confirm.update_all_action",
      onConfirm: runUpdateAll,
    });
  };

  const handleCreateSchedule = async (event) => {
    event.preventDefault();

    const formData = new FormData(event.target);
    const taskType = formData.get("task_type") || "cron";
    const target = formData.get("target");

    let payload;
    if (taskType === "date") {
      const dateIso = formData.get("date_iso");
      if (!dateIso || String(dateIso).trim() === "") {
        pushToast("alerts.schedule_error");
        return;
      }
      payload = {
        target,
        task_type: "date",
        frequency: "daily",
        date_iso: withLocalOffset(String(dateIso)),
      };
    } else {
      const hour = Number.parseInt(formData.get("hour"), 10);
      const minute = Number.parseInt(formData.get("minute"), 10);
      if (
        Number.isNaN(hour) ||
        Number.isNaN(minute) ||
        hour < 0 ||
        hour > 23 ||
        minute < 0 ||
        minute > 59
      ) {
        pushToast("alerts.schedule_error");
        return;
      }

      payload = {
        target,
        task_type: "cron",
        frequency: formData.get("frequency"),
        week_day: formData.get("week_day") || "*",
        day_of_month: formData.get("day_of_month") || "1",
        hour,
        minute,
      };
    }

    try {
      const created = await createSchedule(payload, requestContext);
      // The endpoint returns the created row, so appending it saves a full round trip.
      setSchedules((prev) => [...prev, created]);
      event.target.reset();
      setSelectedFreq("daily");
      pushToast("alerts.schedule_created", "success");
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      // The 422 detail explains *why* the trigger was rejected — a date already gone, a
      // weekly schedule with no day. Swallowing it left a flat "could not create".
      pushToast(
        error?.status === 422 ? "alerts.schedule_invalid" : "alerts.schedule_error",
        "error",
        { reason: error?.message ?? "" }
      );
    }
  };

  const runDeleteSchedule = async (id) => {
    try {
      await deleteSchedule(id, requestContext);
      await loadSchedules();
      pushToast("alerts.schedule_deleted", "success");
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      // It used to say "error creating schedule" — literally the wrong verb.
      pushToast(
        error?.status === 404 ? "alerts.schedule_already_gone" : "alerts.schedule_delete_error"
      );
      await loadSchedules();
    }
  };

  const handleDeleteSchedule = (id) => {
    const schedule = schedules.find((row) => row.id === id);
    setConfirmState({
      titleKey: "confirm.delete_schedule_title",
      messageKey: "confirm.delete_schedule_message",
      // Which one, rather than the anonymous "are you sure?" of the native dialog.
      details: schedule
        ? `${schedule.target} · ${formatExpression(schedule.expression, schedule.task_type)}`
        : undefined,
      confirmKey: "confirm.delete_schedule_action",
      onConfirm: () => runDeleteSchedule(id),
    });
  };

  const setSettingValue = (name, setting, value) =>
    setProjects((prev) =>
      prev.map((project) => {
        if (project.name !== name) {
          return project;
        }
        const field = setting === "exclude" ? "excluded" : "full_stop";
        return { ...project, [field]: value };
      })
    );

  const toggleSetting = async (name, setting) => {
    const key = `${name}:${setting}`;
    // Guarded, and the rollback restores a captured value instead of flipping again:
    // double-clicking sent two requests, and if the first failed the "flip back" inverted
    // whatever the second had just set, leaving the UI disagreeing with the server.
    if (pendingToggles[key]) {
      return;
    }

    const current = projects.find((project) => project.name === name);
    if (!current) {
      return;
    }
    const field = setting === "exclude" ? "excluded" : "full_stop";
    const previous = Boolean(current[field]);

    setSettingValue(name, setting, !previous);

    if (isMockMode) {
      return;
    }

    setPendingToggles((prev) => ({ ...prev, [key]: true }));
    try {
      // No reload afterwards: the optimistic flip already matches what the endpoint
      // stored, and re-scanning ran a `compose ps` per project to confirm one boolean.
      await toggleProjectSetting(name, setting, requestContext);
    } catch (error) {
      setSettingValue(name, setting, previous);
      if (!isAuthRedirectError(error)) {
        pushToast("alerts.config_error");
      }
    } finally {
      setPendingToggles((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const toggleLanguage = () => {
    // Normalise before comparing: the browser detector returns "es-ES", so the first
    // click after a clean load used to stay on Spanish.
    const newLang = normalizeUiLocale(i18n.language) === "es" ? "en" : "es";
    i18n.changeLanguage(newLang);
  };

  // Dates were formatted with the *browser's* locale, so setting the UI to English on a
  // Spanish machine still produced Spanish dates.
  const uiLocale = normalizeUiLocale(i18n.language);

  const formatExpression = (expression, taskType = "cron") => {
    if (!expression) {
      return "";
    }

    if (taskType === "date") {
      // Rendered in the reader's timezone. Rows created before the offset was pinned
      // carry none, so they still read as whatever clock the container was on.
      const parsed = new Date(expression.replace(" ", "T"));
      const at = Number.isNaN(parsed.getTime())
        ? expression
        : parsed.toLocaleString(uiLocale);
      return t("schedule.format.once", { at });
    }

    const parts = expression.split(" ");
    // Both padded: only the minute used to be, so 04:05 rendered as "4:05" while the form
    // the user filled in showed "04".
    const minute = (parts[0] || "0").padStart(2, "0");
    const hour = (parts[1] || "0").padStart(2, "0");
    const day = parts[2] || "*";
    const week = parts[4] || "*";

    if (day === "*" && week === "*") {
      return t("schedule.format.daily", { time: `${hour}:${minute}` });
    }
    if (week !== "*") {
      const translatedDay = t(`days.${week}`) !== `days.${week}` ? t(`days.${week}`) : week;
      return t("schedule.format.weekly", { day: translatedDay, time: `${hour}:${minute}` });
    }
    if (day !== "*") {
      return t("schedule.format.monthly", { day, time: `${hour}:${minute}` });
    }
    return expression;
  };

  if (authState === "loading") {
    return <AuthLayout t={t} i18n={i18n} onToggleLanguage={toggleLanguage} loading />;
  }

  if (authState === "offline") {
    return (
      <OfflineView
        t={t}
        i18n={i18n}
        onToggleLanguage={toggleLanguage}
        onRetry={handleRetryConnection}
        retrying={retryingConnection}
      />
    );
  }

  if (authState === "setup") {
    return (
      <SetupView
        t={t}
        i18n={i18n}
        onToggleLanguage={toggleLanguage}
        onSubmit={handleSetupSubmit}
        submitting={authSubmitting}
        error={authError}
      />
    );
  }

  if (authState === "login") {
    return (
      <LoginView
        t={t}
        i18n={i18n}
        onToggleLanguage={toggleLanguage}
        onSubmit={handleLoginSubmit}
        submitting={authSubmitting}
        error={authError}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans flex flex-col">
      <Header
        t={t}
        i18n={i18n}
        isMockMode={isMockMode}
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        // Demo mode has no backend to change anything against.
        onOpenAccount={isMockMode ? undefined : () => setAccountOpen(true)}
        onToggleLanguage={toggleLanguage}
        onLogout={handleLogout}
      />

      <ProgressBar t={t} progress={progress} />

      <main className="max-w-7xl mx-auto p-4 md:p-6 w-full flex-grow">
        {activeTab === "dashboard" && (
          <Dashboard
            t={t}
            projects={projects}
            projectsLoading={projectsLoading}
            progress={progress}
            updatingProjects={updatingProjects}
            onUpdateAll={handleUpdateAll}
            onUpdateProject={handleUpdateProject}
            onToggleSetting={toggleSetting}
          />
        )}

        {activeTab === "schedule" && (
          <ScheduleView
            t={t}
            selectedFreq={selectedFreq}
            onSelectedFreqChange={setSelectedFreq}
            onCreateSchedule={handleCreateSchedule}
            projects={projects}
            schedules={schedules}
            onDeleteSchedule={handleDeleteSchedule}
            formatExpression={formatExpression}
          />
        )}

        {activeTab === "history" && (
          <HistoryView
            t={t}
            history={history}
            historyLoading={historyLoading}
            locale={uiLocale}
            // Wrapped: passed bare, React handed the click event to `allowMockFallback`.
            onRefresh={() => loadHistory()}
            onSelectLog={setSelectedLog}
          />
        )}

        <LogModal
          t={t}
          selectedLog={selectedLog}
          onClose={handleCloseLog}
          onCopied={(_message, tone = "success") =>
            pushToast(tone === "success" ? "modal.copied" : "modal.copy_failed", tone)
          }
        />

        <AccountModal
          t={t}
          open={accountOpen}
          username={authUsername}
          onClose={handleCloseAccount}
          onSubmit={handleChangeCredentials}
          submitting={authSubmitting}
          error={accountError}
          success={accountSuccess}
        />

        <ConfirmDialog
          t={t}
          open={Boolean(confirmState)}
          title={confirmState ? t(confirmState.titleKey) : ""}
          message={confirmState ? t(confirmState.messageKey, confirmState.options) : ""}
          details={confirmState?.details}
          confirmLabel={confirmState ? t(confirmState.confirmKey) : ""}
          onCancel={() => setConfirmState(null)}
          onConfirm={() => {
            const action = confirmState?.onConfirm;
            setConfirmState(null);
            action?.();
          }}
        />
      </main>

      <Footer t={t} />
      <Toaster t={t} toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
