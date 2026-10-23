export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Task {
  id: string;
  title: string;
  notes: string | null;
  priority: "high" | "medium" | "low";
  deadline: string | null;
  duration_minutes: number;
  status: "todo" | "done" | "missed";
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Block {
  id: string;
  task_id: string;
  start_time: string;
  end_time: string;
  kind: "work" | "replan";
  reason: string | null;
  task_title: string;
  task_priority: string;
  task_status: string;
}

export interface Progress {
  total_tasks: number;
  done: number;
  todo: number;
  missed: number;
  completion_rate: number;
  due_today: number;
  done_today: number;
  overdue: number;
  hours_scheduled_this_week: number;
  hours_completed_this_week: number;
  upcoming_with_deadline: number;
}

export interface AgentAction {
  tool: string;
  summary: string;
  ok: boolean;
  detail?: Record<string, unknown>;
}

export interface ChatResponse {
  reply: string;
  mode: "bedrock" | "mock";
  actions: AgentAction[];
}

export interface ChatMode {
  mode: "bedrock" | "mock";
  model: string | null;
  region: string;
}

export interface ScheduleResponse {
  scheduled_count: number;
  blocks: unknown[];
  explanations: string[];
  unscheduled: { task_id: string; title: string; duration_minutes: number }[];
}

export interface ReplanResponse {
  replanned: boolean;
  missed_count: number;
  changes: string[];
  explanations: string[];
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      ...init,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the FocusFlow backend. Is it running on port 8000?",
      0
    );
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail))
        detail = body.detail
          .map((d: { msg?: string }) => d.msg ?? JSON.stringify(d))
          .join("; ");
    } catch {
      /* keep default */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}
