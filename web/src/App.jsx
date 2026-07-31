import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import AccountModal from "./components/AccountModal";
import AuthLayout from "./components/AuthLayout";
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
import { usePolling } from "./hooks/usePolling";
import {
  changeCredentials,
  createSchedule,
  deleteSchedule,
  fetchAuthStatus,
  fetchHistory,
  fetchProjects,
  fetchSchedules,
  fetchUpdateStatus,
  isBackendUnreachableError,
  login,
  logout,
  normalizeUiLocale,
  SESSION_EXPIRED_ERROR,
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

// El modo demo es una herramienta de desarrollo: permite ver la interfaz sin levantar el
// backend. En la build publicada estaba activo y saltaba ante CUALQUIER fallo de red, así
// que mientras PullPilot recreaba su propio contenedor el usuario veía un panel lleno de
// proyectos inventados. Vite evalúa esto en tiempo de compilación y elimina del bundle de
// producción todo lo que cuelga de la condición, mockData.js incluido.
const MOCK_MODE_ALLOWED = import.meta.env.DEV;

/** Traduce el `code` estable del backend a una clave de i18n. */
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

  // loading | setup | login | ready. La SPA ya no redirige al servidor para autenticar:
  // consulta /api/auth/status y decide qué pintar.
  const [authState, setAuthState] = useState("loading");
  const [authUsername, setAuthUsername] = useState(null);
  const [authError, setAuthError] = useState(null);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountError, setAccountError] = useState(null);
  const [accountSuccess, setAccountSuccess] = useState(false);

  const { startPolling, stopPolling } = usePolling();

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
      locale: normalizeUiLocale(i18n.language),
    }),
    [handleSetupRequired, handleUnauthorized, i18n.language]
  );

  const loadProjects = useCallback(async () => {
    try {
      const data = await fetchProjects(requestContext);
      setProjects(data);
      setIsMockMode(false);
    } catch (error) {
      if (error.message === SESSION_EXPIRED_ERROR) {
        return;
      }
      if (isBackendUnreachableError(error)) {
        if (MOCK_MODE_ALLOWED) {
          console.warn("Backend no detectado. Cargando datos de prueba (mock mode).", error);
          setProjects(MOCK_PROJECTS);
          setIsMockMode(true);
          return;
        }
        // Se está actualizando o se ha caído: la pantalla de "sin conexión" con reintento
        // es honesta; datos falsos, no.
        setAuthState("offline");
        return;
      }
      console.error("Error cargando proyectos", error);
      setProjects([]);
      setIsMockMode(false);
      alert(t("alerts.projects_load_error"));
    }
  }, [requestContext, t]);

  const loadHistory = useCallback(
    async (allowMockFallback = true) => {
      setHistoryLoading(true);
      try {
        const data = await fetchHistory(requestContext);
        setHistory(data);
      } catch (error) {
        if (error.message === SESSION_EXPIRED_ERROR) {
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
        console.error("Error cargando historial", error);
        setHistory([]);
        alert(t("alerts.history_load_error"));
      } finally {
        setHistoryLoading(false);
      }
    },
    [requestContext, t]
  );

  const loadSchedules = useCallback(async () => {
    if (isMockMode) {
      return;
    }
    try {
      const data = await fetchSchedules(requestContext);
      setSchedules(data);
    } catch (error) {
      if (error.message !== SESSION_EXPIRED_ERROR) {
        console.error("Error fetching schedules", error);
      }
    }
  }, [isMockMode, requestContext]);

  const checkProgress = useCallback(async () => {
    try {
      const data = await fetchUpdateStatus(requestContext);
      if (data.is_running) {
        setProgress(data);
        startPolling(checkProgress, 1000);
      } else {
        stopPolling();
        setProgress(DEFAULT_PROGRESS);
        await loadProjects();
        await loadHistory(false);
      }
    } catch (error) {
      if (error.message !== SESSION_EXPIRED_ERROR) {
        console.error("Error checking progress", error);
      }
    }
  }, [loadHistory, loadProjects, requestContext, startPolling, stopPolling]);

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
          console.warn("Backend no detectado. Cargando datos de prueba (mock mode).", error);
          setIsMockMode(true);
          setAuthState("ready");
          return;
        }
        setAuthState("offline");
        return;
      }
      console.error("Error consultando el estado de autenticación", error);
      setAuthState("login");
    }
    // i18n.language solo alimenta la cabecera Accept-Language; no hace falta re-ejecutar
    // el bootstrap al cambiar de idioma.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRetryConnection = useCallback(async () => {
    setAuthState("loading");
    await bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    // Sin sesión no se piden datos: antes las cuatro llamadas salían siempre y las
    // cuatro respondían 401.
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
      console.error("Error en la configuración inicial", error);
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
      setTimeout(() => {
        setAccountOpen(false);
        setAccountSuccess(false);
      }, 2500);
    } catch (error) {
      console.error("Error cambiando las credenciales", error);
      setAccountError(authErrorMessage(error, t));
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleCloseAccount = () => {
    setAccountOpen(false);
    setAccountError(null);
    setAccountSuccess(false);
  };

  const handleUpdateProject = async (name) => {
    setUpdatingProjects((prev) => ({ ...prev, [name]: true }));

    if (isMockMode) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    } else {
      try {
        await updateProject(name, requestContext);
        await loadProjects();
      } catch (error) {
        if (error?.status === 409) {
          alert(t("alerts.update_in_progress"));
        } else if (error.message !== SESSION_EXPIRED_ERROR) {
          alert(t("alerts.backend_error"));
        }
      }
    }

    setUpdatingProjects((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const handleUpdateAll = async () => {
    if (!confirm(t("alerts.update_all_confirm"))) {
      return;
    }

    if (isMockMode) {
      alert(t("alerts.mock_global"));
      return;
    }

    try {
      await triggerUpdateAll(requestContext);
      setProgress({
        is_running: true,
        current: 0,
        total: 1,
        current_project: t("status.starting"),
      });
      startPolling(checkProgress, 1000);
    } catch (error) {
      if (error.message !== SESSION_EXPIRED_ERROR) {
        alert(t("alerts.backend_error"));
      }
    }
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
        alert(t("alerts.schedule_error"));
        return;
      }
      payload = {
        target,
        task_type: "date",
        frequency: "daily",
        date_iso: dateIso,
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
        alert(t("alerts.schedule_error"));
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
      await createSchedule(payload, requestContext);
      await loadSchedules();
      event.target.reset();
      setSelectedFreq("daily");
    } catch (error) {
      if (error.message !== SESSION_EXPIRED_ERROR) {
        alert(t("alerts.schedule_error"));
      }
    }
  };

  const handleDeleteSchedule = async (id) => {
    if (!confirm(t("alerts.delete_schedule_confirm"))) {
      return;
    }
    try {
      await deleteSchedule(id, requestContext);
      await loadSchedules();
    } catch (error) {
      if (error.message !== SESSION_EXPIRED_ERROR) {
        alert(t("alerts.schedule_error"));
      }
    }
  };

  const toggleSetting = async (name, setting) => {
    setProjects((prev) =>
      prev.map((project) => {
        if (project.name !== name) {
          return project;
        }
        if (setting === "exclude") {
          return { ...project, excluded: !project.excluded };
        }
        if (setting === "fullstop") {
          return { ...project, full_stop: !project.full_stop };
        }
        return project;
      })
    );

    if (isMockMode) {
      return;
    }

    try {
      await toggleProjectSetting(name, setting, requestContext);
      await loadProjects();
    } catch (error) {
      setProjects((prev) =>
        prev.map((project) => {
          if (project.name !== name) {
            return project;
          }
          if (setting === "exclude") {
            return { ...project, excluded: !project.excluded };
          }
          if (setting === "fullstop") {
            return { ...project, full_stop: !project.full_stop };
          }
          return project;
        })
      );
      if (error.message !== SESSION_EXPIRED_ERROR) {
        alert(t("alerts.config_error"));
      }
    }
  };

  const toggleLanguage = () => {
    // Normalizar antes de comparar: el detector del navegador devuelve "es-ES", que no
    // es igual a "es", así que la primera pulsacion tras una carga limpia se quedaba en
    // castellano en lugar de pasar a ingles.
    const newLang = normalizeUiLocale(i18n.language) === "es" ? "en" : "es";
    i18n.changeLanguage(newLang);
  };

  const formatExpression = (expression, taskType = "cron") => {
    if (!expression) {
      return "";
    }

    if (taskType === "date") {
      return t("schedule.format.once", { at: expression });
    }

    const parts = expression.split(" ");
    const minute = (parts[0] || "0").padStart(2, "0");
    const hour = parts[1] || "0";
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
        // En modo demo no hay backend contra el que cambiar nada.
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
            onRefresh={loadHistory}
            onSelectLog={setSelectedLog}
          />
        )}

        <LogModal t={t} selectedLog={selectedLog} onClose={() => setSelectedLog(null)} />

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
      </main>

      <Footer t={t} />
    </div>
  );
}
