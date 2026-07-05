'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect } from 'react';
import { trendsApi } from '@/lib/api/trends';
import type { MarketTrendsOut } from '@/lib/types/trends';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, LineChart, Line,
  ResponsiveContainer, Legend,
} from 'recharts';
import { TrendingUp } from 'lucide-react';

const CHART_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6'];

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name?: string }[]; label?: string }) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip" style={{ background: 'var(--surface-alt)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius)', padding: '10px 14px', fontSize: '13px', color: 'var(--text-primary)' }}>
        {label && <div style={{ fontWeight: 600, marginBottom: '4px' }}>{label}</div>}
        {payload.map((p, i) => (
          <div key={i} style={{ color: 'var(--text-muted)' }}>
            {p.name && `${p.name}: `}<span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{typeof p.value === 'number' ? p.value.toLocaleString() : p.value}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

function ChartCard({ title, children, loading }: { title: string; children: React.ReactNode; loading: boolean }) {
  return (
    <div className="card animate-fade-in-up" style={{ padding: '24px' }}>
      <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '20px', color: 'var(--text-primary)' }}>{title}</h3>
      {loading ? (
        <div className="skeleton" style={{ height: '200px', borderRadius: 'var(--radius-sm)' }} />
      ) : children}
    </div>
  );
}

export default function TrendsPage() {
  const [trends, setTrends] = useState<MarketTrendsOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    trendsApi.getAll()
      .then(setTrends)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const workTypeData = trends?.work_types.map(({ label, count }) => ({
    name: label.replace('_', '-'),
    value: count,
  })) ?? [];

  const expData = trends?.experience_levels.map(({ label, count }) => ({
    name: label,
    value: count,
  })) ?? [];

  const skillsData = trends?.top_skills.slice(0, 10).map(({ label, count }) => ({
    name: label,
    count,
  })) ?? [];

  const companiesData = trends?.top_companies.slice(0, 8).map(({ label, count }) => ({
    name: label.length > 20 ? `${label.slice(0, 18)}…` : label,
    count,
  })) ?? [];

  const volumeData = trends?.posting_volume.map(({ period, count }) => ({
    period: period.slice(0, 7),
    count,
  })) ?? [];

  const salaryStats = trends?.salary_stats ?? [];

  return (
    <AppShell>
      <div style={{ padding: '32px', maxWidth: '1400px' }}>
        <div style={{ marginBottom: '32px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <TrendingUp size={22} color="var(--amber)" />
            Market Intelligence
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            Real-time job market insights from your indexed positions.
          </p>
        </div>

        {/* Salary cards */}
        {(loading || salaryStats.length > 0) && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            {loading ? (
              [...Array(3)].map((_, i) => (
                <div key={i} className="card skeleton" style={{ height: '100px' }} />
              ))
            ) : (
              salaryStats.map((stat) => (
                <div key={stat.currency} className="card" style={{ padding: '20px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                    Salary · {stat.currency} {stat.period && `· ${stat.period}`}
                  </div>
                  <div style={{ display: 'flex', gap: '16px' }}>
                    <div>
                      <div style={{ fontSize: '10px', color: 'var(--text-subtle)' }}>Avg</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, fontFamily: "'Sora', sans-serif", color: 'var(--emerald)' }}>
                        {stat.avg.toLocaleString('en-US', { notation: 'compact' })}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '10px', color: 'var(--text-subtle)' }}>Range</div>
                      <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                        {stat.min.toLocaleString('en-US', { notation: 'compact' })} – {stat.max.toLocaleString('en-US', { notation: 'compact' })}
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '8px' }}>{stat.count} positions</div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Main charts grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Top Skills */}
          <ChartCard title="Top Skills in Demand" loading={loading}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={skillsData} layout="vertical" margin={{ left: 10, right: 20, top: 0, bottom: 0 }}>
                <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" tick={{ fill: 'var(--text-subtle)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis dataKey="name" type="category" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={80} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]}>
                  {skillsData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Top Companies */}
          <ChartCard title="Top Hiring Companies" loading={loading}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={companiesData} margin={{ left: 0, right: 20, top: 0, bottom: 40 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-subtle)', fontSize: 10 }} angle={-35} textAnchor="end" axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-subtle)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {companiesData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Posting Volume */}
          <ChartCard title="Job Posting Volume Over Time" loading={loading}>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={volumeData} margin={{ left: 0, right: 20, top: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="period" tick={{ fill: 'var(--text-subtle)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-subtle)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1', r: 3 }} activeDot={{ r: 5, fill: '#818cf8' }} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Work types + Experience levels side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <ChartCard title="Work Mode" loading={loading}>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={workTypeData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value" paddingAngle={3}>
                    {workTypeData.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend formatter={(value) => <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{value}</span>} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Experience" loading={loading}>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={expData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value" paddingAngle={3}>
                    {expData.map((_, i) => (
                      <Cell key={i} fill={['#f59e0b', '#6366f1', '#10b981'][i] ?? CHART_COLORS[i]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend formatter={(value) => <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'capitalize' }}>{value}</span>} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
