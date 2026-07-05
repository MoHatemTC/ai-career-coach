'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect } from 'react';
import { applicationsApi } from '@/lib/api/applications';
import { trackingApi } from '@/lib/api/tracking';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { ApplicationResponse, ApplicationMaterialsResponse } from '@/lib/types/tracking';
import { FileText, Copy, CheckCircle2, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { useParams } from 'next/navigation';

export default function ApplicationPage() {
  const params = useParams();
  const jobId = Number(params.jobId);
  const { session } = useUserStore();
  const { addToast } = useUIStore();

  const [data, setData] = useState<ApplicationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (!session.user_id) return;
    const userId = session.user_id;
    // Try to load existing materials first
    trackingApi.getMaterials(jobId, userId)
      .then((res: ApplicationMaterialsResponse) => {
        if (res.cv_tailoring_suggestion || res.cover_letter_draft) {
          setData({
            candidate_id: userId,
            job_id: jobId,
            cv_tailoring: res.cv_tailoring_suggestion || { tailored_summary: '', highlighted_skills: [], missing_skills: [], bullet_point_suggestions: [] },
            cover_letter: res.cover_letter_draft || { draft_content: '', tone_analysis: '' },
            status: 'Draft - Awaiting Human Approval',
            disclaimer: 'AI-generated content. A human-in-the-loop review is required before use.',
          });
          setLoading(false);
        } else {
          generateMaterials();
        }
      })
      .catch(() => generateMaterials());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, jobId]);

  const generateMaterials = async () => {
    if (!session.user_id) return;
    setGenerating(true);
    try {
      const res = await applicationsApi.generate(session.user_id, jobId);
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate materials';
      addToast(msg, 'error');
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  };

  const handleCopy = async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    addToast('Copied to clipboard ✓', 'success');
    setTimeout(() => setCopied(null), 2000);
  };

  const handleMarkApplied = async () => {
    if (!session.user_id) return;
    setApplying(true);
    try {
      await trackingApi.update(jobId, session.user_id, 'applied');
      addToast("Marked as applied! Good luck 🎉", 'success');
    } catch { addToast('Failed to update status', 'error'); }
    finally { setApplying(false); }
  };

  if (loading || generating) {
    return (
      <AppShell>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 100px)', gap: '24px' }}>
          <div
            style={{ width: '72px', height: '72px', borderRadius: '50%', background: 'var(--brand-dim)', border: '2px solid rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            className="brain-pulse"
          >
            <Loader2 size={32} color="var(--brand-light)" className="animate-spin" />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="ai-loading-text" style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>
              {generating ? 'AI is crafting your application materials…' : 'Loading materials…'}
            </div>
            <p style={{ color: 'var(--text-subtle)', fontSize: '13px' }}>
              {generating ? 'This may take 20–30 seconds' : ''}
            </p>
          </div>
        </div>
      </AppShell>
    );
  }

  if (!data) {
    return (
      <AppShell>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 100px)', gap: '16px' }}>
          <AlertTriangle size={48} color="var(--amber)" />
          <p style={{ color: 'var(--text-muted)' }}>Could not load application materials.</p>
          <button className="btn btn-primary" onClick={generateMaterials}>
            <RefreshCw size={16} /> Generate Now
          </button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={{ padding: '32px', maxWidth: '1200px' }}>
        {/* Header */}
        <div style={{ marginBottom: '28px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FileText size={22} color="var(--brand-light)" />
            Application Materials
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>Job #{jobId}</p>
        </div>

        {/* Disclaimer */}
        <div
          style={{
            background: 'var(--amber-dim)',
            border: '1px solid rgba(245,158,11,0.3)',
            borderRadius: 'var(--radius)',
            padding: '14px 20px',
            display: 'flex',
            gap: '12px',
            alignItems: 'flex-start',
            marginBottom: '28px',
          }}
        >
          <AlertTriangle size={18} color="var(--amber)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--amber)', marginBottom: '4px' }}>
              AI-Generated Draft — Human Review Required
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              {data.disclaimer}
            </div>
          </div>
        </div>

        {/* Split panel */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '28px' }}>
          {/* CV Tailoring */}
          <div className="card animate-fade-in-up stagger-1" style={{ padding: '24px' }}>
            <h2 style={{ fontSize: '17px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileText size={18} color="var(--brand-light)" />
              CV Tailoring
            </h2>

            <div style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px' }}>Tailored Summary</div>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: 1.7, background: 'var(--surface-alt)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                {data.cv_tailoring.tailored_summary}
              </p>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>Highlight These Skills</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {data.cv_tailoring.highlighted_skills.map((s) => (
                  <span key={s} className="chip chip-strength">{s}</span>
                ))}
              </div>
            </div>

            {data.cv_tailoring.missing_skills.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>Missing Skills</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {data.cv_tailoring.missing_skills.map((s) => (
                    <span key={s} className="chip chip-missing">{s}</span>
                  ))}
                </div>
              </div>
            )}

            {data.cv_tailoring.bullet_point_suggestions.length > 0 && (
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px' }}>Bullet Points</div>
                <ul style={{ margin: 0, paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {data.cv_tailoring.bullet_point_suggestions.map((b, i) => (
                    <li key={i} style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: 1.6, cursor: 'pointer' }} onClick={() => handleCopy(b, `bullet-${i}`)}>
                      {b}
                      {copied === `bullet-${i}` && <span style={{ marginLeft: '8px', fontSize: '11px', color: 'var(--emerald)' }}>✓ Copied</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Cover Letter */}
          <div className="card animate-fade-in-up stagger-2" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '17px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileText size={18} color="var(--emerald)" />
                Cover Letter
              </h2>
              <div style={{ display: 'flex', gap: '8px' }}>
                <span
                  style={{
                    fontSize: '11px',
                    padding: '3px 10px',
                    borderRadius: '999px',
                    background: 'var(--emerald-dim)',
                    color: 'var(--emerald)',
                    fontWeight: 500,
                  }}
                >
                  {data.cover_letter.tone_analysis}
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleCopy(data.cover_letter.draft_content, 'letter')}
                  style={{ gap: '6px' }}
                >
                  {copied === 'letter' ? <CheckCircle2 size={14} color="var(--emerald)" /> : <Copy size={14} />}
                  {copied === 'letter' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>

            {/* Paper card preview */}
            <div
              style={{
                background: '#f8fafc',
                borderRadius: 'var(--radius)',
                padding: '24px',
                border: '1px solid #e2e8f0',
                fontFamily: "'Georgia', serif",
                fontSize: '13px',
                color: '#1e293b',
                lineHeight: 1.8,
                whiteSpace: 'pre-wrap',
                maxHeight: '480px',
                overflowY: 'auto',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              }}
            >
              {data.cover_letter.draft_content}
            </div>
          </div>
        </div>

        {/* Footer actions */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={generateMaterials}>
            <RefreshCw size={16} />
            Regenerate
          </button>
          <button
            className="btn btn-primary"
            onClick={handleMarkApplied}
            disabled={applying}
            style={{ gap: '8px' }}
          >
            <CheckCircle2 size={16} />
            {applying ? 'Marking…' : 'Mark as Applied'}
          </button>
        </div>
      </div>
    </AppShell>
  );
}
