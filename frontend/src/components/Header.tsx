"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtToday } from "@/lib/format";

export default function Header({ onNewTask }: { onNewTask: () => void }) {
  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  useEffect(() => {
    api("/api/chat/mode")
      .then(() => setBackendUp(true))
      .catch(() => setBackendUp(false));
  }, []);

  const today = fmtToday();

  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line pb-5">
      <div className="flex items-baseline gap-3">
        <h1 className="font-display text-3xl tracking-tight">FocusFlow</h1>
        <span className="label-caps hidden sm:inline">AI productivity agent</span>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <span
          className={`h-2 w-2 rounded-full ${
            backendUp === false ? "bg-danger" : "bg-good"
          } transition-colors`}
          title={backendUp === false ? "Backend not reachable" : "Backend connected"}
        />
        <button className="btn btn-primary" onClick={onNewTask}>
          + New task
        </button>
      </div>
      <p className="w-full text-sm text-muted">{today}</p>
    </header>
  );
}
