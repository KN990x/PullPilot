import { Loader2 } from "lucide-react";

export default function ProgressBar({ t, progress }) {
  const percent =
    progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

  if (!progress.is_running) {
    return null;
  }

  return (
    // Stays visible during a long update by riding inside App's sticky block, rather than
    // pinning itself to the same offset as the header and covering it.
    <div className="bg-blue-600 text-white px-4 md:px-6 py-3 shadow-md transition-all duration-300">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="flex items-center gap-3 w-full md:w-auto">
          <Loader2 className="animate-spin" size={20} aria-hidden="true" />
          <div className="flex flex-col">
            <span className="font-bold text-sm">{t("status.updating_homelab")}</span>
            {/* aria-live: which project is being updated is the one thing that changes
                during a long run, and non-visual users had no way to hear it. blue-200
                on blue-600 is ~4:1, below AA for this size. */}
            <span className="text-xs text-blue-100" aria-live="polite">
              {t("status.processing")}:{" "}
              <span className="font-mono font-bold text-white">{progress.current_project}</span>
            </span>
          </div>
        </div>

        <div className="w-full md:w-1/2 flex items-center gap-3">
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("status.update_progress")}
            className="w-full bg-blue-800/50 rounded-full h-2.5 overflow-hidden"
          >
            <div
              className="bg-white h-2.5 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="text-xs font-bold min-w-[3rem]">{percent}%</span>
          <span className="text-xs text-blue-100 whitespace-nowrap">
            ({progress.current}/{progress.total})
          </span>
        </div>
      </div>
    </div>
  );
}
