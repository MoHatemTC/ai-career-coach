'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { X, CheckCircle2, Zap, SkipForward } from 'lucide-react';
import { usersApi } from '@/lib/api/users';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';

const WORKPLACE_OPTIONS = [
  { value: 'remote', label: 'Remote', emoji: '🌍' },
  { value: 'hybrid', label: 'Hybrid', emoji: '🏠' },
  { value: 'on_site', label: 'On-site', emoji: '🏢' },
];

function TagInput({
  label,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (vals: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim().toLowerCase();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput('');
  };

  const remove = (v: string) => onChange(values.filter((x) => x !== v));

  return (
    <div>
      <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>
        {label}
      </label>
      <div
        style={{
          background: 'var(--surface-alt)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius)',
          padding: '10px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          minHeight: '48px',
        }}
      >
        {values.map((v) => (
          <span
            key={v}
            className="chip chip-skill"
            style={{ cursor: 'pointer' }}
            onClick={() => remove(v)}
          >
            {v} <X size={10} />
          </span>
        ))}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          style={{
            background: 'none',
            border: 'none',
            outline: 'none',
            color: 'var(--text-primary)',
            fontSize: '13px',
            minWidth: '140px',
            flex: 1,
          }}
        />
      </div>
      <p style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '4px' }}>Press Enter to add</p>
    </div>
  );
}

export default function PreferencesPage() {
  const { session, setSession } = useUserStore();
  const { addToast } = useUIStore();
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  const [desiredRoles, setDesiredRoles] = useState<string[]>([]);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [jobCategories, setJobCategories] = useState<string[]>([]);
  const [workplaceSettings, setWorkplaceSettings] = useState<string[]>([]);
  const [preferredLocation, setPreferredLocation] = useState('');

  const toggleWorkplace = (value: string) => {
    setWorkplaceSettings((prev) =>
      prev.includes(value) ? prev.filter((x) => x !== value) : [...prev, value],
    );
  };

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
      setSession({ ...session, onboarding_completed: true });
      addToast('Preferences saved! Welcome to Career Coach 🎉', 'success');
      router.push('/dashboard');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save preferences';
      addToast(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    if (session) setSession({ ...session, onboarding_completed: true });
    router.push('/dashboard');
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '48px 32px',
      }}
    >
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '48px' }}>
        <div style={{ width: '36px', height: '36px', background: 'var(--brand)', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 16px rgba(99,102,241,0.4)' }}>
          <Zap size={20} color="white" />
        </div>
        <span style={{ fontFamily: "'Sora', sans-serif", fontWeight: 700, fontSize: '18px', background: 'linear-gradient(135deg, #818cf8, #6366f1)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
          Career Coach
        </span>
      </div>

      {/* Step indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '40px' }}>
        {[1, 2].map((step) => (
          <div key={step} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '28px', height: '28px', borderRadius: '50%',
                background: step === 1 ? 'var(--emerald)' : 'var(--brand)',
                border: `2px solid ${step === 1 ? 'var(--emerald)' : 'var(--brand)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '12px', fontWeight: 600, color: 'white',
              }}
            >
              {step === 1 ? <CheckCircle2 size={14} /> : '2'}
            </div>
            <span style={{ fontSize: '13px', color: step === 2 ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: step === 2 ? 600 : 400 }}>
              {step === 1 ? 'Upload CV' : 'Preferences'}
            </span>
            {step === 1 && <div style={{ width: '32px', height: '1px', background: 'var(--emerald)', opacity: 0.4 }} />}
          </div>
        ))}
      </div>

      <div style={{ width: '100%', maxWidth: '560px' }}>
        <h1 style={{ fontSize: '28px', marginBottom: '8px', textAlign: 'center' }}>
          Set Your Preferences
        </h1>
        <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginBottom: '36px', fontSize: '14px' }}>
          Help us find the best job matches for you. You can update these any time.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <TagInput
            label="Desired Roles"
            values={desiredRoles}
            onChange={setDesiredRoles}
            placeholder="e.g. AI Engineer, ML Engineer…"
          />

          <TagInput
            label="Job Titles"
            values={jobTitles}
            onChange={setJobTitles}
            placeholder="e.g. Senior Backend Engineer…"
          />

          <TagInput
            label="Job Categories"
            values={jobCategories}
            onChange={setJobCategories}
            placeholder="e.g. Machine Learning, Software Engineering…"
          />

          {/* Workplace */}
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '10px' }}>
              Workplace Settings
            </label>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              {WORKPLACE_OPTIONS.map(({ value, label, emoji }) => {
                const selected = workplaceSettings.includes(value);
                return (
                  <button
                    key={value}
                    onClick={() => toggleWorkplace(value)}
                    className={`btn ${selected ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                      gap: '6px',
                      boxShadow: selected ? '0 0 16px rgba(99,102,241,0.3)' : 'none',
                    }}
                  >
                    {emoji} {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Location */}
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>
              Preferred Location
            </label>
            <input
              className="input"
              value={preferredLocation}
              onChange={(e) => setPreferredLocation(e.target.value)}
              placeholder="e.g. Cairo, Egypt"
            />
          </div>

          <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
            <button
              className="btn btn-ghost"
              onClick={handleSkip}
              style={{ flex: 1, gap: '6px' }}
            >
              <SkipForward size={16} />
              Skip for now
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving}
              style={{ flex: 2 }}
            >
              {saving ? 'Saving…' : 'Save & Go to Dashboard'}
              {!saving && ' →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
