import { useQuery } from '@tanstack/react-query'
import { getArchitectureDoc, getManifest } from '../api/client'
import ReactMarkdown from 'react-markdown'

interface Props { jobId: string; repoUrl: string }

export function ArchitecturePage({ jobId, repoUrl }: Props) {
  const { data: doc,      isLoading, isError } = useQuery({
    queryKey: ['architecture', jobId],
    queryFn:  () => getArchitectureDoc(jobId),
  })
  const { data: manifest } = useQuery({
    queryKey: ['manifest', jobId],
    queryFn:  () => getManifest(jobId),
  })

  const edgeCount = manifest?.dependency_graph
    ? Object.values(manifest.dependency_graph).flat().length : null

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">Architecture</div>
        <div className="page-subtitle" style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {repoUrl.replace('https://github.com/','')} · job/{jobId.slice(0,8)}
        </div>
      </div>

      {manifest && (
        <div className="stats-bar">
          <div className="stat-card"><div className="stat-value amber">{manifest.module_count}</div><div className="stat-label">Modules</div></div>
          <div className="stat-card"><div className="stat-value">{manifest.total_chunks}</div><div className="stat-label">Symbols analysed</div></div>
          <div className="stat-card"><div className="stat-value">{edgeCount ?? '—'}</div><div className="stat-label">Import edges</div></div>
          <div className="stat-card"><div className="stat-value">3</div><div className="stat-label">LLM passes</div></div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 240px', gap: 16, alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="var(--amber)" strokeWidth="1.2">
              <rect x="1" y="1" width="11" height="11" rx="2"/>
              <path d="M3.5 4.5h6M3.5 6.5h6M3.5 8.5h3"/>
            </svg>
            <span className="card-title">ARCHITECTURE.md</span>
          </div>
          <div className="card-body">
            {isLoading && (
              <div style={{ display:'flex', alignItems:'center', gap:10, color:'var(--text-tertiary)', fontSize:13 }}>
                <span className="spinner" /> Loading…
              </div>
            )}
            {isError && <div className="error-banner">Architecture doc not found. Has the analysis completed?</div>}
            {doc && <div className="arch-prose"><ReactMarkdown>{doc}</ReactMarkdown></div>}
          </div>
        </div>

        {manifest?.modules && (
          <div className="card" style={{ position: 'sticky', top: 16 }}>
            <div className="card-header">
              <span className="card-title">Modules ({manifest.modules.length})</span>
            </div>
            <div style={{ maxHeight: 500, overflowY: 'auto' }}>
              {(manifest.modules as string[]).map(m => (
                <div key={m} style={{
                  padding: '7px 14px', borderBottom: '1px solid var(--border-subtle)',
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)',
                }}>{m}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
