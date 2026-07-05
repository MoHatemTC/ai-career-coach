'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect } from 'react';
import { recommendationsApi } from '@/lib/api/recommendations';
import { trackingApi } from '@/lib/api/tracking';
import { matchesApi } from '@/lib/api/recommendations';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { RecommendationItem } from '@/lib/types/tracking';
import type { AnalyzeMatchResponse } from '@/lib/types/tracking';
import { scoreClass, scoreLabel, scoreColor } from '@/lib/utils/score';
import { Sparkles, MapPin, BookmarkCheck, Bookmark, Search, Target, X, ExternalLink } from 'lucide-react';
import Link from 'next/link';

const LOADING_MESSAGES = [
  '🔍 Scanning job database…',
  '🧠 Evaluating skill alignment…',
  '📊 Ranking by match score…',
  '⚡ Running LLM re-ranking…',
  '✨ Finalizing your personalized picks…',
];

export default function RecommendationsPage() {
  const { session } = useUserStore();
  const { addToast } = useUIStore();
  const [recs, setRecs] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [msgIdx, setMsgIdx] = useState(0);
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [analyzing, setAnalyzing] = useState<number | null>(null);
  const [matchResult, setMatchResult] = useState<{ jobId: number; data: AnalyzeMatchResponse } | null>(null);

  useEffect(() => {
    if (!session.user_id) return;
    const interval = setInterval(() => setMsgIdx((i) => (i + 1) % LOADING_MESSAGES.length), 3000);
    recommendationsApi.get(session.user_id)
      .then((res) => setRecs(res.recommendations))
      .catch(() => addToast('Failed to load recommendations', 'error'))
      .finally(() => { setLoading(false); clearInterval(interval); });
    return () => clearInterval(interval);
  }, [session, addToast]);

  const toggleSave = async (jobId: number) => {
    if (!session.user_id) return;
    const isSaved = savedIds.has(jobId);
    setSavedIds((prev) => { const n = new Set(prev); if (isSaved) n.delete(jobId); else n.add(jobId); return n; });
    try {
      await trackingApi.update(jobId, session.user_id, isSaved ? 'reviewed' : 'saved');
      addToast(isSaved ? 'Removed from saved' : 'Job saved ✓', 'success');
    } catch { addToast('Failed to update', 'error'); }
  };

  const handleAnalyze = async (jobId: number) => {
    if (!session.user_id) return;
    setAnalyzing(jobId);
    try {
      const res = await matchesApi.analyze({ user_id: session.user_id, job_id: jobId });
      setMatchResult({ jobId, data: res });
    } catch { addToast('Analysis failed', 'error'); }
    finally { setAnalyzing(null); }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="ai-loading-screen" style={{ position: 'relative', minHeight: 'calc(100vh - 0px)', background: 'var(--bg)' }}>
          <div
            style={{
              width: '96px', height: '96px',
              borderRadius: '50%',
              background: 'var(--brand-dim)',
              border: '2px solid rgba(99,102,241,0.4)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: '32px',
            }}
            className="brain-pulse"
          >
            <Sparkles size={40} color="var(--brand-light)" />
          </div>
          <h2 style={{ fontSize: '22px', marginBottom: '12px' }}>Finding Your Best Matches</h2>
          <p className="ai-loading-text" style={{ fontSize: '16px', fontWeight: 600, marginBottom: '32px', minHeight: '24px' }}>
            {LOADING_MESSAGES[msgIdx]}
          </p>
          <div style={{ display: 'flex', gap: '6px' }}>
            {[0,1,2].map((i) => (
              <div
                key={i}
                style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: 'var(--brand)',
                  opacity: msgIdx % 3 === i ? 1 : 0.3,
                  transition: 'opacity 0.3s ease',
                }}
              />
            ))}
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-subtle)', marginTop: '24px' }}>
            This may take 10–30 seconds while AI evaluates jobs for you…
          </p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={{ padding: '32px' }}>
        <div style={{ marginBottom: '28px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Sparkles size={22} color="var(--brand-light)" />
            AI Recommendations
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            {recs.length} jobs ranked by AI match score — just for you.
          </p>
        </div>

        {recs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px', color: 'var(--text-muted)' }}>
            <Search size={48} style={{ marginBottom: '16px', opacity: 0.3 }} />
            <p>No recommendations yet. Try collecting more jobs first.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {recs.map((rec, i) => (
              <RecCard
                key={rec.job.id}
                rec={rec}
                rank={i + 1}
                isSaved={savedIds.has(rec.job.id)}
                isAnalyzing={analyzing === rec.job.id}
                onSave={() => toggleSave(rec.job.id)}
                onAnalyze={() => handleAnalyze(rec.job.id)}
                animDelay={i < 6 ? `stagger-${Math.min(i + 1, 6)}` : ''}
              />
            ))}
          </div>
        )}

        {/* Match result drawer */}
        {matchResult && (
          <MatchDrawer
            data={matchResult.data}
            onClose={() => setMatchResult(null)}
          />
        )}
      </div>
    </AppShell>
  );
}

function RecCard({
  rec, rank, isSaved, isAnalyzing, onSave, onAnalyze, animDelay,
}: {
  rec: RecommendationItem;
  rank: number;
  isSaved: boolean;
  isAnalyzing: boolean;
  onSave: () => void;
  onAnalyze: () => void;
  animDelay: string;
}) {
  const score = rec.total_score;
  const scoreC = scoreClass(score);
  const color = scoreColor(score);

  return (
    <div
      className={`card card-interactive animate-fade-in-up ${animDelay}`}
      style={{ padding: '24px' }}
    >
      <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
        {/* Rank & Score */}
        <div style={{ textAlign: 'center', flexShrink: 0 }}>
          <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginBottom: '4px' }}>#{rank}</div>
          <div
            className={`chip ${scoreC}`}
            style={{
              fontSize: '20px',
              fontWeight: 700,
              fontFamily: "'Sora', sans-serif",
              padding: '6px 12px',
              boxShadow: `0 0 16px ${color}30`,
            }}
          >
            {score}
          </div>
          <div style={{ fontSize: '10px', color, marginTop: '4px', fontWeight: 500 }}>
            {scoreLabel(score)}
          </div>
        </div>

        {/* Details */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
            <div>
              <Link href={`/jobs/${rec.job.id}`} style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', textDecoration: 'none' }}>
                {rec.job.title}
              </Link>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {rec.job.company}
                {rec.job.location && (
                  <span style={{ marginLeft: '8px' }}>
                    <MapPin size={11} style={{ display: 'inline', marginRight: '3px' }} />
                    {rec.job.location}
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button className="btn btn-ghost btn-icon" onClick={onSave} title={isSaved ? 'Remove' : 'Save'}>
                {isSaved ? <BookmarkCheck size={17} color="var(--brand-light)" /> : <Bookmark size={17} />}
              </button>
              {rec.job.url && (
                <a href={rec.job.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-icon">
                  <ExternalLink size={16} />
                </a>
              )}
            </div>
          </div>

          {/* Explanation */}
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px', lineHeight: 1.6 }}>
            {rec.explanation}
          </p>

          {/* Strengths + Missing */}
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {rec.strengths.slice(0, 3).map((s) => (
              <span key={s} className="chip chip-strength">{s}</span>
            ))}
            {rec.missing_skills.slice(0, 3).map((s) => (
              <span key={s} className="chip chip-missing">{s}</span>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flexShrink: 0 }}>
          <button
            className="btn btn-primary btn-sm"
            onClick={onAnalyze}
            disabled={isAnalyzing}
            style={{ gap: '6px' }}
          >
            <Target size={14} />
            {isAnalyzing ? 'Analyzing…' : 'Analyze'}
          </button>
          <Link href={`/jobs/${rec.job.id}`} className="btn btn-secondary btn-sm">
            View Job
          </Link>
        </div>
      </div>
    </div>
  );
}

function MatchDrawer({ data, onClose }: { data: AnalyzeMatchResponse; onClose: () => void }) {
  const categories = [
    { label: 'Hard Skills', value: data.match_score * 0.4, max: 40, color: 'var(--brand)' },
    { label: 'Experience', value: data.match_score * 0.3, max: 30, color: 'var(--emerald)' },
    { label: 'Soft Skills', value: data.match_score * 0.2, max: 20, color: 'var(--amber)' },
    { label: 'Logistics', value: data.match_score * 0.1, max: 10, color: '#3b82f6' },
  ];

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" style={{ width: '480px', padding: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h2 style={{ fontSize: '20px' }}>Match Analysis</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        {/* Total score */}
        <div
          className="card"
          style={{
            padding: '24px',
            textAlign: 'center',
            marginBottom: '24px',
            background: `${scoreColor(data.match_score)}15`,
            borderColor: `${scoreColor(data.match_score)}30`,
          }}
        >
          <div style={{ fontSize: '56px', fontWeight: 800, fontFamily: "'Sora', sans-serif", color: scoreColor(data.match_score), lineHeight: 1 }}>
            {data.match_score}
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px' }}>
            {scoreLabel(data.match_score)}
          </div>
        </div>

        {/* Score breakdown */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '24px' }}>
          {categories.map(({ label, value, max, color }) => (
            <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ fontWeight: 600, color }}>{Math.round(value)}/{max}</span>
              </div>
              <div className="progress-track" style={{ height: '6px' }}>
                <div
                  className="progress-fill"
                  style={{ width: `${(value / max) * 100}%`, background: color }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Explanation */}
        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Analysis</h3>
          <blockquote style={{ borderLeft: '3px solid var(--brand)', paddingLeft: '16px', color: 'var(--text-muted)', fontSize: '13px', lineHeight: 1.7, margin: 0 }}>
            {data.match_explanation}
          </blockquote>
        </div>

        {/* Missing skills */}
        {data.missing_skills.length > 0 && (
          <div style={{ marginBottom: '20px' }}>
            <h3 style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Skills to Develop</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {data.missing_skills.map((s) => <span key={s} className="chip chip-missing">{s}</span>)}
            </div>
          </div>
        )}

        <Link href={`/applications/${data.job_id}`} className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: '16px' }}>
          View Application Materials
        </Link>
      </div>
    </>
  );
}
