import { CheckCircle, Loader2, RefreshCw, XCircle } from "lucide-react";

export default function HistoryView({
  t,
  history,
  historyLoading,
  appending,
  hasMore,
  onLoadMore,
  onRefresh,
  onSelectLog,
  locale,
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden animate-in fade-in slide-in-from-right-4 duration-300">
      <div className="p-6 border-b border-slate-200 flex justify-between items-center">
        <h2 className="text-lg font-bold text-slate-800">{t("history.title")}</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={historyLoading}
          aria-label={t("history.refresh")}
          title={t("history.refresh")}
          className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:hover:text-slate-500 disabled:hover:bg-transparent disabled:cursor-not-allowed"
        >
          <RefreshCw
            size={18}
            className={historyLoading ? "animate-spin" : ""}
            aria-hidden="true"
          />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="bg-slate-50 text-slate-700 uppercase font-bold text-xs">
            <tr>
              <th scope="col" className="px-6 py-4">
                {t("history.table_status")}
              </th>
              <th scope="col" className="px-6 py-4">
                {t("history.table_date")}
              </th>
              <th scope="col" className="px-6 py-4">
                {t("history.table_summary")}
              </th>
              <th scope="col" className="px-6 py-4">
                {t("history.table_actions")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {historyLoading ? (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-slate-500">
                  {/* Its own status message: this used to reuse the button's label,
                      "Refresh history", which reads as a command, not a state. */}
                  <span role="status" className="inline-flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                    {t("history.loading")}
                  </span>
                </td>
              </tr>
            ) : (
              <>
                {history.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4">
                      {log.status === "SUCCESS" ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 border border-green-200">
                          <CheckCircle size={14} aria-hidden="true" />{" "}
                          {t("history.status_success")}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 border border-red-200">
                          <XCircle size={14} aria-hidden="true" />{" "}
                          {t("history.status_error")}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 font-mono text-slate-500 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString(locale)}
                    </td>
                    <td className="px-6 py-4">
                      {/* The truncation lives on a block inside the cell: `max-width` on
                          a <td> in an auto-layout table is ignored, so a long summary
                          used to blow the row out instead of being clipped. */}
                      <span
                        className="block max-w-md truncate"
                        title={log.summary}
                      >
                        {log.summary}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <button
                        type="button"
                        onClick={() => onSelectLog(log)}
                        className="text-blue-600 hover:text-blue-800 font-medium hover:underline whitespace-nowrap"
                      >
                        {t("history.view_details")}
                      </button>
                    </td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-slate-500 italic">
                      {t("history.no_logs")}
                    </td>
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
      {history.length > 0 && (
        // The server keeps HISTORY_RETENTION rows and has always accepted limit/offset;
        // without this the newest 20 were the only ones anybody could reach.
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between gap-4">
          <p className="text-xs text-slate-500">
            {t("history.showing_latest", { count: history.length })}
          </p>
          {hasMore && (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={appending}
              className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed whitespace-nowrap"
            >
              {appending ? t("history.loading") : t("history.load_more")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
