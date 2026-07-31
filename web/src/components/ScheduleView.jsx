import { useState } from "react";
import { Calendar, ChevronRight, Clock, Plus, Shield, Trash2 } from "lucide-react";

export default function ScheduleView({
  t,
  selectedFreq,
  onSelectedFreqChange,
  onCreateSchedule,
  projects,
  schedules,
  onDeleteSchedule,
  formatExpression,
}) {
  const [taskType, setTaskType] = useState("cron");

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2 pb-4 border-b border-slate-100">
          <Clock size={20} className="text-blue-600" /> {t("schedule.new_schedule")}
        </h2>
        <form
          onSubmit={onCreateSchedule}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-end"
        >
          <input type="hidden" name="task_type" value={taskType} />

          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
              {t("schedule.task_type")}
            </label>
            <div className="relative">
              <select
                value={taskType}
                onChange={(event) => setTaskType(event.target.value)}
                className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700"
              >
                <option value="cron">{t("schedule.type_cron")}</option>
                <option value="date">{t("schedule.type_once")}</option>
              </select>
              <ChevronRight
                className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
                size={16}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
              {t("schedule.target")}
            </label>
            <div className="relative">
              <select
                name="target"
                className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700"
              >
                <option value="GLOBAL">{t("schedule.target_global")}</option>
                {projects.map((project) => (
                  <option key={project.name} value={project.name}>
                    {project.name}
                  </option>
                ))}
              </select>
              <ChevronRight
                className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
                size={16}
              />
            </div>
          </div>

          {taskType === "cron" && (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                {t("schedule.frequency")}
              </label>
              <div className="relative">
                <select
                  name="frequency"
                  className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700"
                  onChange={(event) => onSelectedFreqChange(event.target.value)}
                  value={selectedFreq}
                >
                  <option value="daily">{t("schedule.freq_daily")}</option>
                  <option value="weekly">{t("schedule.freq_weekly")}</option>
                  <option value="monthly">{t("schedule.freq_monthly")}</option>
                </select>
                <ChevronRight
                  className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
                  size={16}
                />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "weekly" && (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                {t("schedule.day_week")}
              </label>
              <div className="relative">
                <select
                  name="week_day"
                  className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700"
                >
                  {["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => (
                    <option key={day} value={day}>
                      {t(`days.${day}`)}
                    </option>
                  ))}
                </select>
                <ChevronRight
                  className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
                  size={16}
                />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "monthly" && (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                {t("schedule.day_month")}
              </label>
              <div className="relative">
                <select
                  name="day_of_month"
                  className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700"
                >
                  {[...Array(28)].map((_, index) => (
                    <option key={index + 1} value={index + 1}>
                      {index + 1}
                    </option>
                  ))}
                </select>
                <ChevronRight
                  className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
                  size={16}
                />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "daily" && <div className="hidden lg:block" />}

          {taskType === "cron" && (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                {t("schedule.time")}
              </label>
              <div className="flex gap-2 items-center bg-slate-50 border border-slate-200 rounded-lg p-3">
                <input
                  type="number"
                  name="hour"
                  min="0"
                  max="23"
                  placeholder="04"
                  defaultValue="04"
                  required
                  className="bg-transparent w-full text-center text-sm font-medium focus:outline-none text-slate-700 placeholder-slate-300"
                />
                <span className="font-bold text-slate-300">:</span>
                <input
                  type="number"
                  name="minute"
                  min="0"
                  max="59"
                  placeholder="00"
                  defaultValue="00"
                  required
                  className="bg-transparent w-full text-center text-sm font-medium focus:outline-none text-slate-700 placeholder-slate-300"
                />
              </div>
              {/* Cron runs on the container clock (TZ), not the browser's. One-off tasks
                  carry the browser offset, so only this one needs saying. */}
              <span className="text-xs text-slate-400">{t("schedule.time_hint")}</span>
            </div>
          )}

          {taskType === "date" && (
            <div className="flex flex-col gap-2 lg:col-span-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">
                {t("schedule.datetime_once")}
              </label>
              <input
                type="datetime-local"
                name="date_iso"
                required
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 text-slate-700"
              />
            </div>
          )}

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 active:scale-95 text-white p-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-md h-[46px]"
          >
            <Plus size={18} /> {t("schedule.create_btn")}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
          <h3 className="font-bold text-slate-700">{t("schedule.active_tasks")}</h3>
          <span className="text-xs font-mono bg-white px-2 py-1 rounded border border-slate-200 text-slate-500">
            {t("schedule.tasks_count", { count: schedules.length })}
          </span>
        </div>
        {schedules.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center text-slate-400 gap-3">
            <Calendar size={48} className="text-slate-200" />
            <p className="italic">{t("schedule.no_tasks")}</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <tbody className="divide-y divide-slate-100">
              {schedules.map((schedule) => (
                <tr key={schedule.id} className="hover:bg-slate-50 group transition-colors">
                  <td className="p-4 font-bold text-slate-800">
                    {schedule.target === "GLOBAL" ? (
                      <span className="text-blue-600 flex items-center gap-2">
                        <Shield size={16} /> {t("schedule.target_global")}
                      </span>
                    ) : (
                      schedule.target
                    )}
                  </td>
                  <td className="p-4 font-mono text-slate-600 text-xs md:text-sm">
                    {formatExpression(schedule.expression, schedule.task_type)}
                  </td>
                  <td className="p-4 text-right">
                    <button
                      onClick={() => onDeleteSchedule(schedule.id)}
                      aria-label={t("schedule.delete_task")}
                      title={t("schedule.delete_task")}
                      className="text-slate-400 hover:text-red-600 p-2 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
