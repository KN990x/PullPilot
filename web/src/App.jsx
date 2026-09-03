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
  isTimeoutError,
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

// Matches the endpoint's own default. The backend keeps HISTORY_RETENTION (200) rows and
// has always accepted limit/offset; the UI just never asked for a second page.
const HISTORY_PAGE_SIZE = 20;
// After a 202, a snapshot that still omits the name may just be a poll that left
// before `mark_running`. Five empty ticks (~5 s) is long enough to wait that out and
// short enough to release the card if the backend restarted and never recorded it.
const EMPTY_POLLS_BEFORE_EXPIRE = 5;

/** The set of in-flight project names, in the shape ProjectCard reads. */
function mapFromNames(names) {
  return Object.fromEntries([...names].map((name) => [name, true]));
}

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
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyAppending, setHistoryAppending] = useState(false);
  const [selectedFreq, setSelectedFreq] = useState("daily");
  const [creatingSchedule, setCreatingSchedule] = useState(false);
  const [progress, setProgress] = useState(DEFAULT_PROGRESS);
  // Without this the dashboard rendered `projects === []` while the very first scan was
  // still running, so the "no projects detected, check your STACKS_PATH" panel flashed on
  // every entry and told the user their setup was broken while the data was in flight.
  const [projectsLoading, setProjectsLoading] = useState(true);
  // Distinct from an empty scan: a 500 with `projects === []` used to draw the
  // STACKS_PATH checklist and tell the user their mount was broken.
  const [projectsLoadFailed, setProjectsLoadFailed] = useState(false);
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
  const accountCloseTimer = useRef(undefined);
  // Whether a global update was running last time we asked. Refreshing on every "not
  // running" answer meant the very first check, right after the mount had already
  // loaded everything, re-ran both loads.
  const wasUpdatingRef = useRef(false);
  // Which projects this tab asked to update and has not yet seen resolve. See the note in
  // checkProgress for why this is a ref and not just the state above.
  const updatingProjectsRef = useRef(new Set());
  // Names whose POST has returned 202. Until then an overlapping poll that omits the
  // name is not "expired" — the backend has not been asked yet.
  const acknowledgedRef = useRef(new Set());
  const seenRunningRef = useRef(new Set());
  const emptyPollsRef = useRef(new Map());
  const historyBusyRef = useRef(null);
  const historyOffsetRef = useRef(0);
  const historyRequestId = useRef(0);
  const projectsRequestId = useRef(0);

  useEffect(() => {
    const locale = normalizeUiLocale(i18n.language);
    localeRef.current = locale;
    // index.html hardcodes lang="es", so in English a screen reader applied Spanish
    // phonetics to the whole document.
    document.documentElement.lang = locale;
  }, [i18n.language]);

  const resetSessionUi = useCallback(() => {
    stopPolling();
    updatingProjectsRef.current.clear();
    acknowledgedRef.current.clear();
    seenRunningRef.current.clear();
    emptyPollsRef.current.clear();
    wasUpdatingRef.current = false;
    historyOffsetRef.current = 0;
    historyBusyRef.current = null;
    clearTimeout(accountCloseTimer.current);
    setUpdatingProjects({});
    setProjects([]);
    setHistory([]);
    setSchedules([]);
    setProgress(DEFAULT_PROGRESS);
    setProjectsLoading(true);
    setProjectsLoadFailed(false);
    setHistoryLoading(false);
    setHistoryAppending(false);
    setHistoryHasMore(false);
    setAccountOpen(false);
    setAccountError(null);
    setAccountSuccess(false);
    setConfirmState(null);
    setSelectedLog(null);
    setAuthUsername(null);
    setAuthError(null);
  }, [stopPolling]);

  const handleUnauthorized = useCallback(() => {
    resetSessionUi();
    setAuthState("login");
  }, [resetSessionUi]);

  const handleSetupRequired = useCallback(() => {
    resetSessionUi();
    setAuthState("setup");
  }, [resetSessionUi]);

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
  const loadProjects = useCallback(async () => {
    const requestId = ++projectsRequestId.current;
    setProjectsLoading(true);
    try {
      const data = await fetchProjects(requestContext);
      if (requestId !== projectsRequestId.current) {
        return;
      }
      setProjects(data);
      setProjectsLoadFailed(false);
      setIsMockMode(false);
    } catch (error) {
      if (isAuthRedirectError(error) || requestId !== projectsRequestId.current) {
        return;
      }
      // A slow scan (Pi, many stacks) aborts at 30 s while uvicorn is still working.
      // Treating that like a dead backend drew OfflineView over a live dashboard.
      if (isTimeoutError(error)) {
        setProjectsLoadFailed(true);
        pushToast("alerts.projects_load_error");
        return;
      }
      if (isBackendUnreachableError(error)) {
        if (MOCK_MODE_ALLOWED) {
          console.warn("Backend unreachable, loading mock data.", error);
          setProjects(MOCK_PROJECTS);
          setProjectsLoadFailed(false);
          setIsMockMode(true);
          return;
        }
        // Updating or down. A retry screen is honest; fake data is not.
        setAuthState("offline");
        return;
      }
      console.error("Error loading projects", error);
      // Keep whatever was on screen: wiping to [] painted the STACKS_PATH checklist
      // over a 500, which is the opposite of what happened.
      setProjectsLoadFailed(true);
      setIsMockMode(false);
      pushToast("alerts.projects_load_error");
    } finally {
      if (requestId === projectsRequestId.current) {
        setProjectsLoading(false);
      }
    }
  }, [pushToast, requestContext]);

  const loadHistory = useCallback(
    async (allowMockFallback = true, { append = false } = {}) => {
      // A "load more" during a refresh used to raise `historyAppending` while the
      // refresh's finally never cleared `historyLoading`, leaving the table spinning.
      if (append && historyBusyRef.current === "refresh") {
        return;
      }
      const requestId = ++historyRequestId.current;
      historyBusyRef.current = append ? "append" : "refresh";
      // Appending must not raise `historyLoading`: that swaps the whole table body for a
      // spinner, so asking for page 2 would blank the rows the user is reading.
      if (append) {
        setHistoryAppending(true);
      } else {
        setHistoryLoading(true);
      }
      try {
        const offset = append ? historyOffsetRef.current : 0;
        const data = await fetchHistory(requestContext, {
          limit: HISTORY_PAGE_SIZE,
          offset,
        });
        if (requestId !== historyRequestId.current) {
          return;
        }
        // A short page is the end of the table: the endpoint caps `limit` at
        // HISTORY_RETENTION, so there is no other signal that there is nothing more.
        setHistoryHasMore(data.length === HISTORY_PAGE_SIZE);
        historyOffsetRef.current = offset + data.length;
        setHistory((prev) => (append ? [...prev, ...data] : data));
      } catch (error) {
        if (isAuthRedirectError(error) || requestId !== historyRequestId.current) {
          return;
        }
        if (MOCK_MODE_ALLOWED && allowMockFallback && isBackendUnreachableError(error)) {
          setHistory(MOCK_HISTORY);
          setHistoryHasMore(false);
          return;
        }
        if (isTimeoutError(error)) {
          pushToast("alerts.history_load_error");
          return;
        }
        if (isBackendUnreachableError(error)) {
          setAuthState("offline");
          return;
        }
        console.error("Error loading history", error);
        // Only the first page is cleared: wiping the table because page 3 failed would
        // throw away what the user is already reading.
        if (!append) {
          setHistory([]);
          setHistoryHasMore(false);
        }
        pushToast("alerts.history_load_error");
      } finally {
        // The winner clears both flags: a superseded call must not leave its sibling
        // stuck true after it returns without touching it.
        if (requestId === historyRequestId.current) {
          historyBusyRef.current = null;
          setHistoryLoading(false);
          setHistoryAppending(false);
        }
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

  useEffect(() => () => clearTimeout(accountCloseTimer.current), []);

  const checkProgress = useCallback(async () => {
    const forgetTrackedUpdate = (name) => {
      updatingProjectsRef.current.delete(name);
      acknowledgedRef.current.delete(name);
      seenRunningRef.current.delete(name);
      emptyPollsRef.current.delete(name);
    };

    try {
      const data = await fetchUpdateStatus(requestContext);

      // Per-project deploys run in the background too now, so the same poll reports both.
      // Anything this tab started and that has since resolved gets its toast here.
      //
      // Read off the ref, not off `updatingProjects`: a state updater runs when React
      // decides to, and under StrictMode it runs twice, so deciding "this one finished,
      // toast it" in there would fire duplicate toasts and read stale values on the line
      // after. The ref is the source of truth; the state exists to render from.
      const projectStates = data.projects ?? {};
      let someProjectRunning = false;
      let resolvedSilently = false;
      const settled = [];
      for (const name of [...updatingProjectsRef.current]) {
        const state = projectStates[name];
        if (state === "running") {
          someProjectRunning = true;
          seenRunningRef.current.add(name);
          emptyPollsRef.current.delete(name);
          continue;
        }
        if (state === "success" || state === "error") {
          settled.push({ name, success: state === "success" });
          forgetTrackedUpdate(name);
          continue;
        }
        // Undefined used to count as settled ("expired / backend restarted"). A poll
        // already in flight when the click added the name saw exactly that and released
        // the card while the POST had not even reached `mark_running`.
        if (!acknowledgedRef.current.has(name)) {
          continue;
        }
        if (seenRunningRef.current.has(name)) {
          resolvedSilently = true;
          forgetTrackedUpdate(name);
          continue;
        }
        const misses = (emptyPollsRef.current.get(name) ?? 0) + 1;
        emptyPollsRef.current.set(name, misses);
        if (misses >= EMPTY_POLLS_BEFORE_EXPIRE) {
          resolvedSilently = true;
          forgetTrackedUpdate(name);
        }
      }
      const anyResolved = settled.length > 0 || resolvedSilently;
      if (anyResolved) {
        setUpdatingProjects(mapFromNames(updatingProjectsRef.current));
      }

      for (const { name, success } of settled) {
        pushToast(
          success ? "alerts.update_ok" : "alerts.update_failed",
          success ? "success" : "error",
          { name }
        );
      }
      if (anyResolved) {
        await loadProjects();
        // The history row is written by the same background task, so a per-project update
        // refreshes it too. It used to be written and never shown until a manual refresh.
        await loadHistory(false);
      }

      if (data.is_running) {
        wasUpdatingRef.current = true;
        setProgress(data);
        startPolling(checkProgress, 1000);
        return;
      }

      setProgress(DEFAULT_PROGRESS);
      // Keep polling while any single-project deploy is still going: stopping on
      // `!is_running` alone would abandon them halfway. Names still in the set (POST
      // in flight, or waiting for the first snapshot) count too.
      if (someProjectRunning || updatingProjectsRef.current.size > 0) {
        startPolling(checkProgress, 1000);
        return;
      }

      stopPolling();
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
    resetSessionUi();
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

  // Same reason as the two above: an inline cancel re-ran the focus trap on every
  // progress tick, which jumped focus back to Cancelar and recaptured the restore target.
  const handleCloseConfirm = useCallback(() => setConfirmState(null), []);

  /**
   * Asks for the deploy and returns; the outcome arrives through checkProgress.
   *
   * It used to await the whole thing, which meant one open request for as long as the
   * deploy took — minutes — with nothing on screen but a spinner.
   */
  const handleUpdateProject = async (name) => {
    if (isMockMode) {
      setUpdatingProjects((prev) => ({ ...prev, [name]: true }));
      await new Promise((resolve) => setTimeout(resolve, 1500));
      setUpdatingProjects((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      return;
    }

    if (updatingProjectsRef.current.has(name)) {
      return;
    }
    updatingProjectsRef.current.add(name);
    setUpdatingProjects(mapFromNames(updatingProjectsRef.current));

    try {
      await updateProject(name, requestContext);
      // 202 in hand: the deploy is running server-side and the poll owns it from here.
      acknowledgedRef.current.add(name);
      startPolling(checkProgress, 1000);
    } catch (error) {
      updatingProjectsRef.current.delete(name);
      acknowledgedRef.current.delete(name);
      seenRunningRef.current.delete(name);
      emptyPollsRef.current.delete(name);
      setUpdatingProjects(mapFromNames(updatingProjectsRef.current));
      if (error?.status === 409) {
        pushToast("alerts.update_in_progress");
      } else if (!isAuthRedirectError(error)) {
        // "Error connecting to backend" was wrong here: the backend answered and refused
        // to start. A deploy that starts and then fails is reported by checkProgress.
        pushToast(
          isBackendUnreachableError(error)
            ? "alerts.backend_error"
            : "alerts.update_failed",
          "error",
          { name }
        );
      }
    }
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
      if (isAuthRedirectError(error)) {
        return;
      }
      // 409 means another run already holds the global lock. Starting the polling here
      // would draw a progress bar for a run this click never launched.
      if (error?.status === 409) {
        pushToast("alerts.update_all_in_progress");
      } else {
        pushToast(
          isBackendUnreachableError(error)
            ? "alerts.backend_error"
            : "alerts.update_all_failed"
        );
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

    if (creatingSchedule) {
      return;
    }
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

    // Captured before the first await: `event.target` is nulled out once React recycles
    // the synthetic event, and the reset below needs the form either way.
    const form = event.target;
    setCreatingSchedule(true);
    try {
      const created = await createSchedule(payload, requestContext);
      // The endpoint returns the created row, so appending it saves a full round trip.
      setSchedules((prev) => [...prev, created]);
      form.reset();
      setSelectedFreq("daily");
      pushToast("alerts.schedule_created", "success");
    } catch (error) {
      if (isAuthRedirectError(error)) {
        return;
      }
      // Each rejection says something different and actionable: a date already gone, a
      // target that no longer exists, one the user excluded, or a schedule they already
      // have. A flat "could not create" for all four sends them guessing.
      const byStatus = {
        404: "alerts.schedule_rejected",
        409: "alerts.schedule_rejected",
        422: "alerts.schedule_invalid",
      };
      pushToast(byStatus[error?.status] ?? "alerts.schedule_error", "error", {
        reason: error?.message ?? "",
      });
      // The target vanished or changed under the tab: reload so the picker and the
      // warnings in the table agree with the server again.
      if (error?.status === 404 || error?.status === 409) {
        loadProjects();
      }
    } finally {
      // In a finally: the auth-redirect branch above returns early, and leaving the flag
      // set would disable the submit button for good.
      setCreatingSchedule(false);
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
    <div className="min-h-dvh bg-slate-50 text-slate-900 font-sans flex flex-col">
      {/* One sticky block, not three. Header, its mobile tab bar and the progress bar are
          siblings in this flex column, and each carried its own `sticky top-0`: they all
          pinned to the same offset and overlapped, so on a phone the tab bar rode over the
          header and during a global update the progress bar covered both. */}
      <div className="sticky top-0 z-30">
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
      </div>

      <main className="max-w-7xl mx-auto p-4 md:p-6 w-full flex-grow">
        {activeTab === "dashboard" && (
          <Dashboard
            t={t}
            projects={projects}
            projectsLoading={projectsLoading}
            projectsLoadFailed={projectsLoadFailed}
            progress={progress}
            updatingProjects={updatingProjects}
            onRefresh={loadProjects}
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
            creating={creatingSchedule}
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
            appending={historyAppending}
            hasMore={historyHasMore}
            locale={uiLocale}
            // Wrapped: passed bare, React handed the click event to `allowMockFallback`.
            onRefresh={() => loadHistory()}
            onLoadMore={() => loadHistory(false, { append: true })}
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
          onCancel={handleCloseConfirm}
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
