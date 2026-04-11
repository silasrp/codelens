import { useState } from 'react'
import { AnalysisPage }    from './pages/AnalysisPage'
import { SearchPage }      from './pages/SearchPage'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { HistoryPage }     from './pages/HistoryPage'

type View = 'analysis' | 'search' | 'architecture' | 'history'
export interface ActiveJob { jobId: string; repoUrl: string }

export default function App() {
  const [view, setView]           = useState<View>('analysis')
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null)

  const handleComplete  = (jobId: string, repoUrl: string) => { setActiveJob({ jobId, repoUrl }); setView('search') }
  const handleSelectJob = (jobId: string, repoUrl: string) => { setActiveJob({ jobId, repoUrl }); setView('search') }

  const navTo = (v: View) => { if ((v === 'search' || v === 'architecture') && !activeJob) return; setView(v) }

  return (
    <div className="app">
      <header className="header">
        <button className="header-logo" onClick={() => setView('analysis')}>
          <div className="logo-mark">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="2" width="5" height="5" rx="1" fill="#070b14"/>
              <rect x="9" y="2" width="5" height="5" rx="1" fill="#070b14" opacity="0.6"/>
              <rect x="2" y="9" width="5" height="5" rx="1" fill="#070b14" opacity="0.6"/>
              <rect x="9" y="9" width="5" height="5" rx="1" fill="#070b14" opacity="0.3"/>
            </svg>
          </div>
          <span className="logo-text">Code<span>Lens</span></span>
        </button>
        <div className="header-divider" />
        {activeJob && (
          <div className="header-job-badge">
            <span className="dot" />
            <span>job/{activeJob.jobId.slice(0, 8)}</span>
          </div>
        )}
        <div className="header-actions">
          {activeJob && <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => setActiveJob(null)}>Clear job</button>}
        </div>
      </header>

      <nav className="sidebar">
        <span className="sidebar-section-label">Workspace</span>
        <NavItem icon={<IconAnalysis />} label="New analysis"   active={view === 'analysis'}      onClick={() => setView('analysis')} />
        <NavItem icon={<IconSearch />}   label="Search"         active={view === 'search'}         onClick={() => navTo('search')}        disabled={!activeJob} />
        <NavItem icon={<IconArch />}     label="Architecture"   active={view === 'architecture'}   onClick={() => navTo('architecture')}  disabled={!activeJob} />
        <span className="sidebar-section-label">Jobs</span>
        <NavItem icon={<IconHistory />}  label="Job history"    active={view === 'history'}        onClick={() => setView('history')} />
        <div className="sidebar-footer">
          <div className="version-tag">codelens v0.1.0</div>
        </div>
      </nav>

      <main className="main">
        {view === 'analysis'      && <AnalysisPage onComplete={handleComplete} />}
        {view === 'search'        && activeJob && <SearchPage jobId={activeJob.jobId} repoUrl={activeJob.repoUrl} />}
        {view === 'architecture'  && activeJob && <ArchitecturePage jobId={activeJob.jobId} repoUrl={activeJob.repoUrl} />}
        {view === 'history'       && <HistoryPage onSelectJob={handleSelectJob} activeJobId={activeJob?.jobId} />}
        {(view === 'search' || view === 'architecture') && !activeJob && (
          <div className="page"><div className="empty-state">
            <div className="empty-icon">🔍</div>
            <div className="empty-title">No active job</div>
            <div className="empty-desc">Submit and complete an analysis first.</div>
          </div></div>
        )}
      </main>
    </div>
  )
}

function NavItem({ icon, label, active, onClick, disabled }: {
  icon: React.ReactNode; label: string; active: boolean;
  onClick: () => void; disabled?: boolean;
}) {
  return (
    <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}
      style={{ opacity: disabled ? 0.35 : 1 }} disabled={disabled}>
      <span className="nav-icon">{icon}</span>{label}
    </button>
  )
}

const IconAnalysis = () => <svg viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.2" width="15" height="15"><rect x="1.5" y="1.5" width="12" height="12" rx="2"/><path d="M5 7.5h5M5 5h3M5 10h2"/></svg>
const IconSearch   = () => <svg viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.2" width="15" height="15"><circle cx="6.5" cy="6.5" r="4.5"/><path d="M10 10l3 3"/></svg>
const IconArch     = () => <svg viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.2" width="15" height="15"><circle cx="7.5" cy="4" r="1.5"/><circle cx="7.5" cy="11" r="1.5"/><circle cx="4" cy="7.5" r="1.5"/><circle cx="11" cy="7.5" r="1.5"/><path d="M7.5 5.5v4M5.5 7.5h4"/></svg>
const IconHistory  = () => <svg viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.2" width="15" height="15"><circle cx="7.5" cy="7.5" r="6"/><path d="M7.5 4v4l2.5 1.5"/></svg>
