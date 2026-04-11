/**
 * Semantic code search panel.
 *
 * Lets users query a previously analysed codebase with natural language.
 * Results are ranked by Qdrant cosine similarity and displayed with the
 * relevant code snippet and LLM-generated documentation side by side.
 */

import { useState, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { semanticSearch } from "../api/client";
import type { SearchResult } from "../api/client";

interface SearchPanelProps {
  jobId: string;
}

const EXAMPLE_QUERIES = [
  "where is authentication handled?",
  "how are database connections managed?",
  "find all error handling code",
  "what is the main entry point?",
  "show me the data validation logic",
];

export function SearchPanel({ jobId }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);

  const searchMutation = useMutation({
    mutationFn: (q: string) =>
      semanticSearch({ job_id: jobId, query: q, top_k: 8 }),
  });

  const handleSearch = useCallback(
    (q: string) => {
      if (!q.trim()) return;
      setQuery(q);
      setSelectedResult(null);
      searchMutation.mutate(q);
    },
    [searchMutation]
  );

  return (
    <div className="search-panel">
      {/* Search input */}
      <div className="search-input-wrapper">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch(query)}
          placeholder="Ask anything about the codebase…"
          className="search-input"
          aria-label="Search query"
        />
        <button
          onClick={() => handleSearch(query)}
          disabled={searchMutation.isPending || !query.trim()}
          className="search-btn"
        >
          {searchMutation.isPending ? "Searching…" : "Search"}
        </button>
      </div>

      {/* Example queries */}
      {!searchMutation.data && !searchMutation.isPending && (
        <div className="example-queries">
          <span className="examples-label">Try:</span>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              className="example-chip"
              onClick={() => handleSearch(q)}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Results layout */}
      {searchMutation.data && (
        <div className="results-layout">
          {/* Result list */}
          <div className="result-list" role="list">
            <p className="results-meta">
              {searchMutation.data.results.length} results for{" "}
              <em>"{searchMutation.data.query}"</em>
            </p>
            {searchMutation.data.results.map((result) => (
              <ResultCard
                key={result.chunk_id}
                result={result}
                isSelected={selectedResult?.chunk_id === result.chunk_id}
                onSelect={() =>
                  setSelectedResult(
                    selectedResult?.chunk_id === result.chunk_id
                      ? null
                      : result
                  )
                }
              />
            ))}
          </div>

          {/* Detail panel */}
          {selectedResult && (
            <ResultDetail result={selectedResult} />
          )}
        </div>
      )}

      {searchMutation.isError && (
        <div className="search-error" role="alert">
          Search failed. Make sure the analysis is complete and try again.
        </div>
      )}
    </div>
  );
}

interface ResultCardProps {
  result: SearchResult;
  isSelected: boolean;
  onSelect: () => void;
}

function ResultCard({ result, isSelected, onSelect }: ResultCardProps) {
  const scorePercent = Math.round(result.score * 100);

  return (
    <div
      className={`result-card ${isSelected ? "result-card--selected" : ""}`}
      onClick={onSelect}
      role="listitem"
      aria-selected={isSelected}
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
    >
      <div className="result-card-header">
        <div className="result-symbols">
          {result.symbol_names.map((name) => (
            <code key={name} className="symbol-name">
              {name}
            </code>
          ))}
        </div>
        <span
          className="similarity-score"
          title={`${scorePercent}% similarity`}
          aria-label={`Similarity: ${scorePercent}%`}
        >
          {scorePercent}%
        </span>
      </div>

      <div className="result-file-path">
        <span className={`lang-badge lang-badge--${result.language}`}>
          {result.language}
        </span>
        <span className="file-path">{result.file_path}</span>
      </div>

      {result.generated_doc && (
        <p className="result-doc-preview">
          {result.generated_doc.slice(0, 160)}
          {result.generated_doc.length > 160 ? "…" : ""}
        </p>
      )}
    </div>
  );
}

function ResultDetail({ result }: { result: SearchResult }) {
  return (
    <div className="result-detail" aria-label="Result detail">
      <div className="detail-header">
        <div>
          {result.symbol_names.map((n) => (
            <code key={n} className="symbol-name symbol-name--large">
              {n}
            </code>
          ))}
          <span className="detail-file-path">{result.file_path}</span>
        </div>
      </div>

      {/* LLM-generated documentation */}
      {result.generated_doc && (
        <section className="detail-section">
          <h3 className="detail-section-title">Documentation</h3>
          <p className="detail-doc">{result.generated_doc}</p>
        </section>
      )}

      {/* Raw code snippet */}
      <section className="detail-section">
        <h3 className="detail-section-title">Code</h3>
        <pre className="code-block">
          <code>{result.snippet}</code>
        </pre>
      </section>
    </div>
  );
}
