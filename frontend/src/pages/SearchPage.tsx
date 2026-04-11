import { useState, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { semanticSearch } from '../api/client'
import type { SearchResult } from '../api/client'

const EXAMPLES = [
  'how are HTTP connections managed?',
  'where is authentication handled?',
  'find all error handling code',
  'how is configuration loaded?',
  'what is the main entry point?',
]

interface Props { jobId: string; repoUrl: string }

export function SearchPage({ jobId, repoUrl }: Props) {
  const [query, setQuery]     = useState('')
  const [selected, setSelected] = useState<SearchResult | null>(null)

  const search = useMutation({
    mutationFn: (q: string) => semanticSearch({ job_id: jobId, query: q, top_k: 8 }),
    onSuccess:  () => setSelected(null),
  })

  const run = useCallback((q: string) => {
    if (!q.trim()) return
    setQuery(q)
    search.mutate(q)
  }, [search])

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">Semantic search</div>
        <div className="page-subtitle" style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {repoUrl.replace('https://github.com/','')} · job/{jobId.slice(0,8)}
        </div>
      </div>

      <div className="search-bar">
        <input className="search-input" type="text" value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run(query)}
          placeholder="Ask anything about the codebase…" autoFocus />
        <button className="btn-primary" onClick={() => run(query)}
          disabled={search.isPending || !query.trim()} style={{ flexShrink: 0 }}>
          {search.isPending ? <span className="spinner" /> : 'Search'}
        </button>
      </div>

      {!search.data && !search.isPending && (
        <div className="examples-row">
          <span className="examples-label">Try:</span>
          {EXAMPLES.map(e => <button key={e} className="chip" onClick={() => run(e)}>{e}</button>)}
        </div>
      )}

      {search.isError && (
        <div className="error-banner">Search failed — is Qdrant running and analysis complete?</div>
      )}

      {search.data && (
        <div className="results-grid">
          <div>
            <div className="results-meta">
              {search.data.results.length} results for <em>"{search.data.query}"</em>
            </div>
            <div className="result-list">
              {search.data.results.length === 0 ? (
                <div className="empty-state" style={{ padding: '28px 0' }}>
                  <div className="empty-icon">∅</div>
                  <div className="empty-title">No results</div>
                  <div className="empty-desc">Try rephrasing or a broader query.</div>
                </div>
              ) : search.data.results.map(r => (
                <ResultCard key={r.chunk_id} result={r}
                  selected={selected?.chunk_id === r.chunk_id}
                  onSelect={() => setSelected(selected?.chunk_id === r.chunk_id ? null : r)} />
              ))}
            </div>
          </div>

          <div>
            {selected
              ? <ResultDetail result={selected} />
              : <div className="card" style={{ opacity: 0.45 }}>
                  <div className="empty-state" style={{ padding: '36px 16px' }}>
                    <div className="empty-title" style={{ fontSize: 13 }}>Select a result</div>
                    <div className="empty-desc">Click any result to view code and documentation.</div>
                  </div>
                </div>
            }
          </div>
        </div>
      )}
    </div>
  )
}

function ResultCard({ result, selected, onSelect }: {
  result: SearchResult; selected: boolean; onSelect: () => void
}) {
  return (
    <div className={`result-card ${selected ? 'selected' : ''}`}
      onClick={onSelect} role="button" tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect()}>
      <div className="result-card-top">
        <div className="symbol-pills">
          {result.symbol_names.slice(0,3).map(n => <span key={n} className="symbol-pill">{n}</span>)}
          {result.symbol_names.length > 3 && <span className="symbol-pill">+{result.symbol_names.length - 3}</span>}
        </div>
        <span className="score-badge">{Math.round(result.score * 100)}%</span>
      </div>
      <div className="result-file">
        <span className={`lang-badge lang-${result.language}`}>{result.language}</span>
        <span className="file-path">{result.file_path}</span>
      </div>
      {result.generated_doc && <p className="result-doc-preview">{result.generated_doc}</p>}
    </div>
  )
}

function ResultDetail({ result }: { result: SearchResult }) {
  return (
    <div className="result-detail">
      <div className="detail-header">
        <div className="detail-symbols">
          {result.symbol_names.map(n => <span key={n} className="detail-symbol">{n}</span>)}
        </div>
        <div className="detail-path">{result.file_path}</div>
      </div>
      {result.generated_doc && (
        <div className="detail-section">
          <div className="detail-section-label">Documentation</div>
          <p className="detail-doc">{result.generated_doc}</p>
        </div>
      )}
      <div className="detail-section">
        <div className="detail-section-label">Source</div>
        <pre className="code-block"><code>{result.snippet}</code></pre>
      </div>
    </div>
  )
}
