import { AlertTriangle, FileText, Loader2, Power, RefreshCw } from "lucide-react";

export default function ProjectCard({
  project,
  t,
  isUpdatingThis,
  isGlobalUpdate,
  currentProject,
  onUpdateProject,
  onToggleSetting,
}) {
  const isLocked = isGlobalUpdate || isUpdatingThis;

  // `key` used to sit here too, where it means nothing: it only matters on the element a
  // list render produces, which Dashboard already does.
  return (
    <div
      // No `pointer-events-none`: every control inside is already `disabled`, and the
      // blanket rule also took away selecting the stack name and reading the tooltips —
      // on every card, for as long as any global update ran.
      className={`bg-white rounded-xl border shadow-sm transition-all duration-200
        ${project.excluded ? "opacity-60 border-slate-200 bg-slate-50" : "border-slate-200"}
        ${isLocked ? "opacity-60 grayscale-[0.5]" : "hover:shadow-md"}
      `}
    >
      <div className="p-5 border-b border-slate-100 flex justify-between items-start">
        <div>
          <h3 className="font-bold text-lg text-slate-800 break-all">{project.name}</h3>
          {(isGlobalUpdate && currentProject === project.name) || isUpdatingThis ? (
            <span className="text-xs text-blue-600 flex items-center gap-1 mt-1 animate-pulse font-bold">
              <Loader2 size={12} className="animate-spin" aria-hidden="true" />{" "}
              {t("status.updating")}
            </span>
          ) : (
            <div className="flex items-center gap-2 mt-1">
              {/* `stopped` is slate, not red: a stack you took down on purpose and one
                  whose status could not be read are different things, and the dot is what
                  gets scanned first. Red is reserved for the one that needs looking at. */}
              <span
                aria-hidden="true"
                className={`w-2 h-2 rounded-full ${
                  project.status === "running"
                    ? "bg-green-500"
                    : project.status === "partial"
                      ? "bg-yellow-500"
                      : project.status === "stopped"
                        ? "bg-slate-400"
                        : "bg-red-500"
                }`}
              />
              {/* Translated, and at slate-600: the raw backend literal meant a Spanish
                  user read "RUNNING", and slate-400 on white is ~2.6:1 for what is the
                  card's primary datum. */}
              <span className="text-xs uppercase font-bold text-slate-600 tracking-wider">
                {t(`status.state_${project.status}`, { defaultValue: project.status })}
              </span>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onUpdateProject(project.name)}
            disabled={isUpdatingThis || project.excluded || isGlobalUpdate}
            title={t("card.update_project_named", { name: project.name })}
            aria-label={t("card.update_project_named", { name: project.name })}
            className="p-2 text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <RefreshCw
              size={18}
              className={isUpdatingThis ? "animate-spin" : ""}
              aria-hidden="true"
            />
          </button>
        </div>
      </div>

      <div className="p-5 space-y-4">
        <div className="flex justify-between items-center text-sm">
          <span className="text-slate-500 flex items-center gap-2">
            <FileText size={16} aria-hidden="true" /> {t("card.containers")}
          </span>
          <span className="font-mono font-medium bg-slate-100 px-2 py-0.5 rounded text-slate-700">
            {project.containers}
          </span>
        </div>

        <div className="pt-4 border-t border-slate-100 space-y-3">
          <label className="flex items-center justify-between gap-3 cursor-pointer group">
            <span className="text-sm text-slate-600 group-hover:text-slate-900 flex items-center gap-2 min-w-0">
              <Power size={16} className="shrink-0" aria-hidden="true" />{" "}
              <span className="min-w-0">{t("card.full_stop")}</span>
            </span>
            <div className="relative inline-flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={project.full_stop}
                onChange={() => onToggleSetting(project.name, "fullstop")}
                disabled={isLocked}
              />
              <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
            </div>
          </label>

          <label className="flex items-center justify-between gap-3 cursor-pointer group">
            <span className="text-sm text-slate-600 group-hover:text-slate-900 flex items-center gap-2 min-w-0">
              <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />{" "}
              <span className="min-w-0">{t("card.exclude")}</span>
            </span>
            <div className="relative inline-flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={project.excluded}
                onChange={() => onToggleSetting(project.name, "exclude")}
                disabled={isLocked}
              />
              <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-red-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-red-500" />
            </div>
          </label>
        </div>
      </div>
    </div>
  );
}
