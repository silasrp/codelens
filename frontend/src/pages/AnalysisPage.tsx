import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { submitRepository, getJobStatus } from '../api/client'

const STAGES = [
  { id: 'cloned',             label: 'Repository cloned',            desc: 'Source files fetched' },
  { id: 'parsing',            label: 'AST parse + dependency graph', desc: 'tree-sitter + NetworkX' },
  { id: 'analyzing_symbols',  label: 'Pass 1 — Symbol docs',         desc: 'Per-function via GPT-4o (parallel)' },
  { id: 'analyzing_modules',  label: 'Pass 2 — Module summaries',    desc: 'With upstream context injected' },
  { id: 'synthesizing',       label: 'Pass 3 — Architecture',        desc: 'Graph + all summaries → narrative' },
  { id: 'embedding',          label: 'Semantic indexing',            desc: 'voyage-code-3 → Qdrant' },
  { id: 'storing',            label: 'Saving results',               desc: 'Writing docs to S3' },
]

const ORDER = ['queued','cloned','parsing','analyzing_symbols','analyzing_modules',
               'synthesizing','embedding','storing','complete']

interface Props { onComplete: (jobId: string, repoUrl: string) => void }

export function AnalysisPage({ onComplete }: Props) {
  const [url, setUrl]           = useState('')
  const [branch, setBranch]     = useState('main')
  const [activeJob, setActive]  = useState<string | null>(null)
  const [submitted, setSubmitted] = useState('')

  const submit = useMutation({
    mutationFn: () => submitRepository({ repo_url: url, branch }),
    onSuccess:  d => { setActive(d.job_id); setSubmitted(url) },
  })

  const { data: job } = useQuery({
    queryKey: ['jobStatus', activeJob],
    queryFn:  () => getJobStatus(activeJob!),
    enabled:  !!activeJob,
    refetchInterval: q => {
      const s = q.state.data?.status
      return (!s || s === 'complete' || s === 'failed') ? false : 2500
    },
  })

  if (job?.status === 'complete' && activeJob) onComplete(activeJob, submitted)

  const idx = job ? ORDER.indexOf(job.status) : -1
  const stageState = (id: string) => {
    if (!job) return 'pending'
    const si = ORDER.indexOf(id)
    if (si < idx) return 'done'
    if (id === job.status) return 'active'
    return 'pending'
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">New analysis</div>
        <div className="page-subtitle">Submit a repository for multi-pass LLM analysis</div>
      </div>

      <div className="submit-card" style={{ maxWidth: 620 }}>
        <div style={{ marginBottom: 16 }}>
          <label className="field-label" htmlFor="url">Repository URL</label>
          <input id="url" className="text-input" type="url" value={url}
            onChange={e => setUrl(e.target.value)} placeholder="https://github.com/owner/repo"
            disabled={!!activeJob}
            onKeyDown={e => e.key === 'Enter' && !activeJob && url && submit.mutate()} />
        </div>

        <div className="field-row">
          <div>
            <label className="field-label" htmlFor="branch">Branch</label>
            <input id="branch" className="text-input" value={branch}
              onChange={e => setBranch(e.target.value)} placeholder="main" disabled={!!activeJob} />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="btn-primary" style={{ width: '100%', height: 41 }}
              onClick={() => submit.mutate()}
              disabled={submit.isPending || !url || !!activeJob}>
              {submit.isPending ? 'Submitting…' : 'Analyse →'}
            </button>
          </div>
        </div>

        {job && job.status !== 'failed' && (
          <div className="progress-block">
            <div className="progress-top">
              <span className="progress-status-text">
                {job.status === 'complete' ? '✓ Complete' : '⟳ Running…'}
              </span>
              <span className="progress-pct">{job.progress}%</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${job.progress}%` }} />
            </div>
            <div className="pipeline">
              {STAGES.map(s => {
                const state = stageState(s.id)
                return (
                  <div key={s.id} className={`pipeline-stage ${state}`}>
                    <div className="stage-dot"><div className="stage-dot-inner" /></div>
                    <div className="stage-info">
                      <div className="stage-name">{s.label}</div>
                      <div className="stage-desc">{s.desc}</div>
                    </div>
                    {state === 'done' && <div className="stage-check">✓</div>}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {job?.status === 'failed' && (
          <div className="error-banner">✗ {job.error_message ?? 'Analysis failed'}</div>
        )}

        {!activeJob && (
          <div style={{ marginTop: 18, paddingTop: 18, borderTop: '1px solid var(--border-subtle)' }}>
            <div className="field-label" style={{ marginBottom: 8 }}>Quick start</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['https://github.com/psf/requests','https://github.com/pallets/flask',
                'https://github.com/encode/httpx'].map(u => (
                <button key={u} className="chip" onClick={() => setUrl(u)}>
                  {u.replace('https://github.com/','')}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {!activeJob && (
        <div style={{ marginTop: 28, maxWidth: 620 }}>
          <div className="card">
            <div className="card-header">
              <span className="card-title">What CodeLens does</span>
            </div>
            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                ['AST parsing',       'tree-sitter builds a full syntax tree — not line-count chunking'],
                ['Dependency graph',  'NetworkX resolves imports into a directed module graph with cycle detection'],
                ['Pass 1 (GPT-4o)',   'Every function and class gets a docstring, run in parallel'],
                ['Pass 2 (GPT-4o)',   'Each module summarised with upstream dependency context injected'],
                ['Pass 3 (GPT-4o)',   'Architecture narrative from the graph + all module summaries'],
                ['Semantic search',   'voyage-code-3 embeddings in Qdrant for natural language queries'],
              ].map(([title, desc]) => (
                <div key={title} style={{ display: 'flex', gap: 10 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)',
                    background: 'var(--amber-dim)', border: '1px solid var(--amber)',
                    borderRadius: 'var(--radius-sm)', padding: '2px 8px',
                    height: 'fit-content', whiteSpace: 'nowrap', marginTop: 2,
                  }}>{title}</span>
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 300 }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
