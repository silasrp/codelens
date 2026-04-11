import { useQuery } from '@tanstack/react-query'
import { listJobs } from '../api/client'

interface Props { onSelectJob: (jobId: string, repoUrl: string) => void; activeJobId?: string }

export function HistoryPage({ onSelectJob, activeJobId }: Props) {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs'], queryFn: () => listJobs(50), refetchInterval: 5000,
  })

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">Job history</div>
        <div className="page-subtitle">All analysis jobs, most recent first</div>
      </div>

      <div className="card">
        {isLoading && (
          <div style={{ padding:28, display:'flex', alignItems:'center', gap:10,
            color:'var(--text-tertiary)', fontSize:13 }}>
            <span className="spinner" /> Loading jobs…
          </div>
        )}

        {jobs?.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <div className="empty-title">No jobs yet</div>
            <div className="empty-desc">Submit a repository to start your first analysis.</div>
          </div>
        )}

        {jobs && jobs.length > 0 && (
          <table className="job-table">
            <thead>
              <tr>
                <th>Job ID</th><th>Repository</th><th>Status</th><th>Progress</th><th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.job_id}
                  style={{ background: job.job_id === activeJobId ? 'var(--amber-dim)' : undefined }}>
                  <td style={{ color: job.job_id === activeJobId ? 'var(--amber)' : undefined }}>
                    {job.job_id.slice(0,8)}…
                  </td>
                  <td style={{ maxWidth:260, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {job.repo_url ?? '—'}
                  </td>
                  <td>
                    <span className={`status-pill ${job.status}`}>
                      <span className="dot-sm" />{job.status}
                    </span>
                  </td>
                  <td>
                    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                      <div style={{ width:52, height:3, background:'var(--bg-overlay)', borderRadius:99, overflow:'hidden' }}>
                        <div style={{
                          height:'100%', width:`${job.progress}%`, borderRadius:99,
                          background: job.status==='complete' ? 'var(--green)'
                                    : job.status==='failed'   ? 'var(--red)' : 'var(--amber)',
                        }} />
                      </div>
                      <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-tertiary)' }}>
                        {job.progress}%
                      </span>
                    </div>
                  </td>
                  <td>
                    {job.status === 'complete' && (
                      <button className="btn-link"
                        onClick={() => onSelectJob(job.job_id, job.repo_url ?? '')}>
                        {job.job_id === activeJobId ? 'active' : 'open →'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
