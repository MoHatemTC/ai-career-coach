'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { jobsApi } from '@/lib/api/jobs';
import { trackingApi } from '@/lib/api/tracking';
import { matchesApi } from '@/lib/api/recommendations';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { JobOut } from '@/lib/types/job';
import type { TrackingStatus, AnalyzeMatchResponse } from '@/lib/types/tracking';
import { formatSalary, scoreLabel, scoreColor, statusLabel, statusClass } from '@/lib/utils/score';
import { timeAgo } from '@/lib/utils/date';
import {
  MapPin, Calendar, Briefcase, Globe, Star, Bookmark, BookmarkCheck,
  CheckCircle2, XCircle, Target, FileText, Loader2, ExternalLink
} from 'lucide-react';
import Link from 'next/link';

export default function JobDetailPage() {
  const params = useParams();
  const jobId = Number(params.id);
  const { session } = useUserStore();
  const { addToast } = useUIStore();
  const [job, setJob] = useState<JobOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentStatus, setCurrentStatus] = useState<TrackingStatus | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [matchData, setMatchData] = useState<AnalyzeMatchResponse | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!session.user_id) return;
    Promise.all([
      jobsApi.list({ limit: 1, offset: jobId - 1 }).then((r) => {
        // Try to find by id from the general list
        setJob(r.jobs.find((j) => j.id === jobId) ?? r.jobs[0] ?? null);
      }),
      trackingApi.getForJob(jobId, session.user_id)
        .then((t) => setCurrentStatus(t.status))
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [jobId, session]);

  const updateStatus = async (status: TrackingStatus) => {
    if (!session.user_id) return;
    setActionLoading(status);
    try {
      await trackingApi.update(jobId, session.user_id, status);
      setCurrentStatus(status);
      addToast(
        status === 'shortlisted' ? '⭐ Shortlisted! AI is preparing materials…'
        : status === 'applied' ? '✅ Marked as applied! Good luck 🎉'
        : `Moved to ${statusLabel(status)}`,
        'success',
      );
    } catch { addToast('Failed to update', 'error'); }
    finally { setActionLoading(null); }
  };

  const handleAnalyze = async () => {
    if (!session.user_id) return;
    setAnalyzing(true);
    try {
      const res = await matchesApi.analyze({ user_id: session.user_id, job_id: jobId });
      setMatchData(res);
    } catch { addToast('Analysis failed', 'error'); }
    finally { setAnalyzing(false); }
  };

  if (loading) {
    return (
      <AppShell>
        <div style={{ padding: '32px' }}>
          <div className="skeleton" style={{ height: '300px', borderRadius: 'var(--radius-lg)' }} />
        </div>
      </AppShell>
    );
  }

  if (!job) {
    return (
      <AppShell>
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Job not found.
        </div>
      </AppShell>
    );
  }

  const workModeColors: Record<string, string> = {
    remote: 'var(--emerald)', hybrid: 'var(--brand-light)', on_site: 'var(--amber)',
  };

  return (
    <AppShell>
      <div style={{ padding: '32px', maxWidth: '1100px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '28px', alignItems: 'flex-start' }}>
          {/* Main content */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card animate-fade-in" style={{ padding: '28px' }}>
              {/* Title */}
              <h1 style={{ fontSize: '24px', marginBottom: '6px' }}>{job.title}</h1>
              <div style={{ fontSize: '16px', color: 'var(--text-muted)', marginBottom: '16px' }}>{job.company}</div>

              {/* Meta row */}
              <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '13px', color: 'var(--text-muted)', marginBottom: '20px' }}>
                {job.city && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <MapPin size={13} /> {job.city}{job.area ? `, ${job.area}` : ''}
                  </span>
                )}
                {job.posted_date && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <Calendar size={13} /> {timeAgo(job.posted_date)}
                  </span>
                )}
                {job.work_mode && (
                  <span style={{ color: workModeColors[job.work_mode], fontWeight: 500 }}>
                    {job.work_mode.replace('_', '-')}
                  </span>
                )}
                {job.experience_level && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <Briefcase size={13} /> {job.experience_level}
                  </span>
                )}
                {job.source && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <Globe size={13} /> {job.source}
                  </span>
                )}
              </div>

              {/* Salary */}
              {!job.salary_hidden && (job.salary_min || job.salary_max) && (
                <div
                  style={{
                    display: 'inline-block',
                    background: 'var(--emerald-dim)',
                    color: 'var(--emerald)',
                    border: '1px solid rgba(16,185,129,0.2)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '6px 14px',
                    fontSize: '14px',
                    fontWeight: 600,
                    marginBottom: '20px',
                  }}
                >
                  {formatSalary(job.salary_min, job.salary_max, job.salary_currency, job.salary_period)}
                </div>
              )}

              {/* Required skills */}
              {job.required_skills.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px' }}>
                    Required Skills
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {job.required_skills.map((s) => <span key={s} className="chip chip-skill">{s}</span>)}
                  </div>
                </div>
              )}

              {/* Description */}
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                  Job Description
                </div>
                <div
                  style={{
                    fontSize: '14px',
                    color: 'var(--text-muted)',
                    lineHeight: 1.8,
                    whiteSpace: 'pre-wrap',
                    maxHeight: '400px',
                    overflowY: 'auto',
                  }}
                >
                  {job.description}
                </div>
              </div>
            </div>
          </div>

          {/* Sticky sidebar */}
          <div style={{ position: 'sticky', top: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="card animate-fade-in-up" style={{ padding: '20px' }}>
              {/* Current status */}
              {currentStatus && (
                <div style={{ marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginBottom: '6px' }}>Current Status</div>
                  <span className={`chip ${statusClass(currentStatus)}`}>{statusLabel(currentStatus)}</span>
                </div>
              )}

              {/* Match score (if analyzed) */}
              {matchData && (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '16px',
                    background: `${scoreColor(matchData.match_score)}10`,
                    borderRadius: 'var(--radius)',
                    border: `1px solid ${scoreColor(matchData.match_score)}25`,
                    marginBottom: '16px',
                  }}
                >
                  <div style={{ fontSize: '36px', fontWeight: 800, fontFamily: "'Sora', sans-serif", color: scoreColor(matchData.match_score) }}>
                    {matchData.match_score}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{scoreLabel(matchData.match_score)}</div>
                  {matchData.missing_skills.length > 0 && (
                    <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '4px', justifyContent: 'center' }}>
                      {matchData.missing_skills.slice(0, 3).map((s) => <span key={s} className="chip chip-missing" style={{ fontSize: '10px' }}>{s}</span>)}
                    </div>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => updateStatus('saved')}
                  disabled={!!actionLoading || currentStatus === 'saved'}
                  style={{ justifyContent: 'flex-start', gap: '10px' }}
                >
                  {currentStatus === 'saved' ? <BookmarkCheck size={16} color="var(--brand-light)" /> : <Bookmark size={16} />}
                  {currentStatus === 'saved' ? 'Saved' : 'Save Job'}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => updateStatus('shortlisted')}
                  disabled={!!actionLoading || currentStatus === 'shortlisted'}
                  style={{ justifyContent: 'flex-start', gap: '10px' }}
                >
                  <Star size={16} color={currentStatus === 'shortlisted' ? 'var(--amber)' : undefined} />
                  {currentStatus === 'shortlisted' ? 'Shortlisted ✓' : 'Shortlist'}
                </button>

                <button
                  className="btn btn-primary"
                  onClick={handleAnalyze}
                  disabled={analyzing}
                  style={{ justifyContent: 'flex-start', gap: '10px' }}
                >
                  {analyzing ? <Loader2 size={16} className="animate-spin" /> : <Target size={16} />}
                  {analyzing ? 'Analyzing…' : 'Analyze Match'}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => updateStatus('applied')}
                  disabled={!!actionLoading}
                  style={{ justifyContent: 'flex-start', gap: '10px' }}
                >
                  {actionLoading === 'applied' ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} color="var(--emerald)" />}
                  Mark Applied
                </button>

                <button
                  className="btn btn-ghost"
                  onClick={() => updateStatus('ignored')}
                  disabled={!!actionLoading}
                  style={{ justifyContent: 'flex-start', gap: '10px', color: 'var(--text-subtle)' }}
                >
                  <XCircle size={16} />
                  Ignore
                </button>
              </div>
            </div>

            {(currentStatus === 'shortlisted' || currentStatus === 'applied') && (
              <Link href={`/applications/${jobId}`} className="btn btn-primary" style={{ justifyContent: 'flex-start', gap: '10px' }}>
                <FileText size={16} />
                Application Materials
              </Link>
            )}

            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary"
                style={{ justifyContent: 'flex-start', gap: '10px' }}
              >
                <ExternalLink size={16} />
                View Original Posting
              </a>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
