"use client";

import type { Progress } from "@/lib/api";

const items = (p: Progress) => [
  { label: "Completion", value: `${p.completion_rate}%`, sub: `${p.done}/${p.total_tasks} tasks done` },
  { label: "Done today", value: String(p.done_today), sub: `${p.due_today} due today` },
  { label: "Open", value: String(p.todo), sub: "tasks to do" },
  { label: "Overdue", value: String(p.overdue), sub: p.overdue > 0 ? "replan suggested" : "all on track" },
  { label: "Scheduled", value: `${p.hours_scheduled_this_week}h`, sub: "this week" },
];

export default function StatsStrip({ progress }: { progress: Progress | null }) {
  return (
    <section aria-label="Progress statistics" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {progress === null
        ? Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card h-[86px] animate-pulse bg-cream/60" />
          ))
        : items(progress).map((s) => (
            <div key={s.label} className="card px-4 py-3">
              <p className="label-caps">{s.label}</p>
              <p
                className={`font-display mt-1 text-2xl leading-none ${
                  s.label === "Overdue" && progress.overdue > 0 ? "text-danger" : ""
                }`}
              >
                {s.value}
              </p>
              {s.label === "Completion" && (
                <div
                  className="mt-2 h-1 w-full overflow-hidden rounded-full bg-cream"
                  role="progressbar"
                  aria-valuenow={progress.completion_rate}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-accent transition-all duration-500"
                    style={{ width: `${progress.completion_rate}%` }}
                  />
                </div>
              )}
              <p className="mt-1 text-xs text-muted">{s.sub}</p>
            </div>
          ))}
    </section>
  );
}
