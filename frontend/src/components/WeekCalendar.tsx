"use client";

import { useState } from "react";
import type { Block } from "@/lib/api";
import { fmtMonthDay, fmtTime, fmtWeekdayShort, isSameDay } from "@/lib/format";

const DAY_COUNT = 7;

function startOfWeek(d: Date): Date {
  const monday = new Date(d);
  monday.setDate(d.getDate() - d.getDay());
  monday.setHours(0, 0, 0, 0);
  return monday;
}

const priorityColor: Record<string, string> = {
  high: "bg-[#f6e8e4] border-l-[3px] border-l-danger text-[#7c3322]",
  medium: "bg-[#f6efe2] border-l-[3px] border-l-warn text-[#6e4a20]",
  low: "bg-cream border-l-[3px] border-l-muted text-ink-soft",
};

export default function WeekCalendar({ blocks }: { blocks: Block[] }) {
  const [weekOffset, setWeekOffset] = useState(0);
  const now = new Date();
  const anchor = new Date(now);
  anchor.setDate(anchor.getDate() + weekOffset * 7);
  const monday = startOfWeek(anchor);
  const days = Array.from({ length: DAY_COUNT }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
  const sunday = days[days.length - 1];

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="font-display text-lg">
          {weekOffset === 0 ? "This week" : "Week"}
        </h2>
        <span className="text-xs text-muted">
          {fmtMonthDay(monday)} – {fmtMonthDay(sunday)} · {blocks.length} block
          {blocks.length === 1 ? "" : "s"}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            className="btn !px-2"
            onClick={() => setWeekOffset((o) => o - 1)}
            title="Previous week"
            aria-label="Previous week"
          >
            ‹
          </button>
          <button
            className="btn !px-2"
            onClick={() => setWeekOffset(0)}
            disabled={weekOffset === 0}
          >
            Today
          </button>
          <button
            className="btn !px-2"
            onClick={() => setWeekOffset((o) => o + 1)}
            title="Next week"
            aria-label="Next week"
          >
            ›
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 divide-y divide-line sm:grid-cols-7 sm:divide-x sm:divide-y-0">
        {days.map((day) => {
          const dayBlocks = blocks
            .filter((b) => isSameDay(new Date(b.start_time), day))
            .sort((a, b) => a.start_time.localeCompare(b.start_time));
          const isToday = weekOffset === 0 && isSameDay(day, now);
          return (
            <div
              key={day.toISOString()}
              className={`min-h-[160px] px-2.5 py-2.5 ${isToday ? "bg-cream/40" : ""}`}
            >
              <p
                className={`label-caps flex items-baseline justify-between ${
                  isToday ? "!text-accent" : ""
                }`}
              >
                {fmtWeekdayShort(day)}
                <span className={`text-xs font-medium ${isToday ? "text-accent" : "text-muted"}`}>
                  {day.getMonth() + 1}/{day.getDate()}
                </span>
              </p>
              <div className="mt-2 space-y-1.5">
                {dayBlocks.length === 0 ? (
                  <p className="pt-3 text-xs text-muted/70">Nothing scheduled</p>
                ) : (
                  dayBlocks.map((b) => (
                    <div
                      key={b.id}
                      title={`${b.task_title}\n${fmtTime(b.start_time)}–${fmtTime(b.end_time)}${
                        b.reason ? `\n${b.reason}` : ""
                      }`}
                      className={`rounded-sm px-1.5 py-1 text-[11px] leading-tight ${
                        priorityColor[b.task_priority] ?? priorityColor.low
                      }`}
                    >
                      <span className="font-semibold">{fmtTime(b.start_time)}</span>
                      <span className="block truncate">{b.task_title}</span>
                      {b.kind === "replan" && (
                        <span className="text-[10px] italic opacity-75">replanned</span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
