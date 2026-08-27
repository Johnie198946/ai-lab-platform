import { CalendarOff } from "lucide-react";
import { buildScheduleRows } from "./quantumProjection";

const day = 86400000;

export function ProjectSchedule({ schedule, focusTaskId }) {
  const rows = buildScheduleRows(schedule);
  const scheduled = rows.filter((row) => row.start && row.finish);
  const start = scheduled.length ? Math.min(...scheduled.map((row) => Date.parse(row.start))) : null;
  const finish = scheduled.length ? Math.max(...scheduled.map((row) => Date.parse(row.finish))) : null;
  const span = start !== null && finish !== null ? Math.max(finish - start + day, day) : null;
  const stages = new Map((schedule.stages ?? []).map((stage) => [stage.id, stage.name]));

  return (
    <section className="qw-schedule">
      <div className="qw-schedule-head"><div><span className="qw-eyebrow">Read-only schedule</span><h2>项目甘特</h2></div><div className="qw-calendar-status"><CalendarOff size={16} />{schedule.calendar?.status === "UNCONNECTED" ? "工作日历未连接" : schedule.calendar?.timezone}</div></div>
      <div className="qw-schedule-table">
        <div className="qw-schedule-row header"><span>任务</span><span>负责人</span><span>时间轴</span></div>
        {rows.map((row) => {
          const positioned = row.start && row.finish && span;
          const left = positioned ? ((Date.parse(row.start) - start) / span) * 100 : 0;
          const width = positioned ? Math.max(((Date.parse(row.finish) - Date.parse(row.start) + day) / span) * 100, 2) : 0;
          return (
            <div className={`qw-schedule-row ${focusTaskId === row.id ? "focused" : ""}`} key={row.id}>
              <span><strong>{row.title}</strong><small>{stages.get(row.stage_id)}</small></span>
              <span>{row.assignee_id || row.assignee_role || "待分配"}</span>
              <span className="qw-timeline-cell">{positioned ? <><i style={{ left: `${left}%`, width: `${width}%` }} /><small>{row.start.slice(0, 10)} → {row.finish.slice(0, 10)}</small></> : <em>待排期 · {row.unscheduled_reason || "missing_planned_dates"}</em>}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
