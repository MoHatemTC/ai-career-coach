'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect, useCallback } from 'react';
import { trackingApi } from '@/lib/api/tracking';
import { jobsApi } from '@/lib/api/jobs';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { JobTrackingOut, TrackingStatus, TrackingEvent } from '@/lib/types/tracking';
import type { JobOut } from '@/lib/types/job';
import { statusLabel, statusClass, cx } from '@/lib/utils/score';
import { formatDateTime } from '@/lib/utils/date';
import { GitBranch, X, Clock, ExternalLink, ChevronRight } from 'lucide-react';
import Link from 'next/link';

const COLUMNS: { status: TrackingStatus; label: string; color: string }[] = [
  { status: 'reviewed',    label: 'Reviewed',    color: '#64748b' },
  { status: 'saved',       label: 'Saved',       color: '#6366f1' },
  { status: 'shortlisted', label: 'Shortlisted', color: '#3b82f6' },
  { status: 'applied',     label: 'Applied',     color: '#10b981' },
  { status: 'rejected',    label: 'Rejected',    color: '#f43f5e' },
  { status: 'ignored',     label: 'Ignored',     color: '#475569' },
];

type JobMap = Record<number, JobOut>;

export default function PipelinePage() {
  const { session } = useUserStore();
  const { addToast } = useUIStore();
  const [items, setItems] = useState<JobTrackingOut[]>([]);
  const [jobMap, setJobMap] = useState<JobMap>({});
  const [loading, setLoading] = useState(true);
  const [drawerItem, setDrawerItem] = useState<JobTrackingOut | null>(null);
  const [history, setHistory] = useState<TrackingEvent[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const load = useCallback(async () => {
    if (!session.user_id) return;
    setLoading(true);
    try {
      const res = await trackingApi.list(session.user_id);
      setItems(res.items);
      // Fetch job details for all tracked jobs
      const jobsRes = await jobsApi.list({ limit: 200, offset: 0 });
      const map: JobMap = {};
      for (const j of jobsRes.jobs) map[j.id] = j;
      setJobMap(map);
    } catch { addToast('Failed to load pipeline', 'error'); }
    finally { setLoading(false); }
  }, [session, addToast]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (item: JobTrackingOut, newStatus: TrackingStatus) => {
    if (!session.user_id) return;
    // Optimistic
    setItems((prev) => prev.map((i) => i.id === item.id ? { ...i, status: newStatus } : i));
    try {
      await trackingApi.update(item.job_id, session.user_id, newStatus);
      addToast(
        newStatus === 'shortlisted'
          ? '⭐ Shortlisted! AI is preparing application materials…'
          : `Moved to ${statusLabel(newStatus)}`,
        'success',
      );
    } catch {
      // rollback
      setItems((prev) => prev.map((i) => i.id === item.id ? { ...i, status: item.status } : i));
      addToast('Failed to update status', 'error');
    }
  };

  const openDrawer = async (item: JobTrackingOut) => {
    setDrawerItem(item);
    if (!session.user_id) return;
    setLoadingHistory(true);
    try {
      const res = await trackingApi.getHistory(item.job_id, session.user_id);
      setHistory(res.events);
    } catch { /* silent */ }
    finally { setLoadingHistory(false); }
  };

  const columns = COLUMNS.map((col) => ({
    ...col,
    items: items.filter((i) => i.status === col.status),
  }));

  const NEXT_STATUSES: Record<TrackingStatus, TrackingStatus[]> = {
    reviewed:    ['saved', 'ignored'],
    saved:       ['shortlisted', 'ignored'],
    shortlisted: ['applied', 'ignored'],
    applied:     ['rejected'],
    rejected:    [],
    ignored:     ['reviewed'],
  };

  return (
    <AppShell>
      <div style={{ padding: '32px', overflow: 'hidden' }}>
        <div style={{ marginBottom: '24px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <GitBranch size={22} color="var(--brand-light)" />
            My Pipeline
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            {items.length} tracked job{items.length !== 1 ? 's' : ''}
          </p>
        </div>

        {loading ? (
          <div style={{ display: 'flex', gap: '16px', overflowX: 'auto', paddingBottom: '16px' }}>
            {COLUMNS.map((c) => (
              <div key={c.status} className="card skeleton" style={{ width: '280px', height: '400px', flexShrink: 0 }} />
            ))}
          </div>
        ) : (
          <div className="kanban-board">
            {columns.map((col) => (
              <div key={col.status} className="kanban-column">
                <div
                  style={{
                    padding: '16px 16px 12px',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexShrink: 0,
                  }}
                >
                  <span style={{ fontSize: '13px', fontWeight: 600, color: col.color }}>{col.label}</span>
                  <span
                    style={{
                      background: `${col.color}20`,
                      color: col.color,
                      borderRadius: '999px',
                      padding: '1px 8px',
                      fontSize: '12px',
                      fontWeight: 600,
                    }}
                  >
                    {col.items.length}
                  </span>
                </div>

                <div className="kanban-column-body">
                  {col.items.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-subtle)', fontSize: '13px' }}>
                      No jobs here yet
                    </div>
                  )}
                  {col.items.map((item) => {
                    const job = jobMap[item.job_id];
                    return (
                      <div
                        key={item.id}
                        className="card card-interactive animate-fade-in"
                        style={{ padding: '14px', cursor: 'pointer' }}
                        onClick={() => openDrawer(item)}
                      >
                        <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px', lineHeight: 1.3 }}>
                          {job?.title ?? `Job #${item.job_id}`}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '10px' }}>
                          {job?.company ?? '—'}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-subtle)' }}>
                            {formatDateTime(item.updated_at)}
                          </span>
                          <ChevronRight size={14} color="var(--text-subtle)" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Drawer */}
        {drawerItem && (
          <>
            <div className="drawer-backdrop" onClick={() => setDrawerItem(null)} />
            <div className="drawer" style={{ width: '440px', padding: '28px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ fontSize: '18px' }}>Job Details</h2>
                <button className="btn btn-ghost btn-icon" onClick={() => setDrawerItem(null)}>
                  <X size={18} />
                </button>
              </div>

              {(() => {
                const job = jobMap[drawerItem.job_id];
                return (
                  <>
                    <div className="card" style={{ padding: '16px', marginBottom: '20px' }}>
                      <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                        {job?.title ?? `Job #${drawerItem.job_id}`}
                      </div>
                      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                        {job?.company} {job?.city && `· ${job.city}`}
                      </div>
                      <span className={`chip ${statusClass(drawerItem.status)}`}>
                        {statusLabel(drawerItem.status)}
                      </span>
                    </div>

                    {/* Move actions */}
                    <div style={{ marginBottom: '24px' }}>
                      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '10px', fontWeight: 500 }}>
                        Move to
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {NEXT_STATUSES[drawerItem.status].map((s) => (
                          <button
                            key={s}
                            className={`btn btn-secondary btn-sm ${statusClass(s)}`}
                            onClick={async () => {
                              await updateStatus(drawerItem, s);
                              setDrawerItem((prev) => prev ? { ...prev, status: s } : null);
                            }}
                          >
                            {statusLabel(s)}
                          </button>
                        ))}
                        {job?.url && (
                          <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm">
                            <ExternalLink size={13} /> Apply
                          </a>
                        )}
                      </div>
                    </div>

                    {drawerItem.status === 'shortlisted' || drawerItem.status === 'applied' ? (
                      <Link href={`/applications/${drawerItem.job_id}`} className="btn btn-primary btn-sm" style={{ marginBottom: '24px', display: 'inline-flex' }}>
                        View Application Materials
                      </Link>
                    ) : null}

                    {/* History */}
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={14} />
                        Status History
                      </div>
                      {loadingHistory ? (
                        <div className="skeleton" style={{ height: '80px', borderRadius: '8px' }} />
                      ) : (
                        <div style={{ position: 'relative' }}>
                          {history.map((event, i) => (
                            <div key={event.id} style={{ display: 'flex', gap: '12px', paddingBottom: '16px', position: 'relative' }}>
                              {i < history.length - 1 && (
                                <div style={{ position: 'absolute', left: '7px', top: '16px', bottom: 0, width: '1px', background: 'var(--border)' }} />
                              )}
                              <div style={{
                                width: '15px', height: '15px', borderRadius: '50%',
                                background: i === history.length - 1 ? 'var(--brand)' : 'var(--surface-alt)',
                                border: `2px solid ${i === history.length - 1 ? 'var(--brand)' : 'var(--border)'}`,
                                flexShrink: 0, marginTop: '2px',
                              }} />
                              <div>
                                <span className={cx('chip', statusClass(event.to_status))} style={{ fontSize: '11px' }}>
                                  {statusLabel(event.to_status)}
                                </span>
                                <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '4px' }}>
                                  {formatDateTime(event.created_at)}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                );
              })()}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
