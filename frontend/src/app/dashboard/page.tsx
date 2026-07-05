'use client';

import AppShell from '@/components/layout/AppShell';
import Link from 'next/link';
import { Sparkles, Briefcase, GitBranch, TrendingUp, ArrowRight, Target } from 'lucide-react';
import { useUserStore } from '@/lib/store/userStore';
import { useEffect, useState } from 'react';
import { usersApi } from '@/lib/api/users';
import { trackingApi } from '@/lib/api/tracking';
import { trendsApi } from '@/lib/api/trends';
import type { UserProfileOut } from '@/lib/types/user';
import type { TrackingListResponse } from '@/lib/types/tracking';
import type { LabeledCount } from '@/lib/types/trends';
import { statusLabel, statusClass } from '@/lib/utils/score';

const TRACKING_STATUSES = ['reviewed', 'saved', 'shortlisted', 'applied', 'rejected', 'ignored'];

export default function DashboardPage() {
  const { session } = useUserStore();
  const [profile, setProfile] = useState<UserProfileOut | null>(null);
  const [pipeline, setPipeline] = useState<TrackingListResponse | null>(null);
  const [topSkills, setTopSkills] = useState<LabeledCount[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session.user_id) return;
    Promise.all([
      usersApi.getProfile(session.user_id).then(setProfile),
      trackingApi.list(session.user_id).then(setPipeline),
      trendsApi.getSkills(6).then(setTopSkills),
    ]).finally(() => setLoading(false));
  }, [session]);

  const pipelineCounts = TRACKING_STATUSES.reduce<Record<string, number>>((acc, s) => {
    acc[s] = pipeline?.items.filter((i) => i.status === s).length ?? 0;
    return acc;
  }, {});

  return (
    <AppShell>
      <div style={{ padding: '32px', maxWidth: '1200px' }}>
        {/* Welcome */}
        <div style={{ marginBottom: '40px' }} className="animate-fade-in">
          <h1 style={{ fontSize: '28px', marginBottom: '8px' }}>
            Welcome back, <span className="gradient-text">{session?.name?.split(' ')[0] ?? 'there'}</span> 👋
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '15px' }}>
            Here&apos;s your career acceleration overview.
          </p>
        </div>

        {/* Quick action cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '16px',
            marginBottom: '40px',
          }}
        >
          <QuickCard
            href="/recommendations"
            icon={<Sparkles size={24} color="var(--brand-light)" />}
            title="AI Recommendations"
            desc="Get your personalized job picks"
            accent="var(--brand)"
            delay="stagger-1"
          />
          <QuickCard
            href="/jobs"
            icon={<Briefcase size={24} color="var(--emerald)" />}
            title="Browse Jobs"
            desc="Explore the full job board"
            accent="var(--emerald)"
            delay="stagger-2"
          />
          <QuickCard
            href="/pipeline"
            icon={<GitBranch size={24} color="#3b82f6" />}
            title="My Pipeline"
            desc="Track your applications"
            accent="#3b82f6"
            delay="stagger-3"
          />
          <QuickCard
            href="/trends"
            icon={<TrendingUp size={24} color="var(--amber)" />}
            title="Market Trends"
            desc="Explore the job market"
            accent="var(--amber)"
            delay="stagger-4"
          />
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '24px',
          }}
        >
          {/* Pipeline summary */}
          <div className="card animate-fade-in-up stagger-2" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <GitBranch size={18} color="var(--brand-light)" />
                Application Pipeline
              </h2>
              <Link href="/pipeline" style={{ fontSize: '13px', color: 'var(--brand-light)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                View all <ArrowRight size={12} />
              </Link>
            </div>
            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: '32px', borderRadius: '8px' }} />)}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {TRACKING_STATUSES.map((s) => (
                  <div
                    key={s}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '8px 12px',
                      background: 'var(--surface-alt)',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <span className={`chip ${statusClass(s)}`} style={{ fontSize: '12px' }}>
                      {statusLabel(s)}
                    </span>
                    <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {pipelineCounts[s]}
                    </span>
                  </div>
                ))}
                <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textAlign: 'center', marginTop: '4px' }}>
                  {pipeline?.total ?? 0} total tracked jobs
                </div>
              </div>
            )}
          </div>

          {/* Top skills + profile */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Profile card */}
            <div className="card animate-fade-in-up stagger-3" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Target size={16} color="var(--brand-light)" />
                  Your Profile
                </h2>
                <Link href="/profile" style={{ fontSize: '12px', color: 'var(--brand-light)' }}>Edit →</Link>
              </div>
              {loading || !profile ? (
                <div className="skeleton" style={{ height: '60px', borderRadius: '8px' }} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <span className="chip chip-skill">{profile.career_level}</span>
                    <span className="chip chip-neutral">{profile.years_of_experience}y exp</span>
                    {profile.workplace_settings.map((w) => (
                      <span key={w} className="chip chip-neutral">{w}</span>
                    ))}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    {profile.skills.slice(0, 5).join(', ')}{profile.skills.length > 5 ? `…+${profile.skills.length - 5}` : ''}
                  </div>
                </div>
              )}
            </div>

            {/* Top skills */}
            <div className="card animate-fade-in-up stagger-4" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <TrendingUp size={16} color="var(--amber)" />
                  Trending Skills
                </h2>
                <Link href="/trends" style={{ fontSize: '12px', color: 'var(--brand-light)' }}>See all →</Link>
              </div>
              {loading ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {[1,2,3,4].map(i => <div key={i} className="skeleton" style={{ width: '80px', height: '24px', borderRadius: '999px' }} />)}
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {topSkills.map(({ label, count }) => (
                    <span
                      key={label}
                      className="chip chip-neutral"
                      title={`${count} job postings`}
                    >
                      {label}
                      <span style={{ color: 'var(--amber)', marginLeft: '4px', fontSize: '10px' }}>{count}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function QuickCard({
  href, icon, title, desc, accent, delay,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  desc: string;
  accent: string;
  delay: string;
}) {
  return (
    <Link
      href={href}
      className={`card card-interactive animate-fade-in-up ${delay}`}
      style={{
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        textDecoration: 'none',
        cursor: 'pointer',
      }}
    >
      <div
        style={{
          width: '44px', height: '44px',
          background: 'var(--surface-alt)',
          border: `1px solid ${accent}30`,
          boxShadow: `0 0 16px ${accent}20`,
          borderRadius: '10px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>{title}</div>
        <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{desc}</div>
      </div>
      <ArrowRight size={16} color="var(--text-subtle)" style={{ marginTop: 'auto' }} />
    </Link>
  );
}
