'use client';

import AppShell from '@/components/layout/AppShell';
import { useState, useEffect } from 'react';
import { usersApi } from '@/lib/api/users';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { UserProfileOut } from '@/lib/types/user';
import { User, Save, RefreshCw, X } from 'lucide-react';

const WORKPLACE_OPTIONS = [
  { value: 'remote', label: '🌍 Remote' },
  { value: 'hybrid', label: '🏠 Hybrid' },
  { value: 'on_site', label: '🏢 On-site' },
];

function TagInput({ label, values, onChange, placeholder }: { label: string; values: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [input, setInput] = useState('');
  const add = () => { const v = input.trim().toLowerCase(); if (v && !values.includes(v)) onChange([...values, v]); setInput(''); };
  return (
    <div>
      <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>{label}</label>
      <div style={{ background: 'var(--surface-alt)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius)', padding: '8px', display: 'flex', flexWrap: 'wrap', gap: '6px', minHeight: '44px' }}>
        {values.map((v) => (
          <span key={v} className="chip chip-skill" style={{ cursor: 'pointer' }} onClick={() => onChange(values.filter(x => x !== v))}>
            {v} <X size={10} />
          </span>
        ))}
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }} placeholder={placeholder} style={{ background: 'none', border: 'none', outline: 'none', color: 'var(--text-primary)', fontSize: '13px', minWidth: '120px', flex: 1 }} />
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { session, setSession, clearSession } = useUserStore();
  const { addToast } = useUIStore();
  const [profile, setProfile] = useState<UserProfileOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [desiredRoles, setDesiredRoles] = useState<string[]>([]);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [jobCategories, setJobCategories] = useState<string[]>([]);
  const [workplaceSettings, setWorkplaceSettings] = useState<string[]>([]);
  const [preferredLocation, setPreferredLocation] = useState('');

  useEffect(() => {
    if (!session.user_id) return;
    usersApi.getProfile(session.user_id).then((p) => {
      setProfile(p);
      setDesiredRoles(p.desired_roles);
      setJobTitles(p.job_titles);
      setJobCategories(p.job_categories);
      setWorkplaceSettings(p.workplace_settings);
      setPreferredLocation(p.preferred_location ?? '');
    }).finally(() => setLoading(false));
  }, [session]);

  const handleSave = async () => {
    if (!session.user_id) return;
    setSaving(true);
    try {
      await usersApi.updatePreferences(session.user_id, {
        desired_roles: desiredRoles,
        job_titles: jobTitles,
        job_categories: jobCategories,
        workplace_settings: workplaceSettings,
        preferred_location: preferredLocation || undefined,
      });
      addToast('Preferences updated ✓', 'success');
    } catch { addToast('Failed to save', 'error'); }
    finally { setSaving(false); }
  };

  const toggleWorkplace = (v: string) => setWorkplaceSettings((prev) => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v]);

  return (
    <AppShell>
      <div style={{ padding: '32px', maxWidth: '800px' }}>
        <div style={{ marginBottom: '32px' }}>
          <h1 style={{ fontSize: '26px', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <User size={22} color="var(--brand-light)" />
            Profile & Settings
          </h1>
        </div>

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {[1,2,3].map(i => <div key={i} className="card skeleton" style={{ height: '120px' }} />)}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {/* Identity */}
            {profile && (
              <div className="card animate-fade-in-up stagger-1" style={{ padding: '24px' }}>
                <h2 style={{ marginBottom: '20px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '12px' }}>
                  Identity (from CV)
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  {[
                    { label: 'Name', value: profile.name },
                    { label: 'Email', value: profile.email ?? '—' },
                    { label: 'Career Level', value: profile.career_level },
                    { label: 'Experience', value: `${profile.years_of_experience} years` },
                    { label: 'Education', value: profile.education ?? '—' },
                    { label: 'Location', value: profile.preferred_location ?? '—' },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <div style={{ fontSize: '11px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>{label}</div>
                      <div style={{ fontSize: '14px', color: 'var(--text-primary)', fontWeight: 500 }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Skills from CV */}
            {profile && (
              <div className="card animate-fade-in-up stagger-2" style={{ padding: '24px' }}>
                <h2 style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '20px' }}>
                  Skills & Tools (from CV)
                </h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div>
                    <div style={{ fontSize: '12px', color: 'var(--text-subtle)', marginBottom: '8px' }}>Skills</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {profile.skills.map((s) => <span key={s} className="chip chip-skill">{s}</span>)}
                    </div>
                  </div>
                  {profile.tools.length > 0 && (
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--text-subtle)', marginBottom: '8px' }}>Tools</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {profile.tools.map((t) => <span key={t} className="chip chip-neutral">{t}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Preferences */}
            <div className="card animate-fade-in-up stagger-3" style={{ padding: '24px' }}>
              <h2 style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '24px' }}>
                Career Preferences (editable)
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <TagInput label="Desired Roles" values={desiredRoles} onChange={setDesiredRoles} placeholder="e.g. AI Engineer…" />
                <TagInput label="Job Titles" values={jobTitles} onChange={setJobTitles} placeholder="e.g. Senior Backend…" />
                <TagInput label="Job Categories" values={jobCategories} onChange={setJobCategories} placeholder="e.g. Machine Learning…" />

                <div>
                  <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '10px' }}>Workplace Settings</label>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    {WORKPLACE_OPTIONS.map(({ value, label }) => (
                      <button
                        key={value}
                        onClick={() => toggleWorkplace(value)}
                        className={`btn ${workplaceSettings.includes(value) ? 'btn-primary' : 'btn-secondary'}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>Preferred Location</label>
                  <input className="input" value={preferredLocation} onChange={(e) => setPreferredLocation(e.target.value)} placeholder="e.g. Cairo, Egypt" />
                </div>

                <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ alignSelf: 'flex-start', gap: '8px' }}>
                  <Save size={16} />
                  {saving ? 'Saving…' : 'Save Preferences'}
                </button>
              </div>
            </div>

            {/* Danger zone */}
            <div className="card animate-fade-in-up stagger-4" style={{ padding: '24px', borderColor: 'rgba(244,63,94,0.2)', background: 'rgba(244,63,94,0.03)' }}>
              <h2 style={{ fontSize: '12px', color: 'var(--rose)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px' }}>Danger Zone</h2>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Re-uploading your CV will clear your current session and restart the onboarding process.
              </p>
              <button className="btn btn-danger" onClick={() => { clearSession(); window.location.href = '/onboarding/upload'; }} style={{ gap: '8px' }}>
                <RefreshCw size={16} />
                Re-upload CV
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
