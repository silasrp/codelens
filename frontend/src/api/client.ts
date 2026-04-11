const BASE = import.meta.env.VITE_API_URL ?? ''

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers }, ...opts,
  })
  if (!res.ok) { const b = await res.text(); throw new Error(`${res.status}: ${b}`) }
  return res.json()
}

export type JobStatus =
  | 'queued' | 'cloned' | 'parsing' | 'analyzing_symbols' | 'analyzing_modules'
  | 'synthesizing' | 'embedding' | 'storing' | 'complete' | 'failed'

export interface JobStatusResponse {
  job_id: string; status: JobStatus; progress: number;
  repo_url?: string; error_message?: string; result_manifest?: string;
}

export interface SearchResult {
  chunk_id: string; file_path: string; symbol_names: string[];
  language: string; score: number; snippet: string; generated_doc: string;
}

export interface SearchResponse { query: string; results: SearchResult[]; job_id: string; }

export const submitRepository = (body: { repo_url: string; branch?: string }) =>
  req<{ job_id: string; status: string }>('/api/analysis/submit',
    { method: 'POST', body: JSON.stringify(body) })

export const getJobStatus = (jobId: string) =>
  req<JobStatusResponse>(`/api/analysis/status/${jobId}`)

export const listJobs = (limit = 20) =>
  req<JobStatusResponse[]>(`/api/analysis/jobs?limit=${limit}`)

export const semanticSearch = (body: { job_id: string; query: string; top_k?: number }) =>
  req<SearchResponse>('/api/search', { method: 'POST', body: JSON.stringify(body) })

export const getArchitectureDoc = async (jobId: string): Promise<string> => {
  const res = await fetch(`${BASE}/api/docs/${jobId}/architecture`)
  if (!res.ok) throw new Error(`${res.status}`)
  return res.text()
}

export const getManifest = (jobId: string) =>
  req<{ job_id: string; module_count: number; total_chunks: number;
        modules: string[]; dependency_graph: Record<string, string[]> }>(
    `/api/docs/${jobId}/manifest`)
