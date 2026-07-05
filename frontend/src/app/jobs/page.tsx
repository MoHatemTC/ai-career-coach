'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect, useCallback } from 'react';
import { jobsApi } from '@/lib/api/jobs';
import { trackingApi } from '@/lib/api/tracking';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { JobOut } from '@/lib/types/job';
import { formatSalary, cx } from '@/lib/utils/score';
import { timeAgo } from '@/lib/utils/date';
import { Search, Filter, Briefcase, MapPin, Calendar, Bookmark, BookmarkCheck, ExternalLink } from 'lucide-react';
import Link from 'next/link';

const EXP_LEVELS = ['', 'junior', 'mid', 'senior'];
const WORK_MODES = ['', 'remote', 'hybrid', 'on_site'];

export default function JobsPage() {
  const { session } = useUserStore();
  const { addToast } = useUIStore();
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [expLevel, setExpLevel] = useState('');
  const [workMode, setWorkMode] = useState('');
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState('');

  const LIMIT = 20;

  const fetchJobs = useCallback(async (reset = false) => {
    const currentOffset = reset ? 0 : offset;
    if (reset) setLoading(true); else setLoadingMore(true);
    try {
      const res = await jobsApi.list({
        experience_level: expLevel || undefined,
        limit: LIMIT,
        offset: currentOffset,
      });
      if (reset) {
        setJobs(res.jobs);
        setOffset(LIMIT);
      } else {
        setJobs((prev) => [...prev, ...res.jobs]);
        setOffset((o) => o + LIMIT);
      }
      setTotal(res.total);
    } catch {
      addToast('Failed to load jobs', 'error');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [expLevel, offset, addToast]);

  useEffect(() => {
    // fetch-on-mount / on-filter-change: fetchJobs synchronously toggles the
    // loading flag, which is the intended behavior here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchJobs(true);
    // Intentionally re-run only when the experience-level filter changes;
    // fetchJobs is stable enough for this screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expLevel]);

  const toggleSave = async (job: JobOut) => {
    if (!session.user_id) return;
    const isSaved = savedIds.has(job.id);
    setSavedIds((prev) => {
      const next = new Set(prev);
      if (isSaved) next.delete(job.id); else next.add(job.id);
      return next;
    });
    try {
      await trackingApi.update(job.id, session.user_id, isSaved ? 'reviewed' : 'saved');
      addToast(isSaved ? 'Removed from saved' : 'Job saved ✓', 'success');
    } catch {
      // rollback
      setSavedIds((prev) => {
        const next = new Set(prev);
        if (isSaved) next.add(job.id); else next.delete(job.id);
        return next;
      });
      addToast('Failed to update', 'error');
    }
  };

  const filteredJobs = jobs.filter((j) => {
    if (search) {
      const q = search.toLowerCase();
      if (!j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false;
    }
    if (workMode && j.work_mode !== workMode) return false;
    return true;
  });

  return (
    <AppShell>
      <div style={{ padding: '32px' }}>
        <div style={{ marginBottom: '28px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px' }}>
            <Briefcase size={22} style={{ display: 'inline', marginRight: '10px', color: 'var(--brand-light)' }} />
            Job Board
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            {total.toLocaleString()} jobs available
          </p>
        </div>

        {/* Filters */}
        <div
          className="card"
          style={{
            padding: '16px 20px',
            display: 'flex',
            gap: '12px',
            flexWrap: 'wrap',
            alignItems: 'center',
            marginBottom: '24px',
          }}
        >
          {/* Search */}
          <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
            <Search size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-subtle)' }} />
            <input
              className="input"
              style={{ paddingLeft: '36px' }}
              placeholder="Search title or company…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Experience level */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <Filter size={14} color="var(--text-subtle)" />
            {EXP_LEVELS.map((level) => (
              <button
                key={level || 'all'}
                onClick={() => { setExpLevel(level); }}
                className={cx('btn btn-sm', expLevel === level ? 'btn-primary' : 'btn-secondary')}
                style={{ textTransform: 'capitalize' }}
              >
                {level || 'All levels'}
              </button>
            ))}
          </div>

          {/* Work mode */}
          <div style={{ display: 'flex', gap: '6px' }}>
            {WORK_MODES.filter(Boolean).map((mode) => (
              <button
                key={mode}
                onClick={() => setWorkMode(workMode === mode ? '' : mode)}
                className={cx('btn btn-sm', workMode === mode ? 'btn-primary' : 'btn-secondary')}
                style={{ textTransform: 'capitalize' }}
              >
                {mode.replace('_', '-')}
              </button>
            ))}
          </div>
        </div>

        {/* Job grid */}
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
            {[...Array(6)].map((_, i) => (
              <div key={i} className="card skeleton" style={{ height: '200px' }} />
            ))}
          </div>
        ) : filteredJobs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 32px', color: 'var(--text-muted)' }}>
            <Briefcase size={48} style={{ marginBottom: '16px', opacity: 0.3 }} />
            <p>No jobs match your filters.</p>
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
              {filteredJobs.map((job, i) => (
                <JobCard
                  key={job.id}
                  job={job}
                  isSaved={savedIds.has(job.id)}
                  onSave={() => toggleSave(job)}
                  animDelay={i < 6 ? `stagger-${Math.min(i + 1, 6)}` : ''}
                />
              ))}
            </div>
            {jobs.length < total && (
              <div style={{ textAlign: 'center', marginTop: '32px' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => fetchJobs(false)}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading…' : 'Load More Jobs'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function JobCard({
  job,
  isSaved,
  onSave,
  animDelay,
}: {
  job: JobOut;
  isSaved: boolean;
  onSave: () => void;
  animDelay: string;
}) {
  const workModeColors: Record<string, string> = {
    remote: 'var(--emerald)',
    hybrid: 'var(--brand-light)',
    on_site: 'var(--amber)',
  };
  const workModeColor = workModeColors[job.work_mode ?? ''] ?? 'var(--text-muted)';

  return (
    <div
      className={`card card-interactive animate-fade-in-up ${animDelay}`}
      style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <Link
            href={`/jobs/${job.id}`}
            style={{
              fontSize: '15px',
              fontWeight: 600,
              color: 'var(--text-primary)',
              textDecoration: 'none',
              display: 'block',
              marginBottom: '4px',
            }}
          >
            {job.title}
          </Link>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{job.company}</div>
        </div>
        <button
          className="btn btn-ghost btn-icon"
          onClick={(e) => { e.preventDefault(); onSave(); }}
          title={isSaved ? 'Remove from saved' : 'Save job'}
        >
          {isSaved ? (
            <BookmarkCheck size={18} color="var(--brand-light)" />
          ) : (
            <Bookmark size={18} />
          )}
        </button>
      </div>

      {/* Meta */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--text-muted)' }}>
        {job.city && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <MapPin size={12} /> {job.city}
          </span>
        )}
        {job.posted_date && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Calendar size={12} /> {timeAgo(job.posted_date)}
          </span>
        )}
        {job.work_mode && (
          <span
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              color: workModeColor,
              fontWeight: 500,
            }}
          >
            {job.work_mode.replace('_', '-')}
          </span>
        )}
      </div>

      {/* Skills */}
      {job.required_skills.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
          {job.required_skills.slice(0, 4).map((s) => (
            <span key={s} className="chip chip-skill">{s}</span>
          ))}
          {job.required_skills.length > 4 && (
            <span className="chip chip-neutral">+{job.required_skills.length - 4}</span>
          )}
        </div>
      )}

      {/* Salary + link */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          {!job.salary_hidden
            ? formatSalary(job.salary_min, job.salary_max, job.salary_currency, null)
            : 'Salary hidden'}
        </span>
        {job.url && (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost btn-sm"
            style={{ gap: '4px', fontSize: '12px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink size={12} /> Apply
          </a>
        )}
      </div>
    </div>
  );
}
