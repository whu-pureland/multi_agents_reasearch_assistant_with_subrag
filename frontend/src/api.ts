export type TodoStatus = "pending" | "in_progress" | "done";
export type JobStatus = "created" | "running" | "succeeded" | "failed";

export type JobSettings = {
  max_todos: number;
  web_results_per_todo: number;
  include_private_knowledge: boolean;
  private_semantic_top_k: number;
  enable_fact_check: boolean;
  enable_mcp_tools: boolean;
};

export type TodoItem = {
  id: string;
  title: string;
  status: TodoStatus;
  note_id?: string | null;
};

export type Note = {
  todo_id: string;
  title: string;
  content_md: string;
  source_ids: string[];
};

export type Source = {
  id: string;
  title: string;
  url: string;
  snippet?: string | null;
  provider: string;
  quality_score: number;
};

export type UploadItem = {
  filename: string;
  stored_path: string;
  ingested: boolean;
};

export type Job = {
  id: string;
  query: string;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  settings: JobSettings;
  todos: TodoItem[];
  notes: Note[];
  sources: Source[];
  report?: string | null;
  error?: string | null;
  uploads: UploadItem[];
  events: Record<string, unknown>[];
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function createJob(query: string, settings: JobSettings): Promise<Job> {
  return await http<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ query, settings }) });
}

export async function getJob(jobId: string): Promise<Job> {
  return await http<Job>(`/api/jobs/${jobId}`);
}

export async function startJob(jobId: string): Promise<Job> {
  return await http<Job>(`/api/jobs/${jobId}/start`, { method: "POST" });
}

export async function uploadFile(jobId: string, file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/jobs/${jobId}/uploads`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return (await res.json()) as Job;
}
