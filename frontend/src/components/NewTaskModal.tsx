"use client";

import { useState } from "react";
import { api, type Task } from "@/lib/api";
import { toLocalInputValue } from "@/lib/format";

export default function NewTaskModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (t: Task) => void;
}) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<Task["priority"]>("medium");
  const [deadline, setDeadline] = useState("");
  const [duration, setDuration] = useState(30);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const task = await api<Task>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          title,
          priority,
          deadline: deadline ? new Date(deadline).toISOString() : null,
          duration_minutes: duration,
          notes: notes || null,
        }),
      });
      onCreated(task);
      setTitle("");
      setNotes("");
      setDeadline("");
      setPriority("medium");
      setDuration(30);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create task");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Create task"
    >
      <form
        className="card w-full max-w-md p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h2 className="font-display text-xl">New task</h2>
        <div className="mt-4 space-y-3">
          <label className="block text-xs text-muted">
            Title
            <input
              className="input mt-1"
              required
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Finish investor deck"
              autoFocus
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-muted">
              Priority
              <select
                className="input mt-1"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Task["priority"])}
              >
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
            <label className="block text-xs text-muted">
              Duration (minutes)
              <input
                type="number"
                className="input mt-1"
                min={5}
                max={600}
                step={5}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="block text-xs text-muted">
            Deadline (optional)
            <input
              type="datetime-local"
              className="input mt-1"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </label>
          <label className="block text-xs text-muted">
            Notes (optional)
            <textarea
              className="input mt-1"
              rows={2}
              maxLength={2000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
        </div>
        {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || !title.trim()}>
            {saving ? "Saving…" : "Create task"}
          </button>
        </div>
      </form>
    </div>
  );
}
