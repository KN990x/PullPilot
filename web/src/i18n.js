import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

const resources = {
  es: {
    translation: {
      app: {
        title: "PullPilot",
        subtitle: "Docker Homelab Updater",
        demo_mode: "DEMO",
        change_language: "Cambiar idioma",
      },
      nav: {
        dashboard: "Dashboard",
        schedule: "Programacion",
        history: "Historial",
      },
      auth: {
        logout: "Cerrar sesion",
      },
      status: {
        updating_homelab: "Actualizando Homelab...",
        processing: "Procesando",
        system_status: "Estado del Sistema",
        projects_detected: "{{count}} proyectos detectados.",
        active: "{{count}} activos.",
        update_all: "Actualizar Todo",
        update_project: "Actualizar proyecto",
        updating: "Actualizando...",
        updating_btn: "Actualizando...",
        starting: "Iniciando...",
        empty_projects_title: "No hay proyectos detectados",
        empty_projects_intro:
          "Lista de comprobación Docker Compose (si no ves proyectos):",
        empty_projects_path:
          "1) La carpeta de stacks debe existir en el host. Por defecto el compose usa /srv/docker-stacks; con .env opcional define DOCKER_ROOT_PATH si usas otra ruta.",
        empty_projects_compose:
          "2) Cada proyecto es una subcarpeta con docker-compose.yml o docker-compose.yaml.",
        empty_projects_volume:
          "3) El compose oficial monta esa ruta en host y contenedor (${DOCKER_ROOT_PATH:-/srv/docker-stacks}). Tras cambiar .env: docker compose up -d o restart.",
      },
      card: {
        containers: "Contenedores",
        full_stop: "Full Stop Update",
        exclude: "Excluir (Ignorar)",
      },
      schedule: {
        new_schedule: "Nueva Programacion",
        task_type: "Tipo",
        type_cron: "Recurrente (cron)",
        type_once: "Una sola vez",
        datetime_once: "Fecha y hora",
        target: "Objetivo",
        target_global: "Todo el Sistema (Global)",
        frequency: "Frecuencia",
        freq_daily: "Diaria",
        freq_weekly: "Semanal",
        freq_monthly: "Mensual",
        day_week: "Dia Semana",
        day_month: "Dia del Mes",
        time: "Hora (24h)",
        create_btn: "Crear Tarea",
        delete_task: "Eliminar tarea",
        active_tasks: "Tareas Activas",
        tasks_count: "{{count}} Tareas",
        no_tasks: "No hay tareas programadas.",
        format: {
          daily: "Diaria a las {{time}}",
          weekly: "Semanal ({{day}}) a las {{time}}",
          monthly: "Mensual (Dia {{day}}) a las {{time}}",
          once: "Una vez: {{at}}",
        },
      },
      history: {
        title: "Historial de Actualizaciones",
        refresh: "Actualizar historial",
        table_status: "Estado",
        table_date: "Fecha",
        table_summary: "Resumen",
        table_actions: "Acciones",
        status_success: "Exitoso",
        status_error: "Error",
        view_details: "Ver Detalles",
        no_logs: "No hay registros de actualizaciones aun.",
      },
      modal: {
        title: "Detalles del Log #{{id}}",
        close: "Cerrar",
      },
      alerts: {
        update_all_confirm: "Seguro que quieres actualizar TODO el homelab?",
        delete_schedule_confirm: "Eliminar programacion?",
        backend_error: "Error al conectar con el backend",
        mock_global: "(Simulacion) Proceso global iniciado en segundo plano.",
        schedule_error: "Error al crear programacion",
        config_error: "Error al guardar configuracion",
        projects_load_error: "El servidor respondio con error al cargar proyectos. Revisa el backend.",
        history_load_error: "No se pudo cargar el historial. Revisa el backend.",
      },
      days: {
        mon: "Lunes",
        tue: "Martes",
        wed: "Miercoles",
        thu: "Jueves",
        fri: "Viernes",
        sat: "Sabado",
        sun: "Domingo",
      },
      footer: {
        tip_me: "Invítame un café",
      },
      pwa: {
        update_available: "Nueva version disponible. Recargar?",
      },
    },
  },
  en: {
    translation: {
      app: {
        title: "PullPilot",
        subtitle: "Docker Homelab Updater",
        demo_mode: "DEMO",
        change_language: "Change language",
      },
      nav: {
        dashboard: "Dashboard",
        schedule: "Schedule",
        history: "History",
      },
      auth: {
        logout: "Logout",
      },
      status: {
        updating_homelab: "Updating Homelab...",
        processing: "Processing",
        system_status: "System Status",
        projects_detected: "{{count}} projects detected.",
        active: "{{count}} active.",
        update_all: "Update All",
        update_project: "Update project",
        updating: "Updating...",
        updating_btn: "Updating...",
        starting: "Starting...",
        empty_projects_title: "No projects detected",
        empty_projects_intro:
          "Docker Compose checklist (if the list is empty):",
        empty_projects_path:
          "1) The stacks folder must exist on the host. The default compose path is /srv/docker-stacks; add an optional .env with DOCKER_ROOT_PATH if you use another path.",
        empty_projects_compose:
          "2) Each project is a subfolder with docker-compose.yml or docker-compose.yaml.",
        empty_projects_volume:
          "3) The official compose bind-mounts that path on host and container (${DOCKER_ROOT_PATH:-/srv/docker-stacks}). After .env changes: docker compose up -d or restart.",
      },
      card: {
        containers: "Containers",
        full_stop: "Full Stop Update",
        exclude: "Exclude (Ignore)",
      },
      schedule: {
        new_schedule: "New Schedule",
        task_type: "Type",
        type_cron: "Recurring (cron)",
        type_once: "One-time",
        datetime_once: "Date and time",
        target: "Target",
        target_global: "Whole System (Global)",
        frequency: "Frequency",
        freq_daily: "Daily",
        freq_weekly: "Weekly",
        freq_monthly: "Monthly",
        day_week: "Day of Week",
        day_month: "Day of Month",
        time: "Time (24h)",
        create_btn: "Create Task",
        delete_task: "Delete task",
        active_tasks: "Active Tasks",
        tasks_count: "{{count}} Tasks",
        no_tasks: "No scheduled tasks.",
        format: {
          daily: "Daily at {{time}}",
          weekly: "Weekly ({{day}}) at {{time}}",
          monthly: "Monthly (Day {{day}}) at {{time}}",
          once: "Once: {{at}}",
        },
      },
      history: {
        title: "Update History",
        refresh: "Refresh history",
        table_status: "Status",
        table_date: "Date",
        table_summary: "Summary",
        table_actions: "Actions",
        status_success: "Success",
        status_error: "Error",
        view_details: "View Details",
        no_logs: "No update records yet.",
      },
      modal: {
        title: "Log Details #{{id}}",
        close: "Close",
      },
      alerts: {
        update_all_confirm: "Are you sure you want to update the ENTIRE homelab?",
        delete_schedule_confirm: "Delete schedule?",
        backend_error: "Error connecting to backend",
        mock_global: "(Simulation) Global process started in background.",
        schedule_error: "Error creating schedule",
        config_error: "Error saving configuration",
        projects_load_error: "The server returned an error while loading projects. Check the backend.",
        history_load_error: "Could not load history. Check the backend.",
      },
      days: {
        mon: "Monday",
        tue: "Tuesday",
        wed: "Wednesday",
        thu: "Thursday",
        fri: "Friday",
        sat: "Saturday",
        sun: "Sunday",
      },
      footer: {
        tip_me: "Buy me a coffee",
      },
      pwa: {
        update_available: "New version available. Reload?",
      },
    },
  },
};

i18n.use(LanguageDetector).use(initReactI18next).init({
  resources,
  fallbackLng: "es",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
