"use client";

import { useState } from "react";
import type { Task } from "@/lib/api";
import { fmtDeadlineRelative, fmtDay, fmtTime, toLocalInputValue } from "@/lib/format";

const priorityStyle: Record<Task["priority"], string> = {
  high: "border-danger/40 text-danger",
  medium: "border-warn/40 text-warn",
  low: "border-line text-muted",
};

function TaskRow({
  task,
  onComplete,
  onDelete,
  onReschedule,
  busy,
}: {
  task: Task;
  onComplete: (t: Task) => void;
  onDelete: (t: Task) => void;
  onReschedule: (t: Task, newStart: string, newDeadline: string | null) => void;
  busy: boolean;
}) {
  const [reschedOpen, setReschedOpen] = useState(false);
  const [start, setStart] = useState(() => {
    const d = new Date();
    d.setMinutes(0, 0, 0);
    d.setHours(d.getHours() + 1);
    return toLocalInputValue(d);
  });
  const [deadline, setDeadline] = useState(() =>
    task.deadline ? toLocalInputValue(new Date(task.deadline)) : ""
  );
  const overdue = task.deadline && new Date(task.deadline) < new Date() && task.status === "todo";

  return (
    <li className="border-b border-line transition-colors last:border-b-0 hover:bg-cream/30">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          className={`h-5 w-5 shrink-0 rounded-full border text-[11px] leading-none ${
            task.status === "done"
              ? "border-good bg-good text-white"
              : "border-muted/50 hover:border-accent hover:bg-accent/10"
          }`}
          title={task.status === "done" ? "Completed" : "Mark complete"}
          disabled={busy || task.status === "done"}
          onClick={() => onComplete(task)}
        >
          {task.status === "done" ? "✓" : ""}
        </button>
        <div className="min-w-0 flex-1">
          <p
            className={`truncate text-sm font-medium ${
              task.status === "done" ? "text-muted line-through" : ""
            }`}
            title={task.notes ?? task.title}
          >
            {task.title}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
            <span className={`rounded-sm border px-1 py-px ${priorityStyle[task.priority]}`}>
              {task.priority}
            </span>
            <span>{task.duration_minutes} min</span>
            {task.deadline && (
              <span className={overdue ? "font-semibold text-danger" : ""}>
                due {fmtDay(task.deadline)} {fmtTime(task.deadline)}
                {overdue && ` · ${fmtDeadlineRelative(task.deadline)}`}
              </span>
            )}
            {task.status === "missed" && (
              <span className="font-semibold text-warn">missed</span>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            className="btn"
            disabled={busy || task.status === "done"}
            onClick={() => setReschedOpen((v) => !v)}
          >
            Reschedule
          </button>
          <button className="btn btn-danger" disabled={busy} onClick={() => onDelete(task)}>
            Delete
          </button>
        </div>
      </div>
      {reschedOpen && (
        <div className="flex flex-wrap items-end gap-3 border-t border-line bg-cream/40 px-4 py-3">
          <label className="text-xs text-muted">
            Work block starts
            <input
              type="datetime-local"
              className="input mt-1"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label className="text-xs text-muted">
            Deadline (optional)
            <input
              type="datetime-local"
              className="input mt-1"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => {
                onReschedule(task, start, deadline || null);
                setReschedOpen(false);
              }}
            >
              Save
            </button>
            <button className="btn" onClick={() => setReschedOpen(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

export default function TaskList({
  title,
  subtitle,
  tasks,
  emptyText,
  onComplete,
  onDelete,
  onReschedule,
  busy,
}: {
  title: string;
  subtitle?: string;
  tasks: Task[];
  emptyText: string;
  onComplete: (t: Task) => void;
  onDelete: (t: Task) => void;
  onReschedule: (t: Task, newStart: string, newDeadline: string | null) => void;
  busy: boolean;
}) {
  const [filter, setFilter] = useState<Task["priority"] | "all">("all");
  const counts: Record<Task["priority"] | "all", number> = {
    all: tasks.length,
    high: tasks.filter((t) => t.priority === "high").length,
    medium: tasks.filter((t) => t.priority === "medium").length,
    low: tasks.filter((t) => t.priority === "low").length,
  };
  const visible = filter === "all" ? tasks : tasks.filter((t) => t.priority === filter);

  return (
    <section className="card">
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="font-display text-lg">{title}</h2>
        {subtitle && <span className="text-xs text-muted">{subtitle}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-4 py-2">
        {(["all", "high", "medium", "low"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
              filter === f
                ? "border-ink bg-ink text-paper"
                : "border-line text-ink-soft hover:border-accent hover:text-accent"
            }`}
          >
            {f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)} · {counts[f]}
          </button>
        ))}
      </div>
      {visible.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted">
          {tasks.length > 0 ? `No ${filter} priority tasks here.` : emptyText}
        </p>
      ) : (
        <ul>
          {visible.map((t) => (
            <TaskRow
              key={t.id}
              task={t}
              onComplete={onComplete}
              onDelete={onDelete}
              onReschedule={onReschedule}
              busy={busy}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
