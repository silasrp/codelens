/**
 * Analysis submission and real-time progress dashboard.
 *
 * Handles the full lifecycle from URL input → job polling → result display.
 * Uses TanStack Query for automatic polling with exponential backoff.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { submitRepository, getJobStatus } from "../api/client";
import type { JobStatus } from "../api/client";

const PHASE_LABELS: Record<string, string> = {
  queued: "Queued",
  cloned: "Repository cloned",
  parsing: "Parsing source files",
  analyzing_symbols: "Pass 1 — Documenting symbols",
  analyzing_modules: "Pass 2 — Summarising modules",
  synthesizing: "Pass 3 — Architecture analysis",
  embedding: "Indexing for semantic search",
  storing: "Saving results",
  complete: "Complete",
  failed: "Failed",
};

interface AnalysisDashboardProps {
  onComplete: (jobId: string) => void;
}

export function AnalysisDashboard({ onComplete }: AnalysisDashboardProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const submitMutation = useMutation({
    mutationFn: () => submitRepository({ repo_url: repoUrl, branch }),
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
    },
  });

  // Poll job status every 2s while active, stop when complete/failed
  const { data: jobStatus } = useQuery({
    queryKey: ["jobStatus", activeJobId],
    queryFn: () => getJobStatus(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (data) => {
      if (!data || ["complete", "failed"].includes(data.status)) return false;
      return 2000;
    },
    onSuccess: (data) => {
      if (data.status === "complete") {
        onComplete(activeJobId!);
      }
    },
  });

  const isRunning =
    activeJobId &&
    jobStatus &&
    !["complete", "failed"].includes(jobStatus.status);

  return (
    <div className="analysis-dashboard">
      {/* Submission form */}
      {!activeJobId && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitMutation.mutate();
          }}
          className="submit-form"
        >
          <div className="field-group">
            <label htmlFor="repo-url">GitHub repository URL</label>
            <input
              id="repo-url"
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
              className="url-input"
            />
          </div>

          <div className="field-group">
            <label htmlFor="branch">Branch</label>
            <input
              id="branch"
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              className="branch-input"
            />
          </div>

          <button
            type="submit"
            disabled={submitMutation.isPending || !repoUrl}
            className="submit-btn"
          >
            {submitMutation.isPending ? "Submitting…" : "Analyse repository"}
          </button>
        </form>
      )}

      {/* Progress display */}
      {jobStatus && (
        <div className="job-progress">
          <div className="progress-header">
            <span className="job-id">Job {activeJobId?.slice(0, 8)}</span>
            <span
              className={`status-badge status-${jobStatus.status}`}
              aria-live="polite"
            >
              {PHASE_LABELS[jobStatus.status] ?? jobStatus.status}
            </span>
          </div>

          <div
            className="progress-bar-track"
            role="progressbar"
            aria-valuenow={jobStatus.progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="progress-bar-fill"
              style={{
                width: `${jobStatus.progress}%`,
                transition: "width 0.5s ease",
              }}
            />
          </div>

          <p className="progress-label">
            {jobStatus.progress}% — {PHASE_LABELS[jobStatus.status]}
          </p>

          {jobStatus.status === "failed" && jobStatus.error_message && (
            <div className="error-message" role="alert">
              <strong>Analysis failed:</strong> {jobStatus.error_message}
            </div>
          )}

          {isRunning && (
            <PassVisualiser currentStatus={jobStatus.status} />
          )}

          {jobStatus.status !== "complete" && jobStatus.status !== "failed" && (
            <button
              className="cancel-btn"
              onClick={() => {
                setActiveJobId(null);
                submitMutation.reset();
              }}
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Shows which analysis pass is currently active.
 * Makes the multi-pass nature of the system visible to the user.
 */
function PassVisualiser({ currentStatus }: { currentStatus: string }) {
  const passes = [
    {
      id: "analyzing_symbols",
      label: "Pass 1",
      description: "Per-symbol documentation",
    },
    {
      id: "analyzing_modules",
      label: "Pass 2",
      description: "Module summaries",
    },
    {
      id: "synthesizing",
      label: "Pass 3",
      description: "Architecture narrative",
    },
  ];

  const activeIdx = passes.findIndex((p) => p.id === currentStatus);

  return (
    <div className="pass-visualiser" aria-label="Analysis passes">
      {passes.map((pass, idx) => {
        const state =
          idx < activeIdx
            ? "done"
            : idx === activeIdx
            ? "active"
            : "pending";

        return (
          <div key={pass.id} className={`pass-step pass-${state}`}>
            <div className="pass-indicator">
              {state === "done" ? "✓" : state === "active" ? "◉" : "○"}
            </div>
            <div className="pass-label">
              <strong>{pass.label}</strong>
              <span>{pass.description}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
