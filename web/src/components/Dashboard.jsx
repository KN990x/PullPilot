import { FolderOpen, Loader2, RefreshCw } from "lucide-react";

import ProjectCard from "./ProjectCard";

function ProjectCardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4 animate-pulse">
      <div className="h-5 w-2/3 rounded bg-slate-200" />
      <div className="h-3 w-1/3 rounded bg-slate-100" />
      <div className="pt-4 border-t border-slate-100 space-y-3">
        <div className="h-4 w-full rounded bg-slate-100" />
        <div className="h-4 w-full rounded bg-slate-100" />
      </div>
    </div>
  );
}

export default function Dashboard({
  t,
  projects,
  projectsLoading,
  projectsLoadFailed,
  progress,
  updatingProjects,
  onRefresh,
  onUpdateAll,
  onUpdateProject,
  onToggleSetting,
}) {
  // What "Update All" will actually do. Disabling only on an empty list meant that with
  // everything excluded the dialog asked to confirm updating zero projects.
  const updatableCount = projects.filter((project) => !project.excluded).length;
  // Skeletons, not the empty state: rendering the "no projects detected, check your
  // STACKS_PATH" panel while the first scan is in flight told the user their setup was
  // broken every single time they opened the dashboard.
  if (projectsLoading && projects.length === 0) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-[104px] rounded-xl border border-blue-100 bg-blue-50 animate-pulse" />
        <p role="status" className="sr-only">
          {t("status.loading_projects")}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[0, 1, 2].map((index) => (
            <ProjectCardSkeleton key={index} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-300">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-blue-50 p-4 md:p-6 rounded-xl border border-blue-100 gap-4">
        <div>
          <h2 className="text-lg font-semibold text-blue-900">{t("status.system_status")}</h2>
          <p className="text-blue-700 text-sm mt-1">
            {t("status.projects_detected", { count: projects.length })}{" "}
            {t("status.active", { count: projects.filter((p) => p.status === "running").length })}
          </p>
        </div>
        <div className="flex w-full md:w-auto items-center gap-2">
          {/* The dashboard had no way to refresh: projects were loaded on mount and after
              an update, so a stack that died outside PullPilot stayed green until a full
              page reload. The history tab has had this button all along. */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={projectsLoading || progress.is_running}
            aria-label={t("status.refresh_projects")}
            title={t("status.refresh_projects")}
            className="shrink-0 p-3 text-blue-700 bg-white border border-blue-200 hover:bg-blue-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw
              size={20}
              className={projectsLoading ? "animate-spin" : ""}
              aria-hidden="true"
            />
          </button>
          <button
            type="button"
            onClick={onUpdateAll}
            disabled={progress.is_running || updatableCount === 0}
            className="flex-1 md:flex-none flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg shadow-md transition-all active:scale-95 font-medium disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {progress.is_running ? (
              <Loader2 size={20} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={20} aria-hidden="true" />
            )}
            {progress.is_running ? t("status.updating") : t("status.update_all")}
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div
          className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-950 shadow-sm"
          role="status"
        >
          <div className="flex gap-3">
            <FolderOpen className="h-8 w-8 shrink-0 text-amber-700" aria-hidden="true" />
            <div className="min-w-0 space-y-3">
              {projectsLoadFailed ? (
                <>
                  <h3 className="font-semibold text-amber-900">
                    {t("status.projects_unavailable_title")}
                  </h3>
                  <p className="text-sm text-amber-900/90">
                    {t("status.projects_unavailable_intro")}
                  </p>
                </>
              ) : (
                <>
                  <h3 className="font-semibold text-amber-900">{t("status.empty_projects_title")}</h3>
                  <p className="text-sm text-amber-900/90">{t("status.empty_projects_intro")}</p>
                  <ul className="list-disc space-y-2 pl-5 text-sm text-amber-900/85">
                    <li>{t("status.empty_projects_path")}</li>
                    <li>{t("status.empty_projects_compose")}</li>
                    <li>{t("status.empty_projects_volume")}</li>
                  </ul>
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <ProjectCard
              key={project.name}
              project={project}
              t={t}
              isUpdatingThis={Boolean(updatingProjects[project.name])}
              isGlobalUpdate={progress.is_running}
              currentProject={progress.current_project}
              onUpdateProject={onUpdateProject}
              onToggleSetting={onToggleSetting}
            />
          ))}
        </div>
      )}
    </div>
  );
}
