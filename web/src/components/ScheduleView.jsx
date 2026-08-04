import { useState } from "react";
import { Calendar, ChevronRight, Clock, Plus, Shield, Trash2 } from "lucide-react";

const LABEL_CLASS = "text-xs font-bold text-slate-600 uppercase tracking-wide";
const CONTROL_CLASS =
  "w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700";

function SelectChevron() {
  return (
    <ChevronRight
      className="absolute right-3 top-3 text-slate-400 rotate-90 pointer-events-none"
      size={16}
      aria-hidden="true"
    />
  );
}

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
          <Clock size={20} className="text-blue-600" aria-hidden="true" />{" "}
          {t("schedule.new_schedule")}
        </h2>
        {/* Every control carries an id and its label an htmlFor. Without them a screen
            reader announced seven unnamed comboboxes and spin buttons in a row; the two
            time inputs in particular shared one visual label that reached neither. */}
        <form
          onSubmit={onCreateSchedule}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-end"
        >
          <input type="hidden" name="task_type" value={taskType} />

          <div className="flex flex-col gap-2">
            <label htmlFor="schedule-task-type" className={LABEL_CLASS}>
              {t("schedule.task_type")}
            </label>
            <div className="relative">
              <select
                id="schedule-task-type"
                value={taskType}
                onChange={(event) => setTaskType(event.target.value)}
                className={CONTROL_CLASS}
              >
                <option value="cron">{t("schedule.type_cron")}</option>
                <option value="date">{t("schedule.type_once")}</option>
              </select>
              <SelectChevron />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="schedule-target" className={LABEL_CLASS}>
              {t("schedule.target")}
            </label>
            <div className="relative">
              <select id="schedule-target" name="target" className={CONTROL_CLASS}>
                <option value="GLOBAL">{t("schedule.target_global")}</option>
                {projects.map((project) => (
                  <option key={project.name} value={project.name}>
                    {project.name}
                  </option>
                ))}
              </select>
              <SelectChevron />
            </div>
          </div>

          {taskType === "cron" && (
            <div className="flex flex-col gap-2">
              <label htmlFor="schedule-frequency" className={LABEL_CLASS}>
                {t("schedule.frequency")}
              </label>
              <div className="relative">
                <select
                  id="schedule-frequency"
                  name="frequency"
                  className={CONTROL_CLASS}
                  onChange={(event) => onSelectedFreqChange(event.target.value)}
                  value={selectedFreq}
                >
                  <option value="daily">{t("schedule.freq_daily")}</option>
                  <option value="weekly">{t("schedule.freq_weekly")}</option>
                  <option value="monthly">{t("schedule.freq_monthly")}</option>
                </select>
                <SelectChevron />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "weekly" && (
            <div className="flex flex-col gap-2">
              <label htmlFor="schedule-week-day" className={LABEL_CLASS}>
                {t("schedule.day_week")}
              </label>
              <div className="relative">
                <select id="schedule-week-day" name="week_day" className={CONTROL_CLASS}>
                  {["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => (
                    <option key={day} value={day}>
                      {t(`days.${day}`)}
                    </option>
                  ))}
                </select>
                <SelectChevron />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "monthly" && (
            <div className="flex flex-col gap-2">
              <label htmlFor="schedule-day-of-month" className={LABEL_CLASS}>
                {t("schedule.day_month")}
              </label>
              <div className="relative">
                <select
                  id="schedule-day-of-month"
                  name="day_of_month"
                  className={CONTROL_CLASS}
                >
                  {[...Array(28)].map((_, index) => (
                    <option key={index + 1} value={index + 1}>
                      {index + 1}
                    </option>
                  ))}
                </select>
                <SelectChevron />
              </div>
            </div>
          )}

          {taskType === "cron" && selectedFreq === "daily" && <div className="hidden lg:block" />}

          {taskType === "cron" && (
            <fieldset className="flex flex-col gap-2 border-0 p-0 m-0">
              <legend className={`${LABEL_CLASS} p-0 mb-2`}>{t("schedule.time")}</legend>
              <div className="flex gap-2 items-center bg-slate-50 border border-slate-200 rounded-lg p-3">
                <label htmlFor="schedule-hour" className="sr-only">
                  {t("schedule.hour")}
                </label>
                <input
                  id="schedule-hour"
                  type="number"
                  name="hour"
                  min="0"
                  max="23"
                  placeholder="04"
                  defaultValue="04"
                  required
                  className="bg-transparent w-full text-center text-sm font-medium focus:outline-none text-slate-700 placeholder-slate-400"
                />
                <span className="font-bold text-slate-400" aria-hidden="true">
                  :
                </span>
                <label htmlFor="schedule-minute" className="sr-only">
                  {t("schedule.minute")}
                </label>
                <input
                  id="schedule-minute"
                  type="number"
                  name="minute"
                  min="0"
                  max="59"
                  placeholder="00"
                  defaultValue="00"
                  required
                  className="bg-transparent w-full text-center text-sm font-medium focus:outline-none text-slate-700 placeholder-slate-400"
                />
              </div>
              {/* Cron runs on the container clock (TZ), not the browser's. One-off tasks
                  carry the browser offset, so both cases now say which clock they use. */}
              <span className="text-xs text-slate-500">{t("schedule.time_hint")}</span>
            </fieldset>
          )}

          {taskType === "date" && (
            <div className="flex flex-col gap-2 lg:col-span-2">
              <label htmlFor="schedule-date-iso" className={LABEL_CLASS}>
                {t("schedule.datetime_once")}
              </label>
              <input
                id="schedule-date-iso"
                type="datetime-local"
                name="date_iso"
                required
                className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 text-slate-700"
              />
              <span className="text-xs text-slate-500">{t("schedule.date_hint")}</span>
            </div>
          )}

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 active:scale-95 text-white p-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-md h-[46px]"
          >
            <Plus size={18} aria-hidden="true" /> {t("schedule.create_btn")}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
          <h3 className="font-bold text-slate-700">{t("schedule.active_tasks")}</h3>
          <span className="text-xs font-mono bg-white px-2 py-1 rounded border border-slate-200 text-slate-600">
            {t("schedule.tasks_count", { count: schedules.length })}
          </span>
        </div>
        {schedules.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center text-slate-500 gap-3">
            <Calendar size={48} className="text-slate-300" aria-hidden="true" />
            <p className="italic">{t("schedule.no_tasks")}</p>
          </div>
        ) : (
          // Its own scroll container: the card is overflow-hidden, so on a phone a long
          // project name plus "Weekly (Wednesday) at 04:30" was clipped, not scrollable.
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-700 uppercase font-bold text-xs">
                <tr>
                  <th scope="col" className="p-4">
                    {t("schedule.table_target")}
                  </th>
                  <th scope="col" className="p-4">
                    {t("schedule.table_when")}
                  </th>
                  <th scope="col" className="p-4 text-right">
                    {t("schedule.table_actions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {schedules.map((schedule) => (
                  <tr key={schedule.id} className="hover:bg-slate-50 group transition-colors">
                    <td className="p-4 font-bold text-slate-800">
                      {schedule.target === "GLOBAL" ? (
                        <span className="text-blue-600 flex items-center gap-2 whitespace-nowrap">
                          <Shield size={16} aria-hidden="true" />{" "}
                          {t("schedule.target_global")}
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
                        type="button"
                        onClick={() => onDeleteSchedule(schedule.id)}
                        aria-label={t("schedule.delete_task_named", {
                          target: schedule.target,
                        })}
                        title={t("schedule.delete_task")}
                        className="text-slate-500 hover:text-red-600 p-2 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
