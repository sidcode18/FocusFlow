"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import StatsStrip from "@/components/StatsStrip";
import TaskList from "@/components/TaskList";
import WeekCalendar from "@/components/WeekCalendar";
import AssistantPanel from "@/components/AssistantPanel";
import NewTaskModal from "@/components/NewTaskModal";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  api,
  ApiError,
  type Block,
  type Progress,
  type ReplanResponse,
  type ScheduleResponse,
  type Task,
} from "@/lib/api";
import { fmtDay, fmtTime } from "@/lib/format";

interface Notice {
  kind: "info" | "error";
  text: string;
}

export default function Page() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busyTask, setBusyTask] = useState<string | null>(null);
  const [replanBusy, setReplanBusy] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [confirmReplan, setConfirmReplan] = useState(false);
  const [confirmGenerate, setConfirmGenerate] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [t, s, p] = await Promise.all([
        api<Task[]>("/api/tasks"),
        api<{ blocks: Block[] }>("/api/schedule?days=7"),
        api<Progress>("/api/progress"),
      ]);
      setTasks(t);
      setBlocks(s.blocks);
      setProgress(p);
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof Error ? e.message : "Failed to load data",
      });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const overdueCount = progress?.overdue ?? 0;

  async function completeTask(t: Task) {
    setBusyTask(t.id);
    setNotice(null);
    try {
      await api<Task>(`/api/tasks/${t.id}/complete`, { method: "POST" });
      await refresh();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusyTask(null);
    }
  }

  async function deleteTask(t: Task) {
    setBusyTask(t.id);
    setNotice(null);
    try {
      await api(`/api/tasks/${t.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      await refresh();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusyTask(null);
    }
  }

  async function rescheduleTask(t: Task, newStart: string, newDeadline: string | null) {
    setBusyTask(t.id);
    setNotice(null);
    try {
      const res = await api<{ task: Task; changes: string[] }>(
        `/api/tasks/${t.id}/reschedule`,
        {
          method: "POST",
          body: JSON.stringify({
            new_start: newStart ? new Date(newStart).toISOString() : null,
            new_deadline: newDeadline ? new Date(newDeadline).toISOString() : null,
          }),
        }
      );
      setNotice({
        kind: "info",
        text: `Rescheduled “${res.task.title}”. ${res.changes.join("; ")}.`,
      });
      await refresh();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusyTask(null);
    }
  }

  async function generateSchedule() {
    setGenBusy(true);
    setNotice(null);
    try {
      const res = await api<ScheduleResponse>("/api/schedule/generate", { method: "POST" });
      setConfirmGenerate(false);
      setNotice({
        kind: "info",
        text:
          res.scheduled_count === 0
            ? "Nothing to schedule — no open tasks, or no free slots in the work window."
            : `Generated schedule (${res.scheduled_count} block${res.scheduled_count === 1 ? "" : "s"}):\n` +
              res.explanations.map((x) => `• ${x}`).join("\n"),
      });
      await refresh();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
      setConfirmGenerate(false);
    } finally {
      setGenBusy(false);
    }
  }

  async function replan() {
    setReplanBusy(true);
    setNotice(null);
    try {
      const res = await api<ReplanResponse>("/api/schedule/replan", { method: "POST", body: "{}" });
      setConfirmReplan(false);
      setNotice({
        kind: "info",
        text:
          res.missed_count === 0
            ? "No missed tasks found — everything with a deadline is still on track."
            : `Replanned ${res.missed_count} missed task${res.missed_count === 1 ? "" : "s"}:\n` +
              [...res.changes, ...res.explanations].map((x) => `• ${x}`).join("\n"),
      });
      await refresh();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
      setConfirmReplan(false);
    } finally {
      setReplanBusy(false);
    }
  }

  const now = new Date();
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 59, 999);

  const open = (tasks ?? []).filter((t) => t.status !== "done");
  const todayTasks = open
    .filter((t) => !t.deadline || new Date(t.deadline) <= endOfToday)
    .sort((a, b) => {
      const ao = a.deadline && new Date(a.deadline) < now ? 0 : 1;
      const bo = b.deadline && new Date(b.deadline) < now ? 0 : 1;
      if (ao !== bo) return ao - bo;
      if (a.status === "missed" !== (b.status === "missed"))
        return a.status === "missed" ? -1 : 1;
      return (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999");
    });
  const upcoming = open
    .filter((t) => t.deadline && new Date(t.deadline) > endOfToday)
    .sort((a, b) => (a.deadline ?? "").localeCompare(b.deadline ?? ""));

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <Header onNewTask={() => setNewTaskOpen(true)} />

      {notice && (
        <div
          className={`card flex items-start justify-between gap-3 px-4 py-3 text-sm ${
            notice.kind === "error"
              ? "border-danger/40 bg-[#f7ecec] text-danger"
              : "border-line bg-cream/60 text-ink-soft"
          }`}
        >
          <p className="whitespace-pre-wrap">{notice.text}</p>
          <button className="btn shrink-0" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}

      <StatsStrip progress={progress} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn"
              onClick={() => setConfirmReplan(true)}
              disabled={replanBusy}
              title="Find tasks that missed their deadlines, extend them, and rebuild the schedule"
            >
              {replanBusy ? "Replanning…" : `Replan missed${overdueCount ? ` (${overdueCount})` : ""}`}
            </button>
            <button className="btn" onClick={() => setConfirmGenerate(true)} disabled={genBusy}>
              {genBusy ? "Scheduling…" : "Generate schedule"}
            </button>
            <button className="btn" onClick={() => refresh()}>
              Refresh
            </button>
          </div>

          {tasks === null ? (
            <>
              <div className="card h-40 animate-pulse bg-cream/60" />
              <div className="card h-40 animate-pulse bg-cream/60" />
            </>
          ) : (
            <>
              <TaskList
                title="Today"
                subtitle={`${todayTasks.length} open · ${progress?.done_today ?? 0} done today`}
                tasks={todayTasks}
                emptyText="Nothing due today. Ask the assistant to add a task, or create one manually."
                onComplete={completeTask}
                onDelete={setDeleteTarget}
                onReschedule={rescheduleTask}
                busy={busyTask !== null}
              />
              <TaskList
                title="Upcoming deadlines"
                subtitle={`${upcoming.length} scheduled later`}
                tasks={upcoming}
                emptyText="No future deadlines yet."
                onComplete={completeTask}
                onDelete={setDeleteTarget}
                onReschedule={rescheduleTask}
                busy={busyTask !== null}
              />
            </>
          )}
        </div>

        <div className="lg:col-span-2">
          <AssistantPanel onMutated={refresh} />
        </div>
      </div>

      <WeekCalendar blocks={blocks ?? []} />

      <NewTaskModal open={newTaskOpen} onClose={() => setNewTaskOpen(false)} onCreated={refresh} />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete task?"
        body={
          deleteTarget
            ? `“${deleteTarget.title}” and its schedule blocks will be permanently removed.`
            : ""
        }
        confirmLabel="Delete"
        danger
        busy={busyTask === deleteTarget?.id}
        onConfirm={() => deleteTarget && deleteTask(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={confirmReplan}
        title="Replan missed tasks?"
        body={
          overdueCount > 0
            ? `${overdueCount} task${overdueCount === 1 ? "" : "s"} past its deadline will get a new deadline (next workday, 18:00) and a fresh schedule slot. Every change will be explained.`
            : "No tasks are currently overdue. Replan would do nothing — run it anyway?"
        }
        confirmLabel="Replan"
        busy={replanBusy}
        onConfirm={replan}
        onCancel={() => setConfirmReplan(false)}
      />

      <ConfirmDialog
        open={confirmGenerate}
        title="Regenerate the schedule?"
        body={`Future work blocks will be recomputed for all open tasks (deadlines first, then priority). Existing future blocks are replaced. Time now: ${fmtDay(
          now.toISOString()
        )} ${fmtTime(now.toISOString())}.`}
        confirmLabel="Generate"
        busy={genBusy}
        onConfirm={generateSchedule}
        onCancel={() => setConfirmGenerate(false)}
      />
    </main>
  );
}
