'use client';

import { useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, CheckCircle2, AlertCircle, Zap } from 'lucide-react';
import { cvApi } from '@/lib/api/users';
import { useUserStore } from '@/lib/store/userStore';
import { useUIStore } from '@/lib/store/uiStore';
import type { ParsedCV } from '@/lib/types/user';

type UploadState = 'idle' | 'dragging' | 'uploading' | 'parsing' | 'success' | 'error';

const PARSING_MESSAGES = [
  'Reading your PDF…',
  'Extracting skills and experience…',
  'Parsing education and certifications…',
  'Building your profile…',
  'Finalizing structured data…',
];

export default function CVUploadPage() {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [parsedCV, setParsedCV] = useState<ParsedCV | null>(null);
  const [msgIdx, setMsgIdx] = useState(0);
  const [fileName, setFileName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const router = useRouter();
  const { setSession } = useUserStore();
  const { addToast } = useUIStore();

  const startParsingMessages = () => {
    setMsgIdx(0);
    intervalRef.current = setInterval(() => {
      setMsgIdx((i) => (i + 1) % PARSING_MESSAGES.length);
    }, 2000);
  };

  const stopParsingMessages = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
  };

  const handleFile = useCallback(async (file: File) => {
    if (file.type !== 'application/pdf') {
      setErrorMsg('Please upload a PDF file.');
      setUploadState('error');
      return;
    }
    setFileName(file.name);
    setUploadState('uploading');

    try {
      setUploadState('parsing');
      startParsingMessages();
      const result = await cvApi.upload(file);
      stopParsingMessages();

      setParsedCV(result.parsed_cv);
      setSession({
        user_id: result.user_id,
        name: result.parsed_cv.name,
        career_level: result.parsed_cv.career_level,
        onboarding_completed: false,
      });
      setUploadState('success');
    } catch (err: unknown) {
      stopParsingMessages();
      const msg = err instanceof Error ? err.message : 'Failed to parse CV. Please try again.';
      setErrorMsg(msg);
      setUploadState('error');
    }
  }, [setSession]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setUploadState('idle');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleContinue = () => {
    addToast('Profile created! Set your preferences.', 'success');
    router.push('/onboarding/preferences');
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px',
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: '48px', textAlign: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'center', marginBottom: '24px' }}>
          <div
            style={{
              width: '40px', height: '40px', background: 'var(--brand)',
              borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 20px rgba(99,102,241,0.4)',
            }}
          >
            <Zap size={22} color="white" />
          </div>
          <span style={{ fontFamily: "'Sora', sans-serif", fontWeight: 700, fontSize: '20px', color: 'var(--text-primary)' }}>
            Career Coach
          </span>
        </div>

        {/* Step indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', marginBottom: '32px' }}>
          {[1, 2].map((step) => (
            <div key={step} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: '28px', height: '28px', borderRadius: '50%',
                  background: step === 1 ? 'var(--brand)' : 'var(--surface-alt)',
                  border: `2px solid ${step === 1 ? 'var(--brand)' : 'var(--border)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '12px', fontWeight: 600,
                  color: step === 1 ? 'white' : 'var(--text-muted)',
                }}
              >
                {step}
              </div>
              <span style={{ fontSize: '13px', color: step === 1 ? 'var(--text-primary)' : 'var(--text-subtle)', fontWeight: step === 1 ? 600 : 400 }}>
                {step === 1 ? 'Upload CV' : 'Preferences'}
              </span>
              {step === 1 && <div style={{ width: '32px', height: '1px', background: 'var(--border)' }} />}
            </div>
          ))}
        </div>

        <h1 style={{ fontSize: '32px', marginBottom: '12px' }}>Upload Your CV</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '15px' }}>
          AI will parse it into a structured profile in seconds.
        </p>
      </div>

      {/* Upload area */}
      <div style={{ width: '100%', maxWidth: '560px' }}>
        {uploadState === 'idle' || uploadState === 'dragging' ? (
          <div
            className={`dropzone ${uploadState === 'dragging' ? 'dropzone-active' : ''}`}
            style={{
              padding: '64px 32px',
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '16px',
            }}
            onDragOver={(e) => { e.preventDefault(); setUploadState('dragging'); }}
            onDragLeave={() => setUploadState('idle')}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              style={{ display: 'none' }}
              onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }}
            />
            <div
              style={{
                width: '72px', height: '72px',
                background: 'var(--brand-dim)',
                border: '2px solid rgba(99,102,241,0.3)',
                borderRadius: '16px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              className={uploadState === 'dragging' ? 'animate-bounce-subtle' : ''}
            >
              <Upload size={32} color="var(--brand-light)" />
            </div>
            <div>
              <p style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                Drop your PDF here, or <span style={{ color: 'var(--brand-light)' }}>browse</span>
              </p>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>PDF files only · Max 10MB</p>
            </div>
          </div>
        ) : uploadState === 'uploading' || uploadState === 'parsing' ? (
          <div
            className="card card-glow"
            style={{
              padding: '56px 32px',
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '24px',
            }}
          >
            <div
              style={{
                width: '80px', height: '80px',
                borderRadius: '50%',
                background: 'var(--brand-dim)',
                border: '2px solid rgba(99,102,241,0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              className="brain-pulse"
            >
              <Zap size={36} color="var(--brand-light)" className="animate-pulse-glow" />
            </div>
            <div>
              <div className="ai-loading-text" style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>
                {PARSING_MESSAGES[msgIdx]}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {fileName}
              </div>
            </div>
            <div
              className="progress-track"
              style={{ width: '100%', height: '4px' }}
            >
              <div
                className="progress-fill"
                style={{
                  width: '60%',
                  background: 'linear-gradient(90deg, var(--brand), var(--brand-light))',
                  animation: 'shimmer 2s linear infinite',
                  backgroundSize: '200% auto',
                }}
              />
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              This may take 10–20 seconds…
            </p>
          </div>
        ) : uploadState === 'error' ? (
          <div
            className="card"
            style={{
              padding: '40px 32px',
              textAlign: 'center',
              borderColor: 'rgba(244,63,94,0.3)',
              background: 'rgba(244,63,94,0.05)',
            }}
          >
            <AlertCircle size={48} color="var(--rose)" style={{ marginBottom: '16px' }} />
            <h3 style={{ fontSize: '18px', marginBottom: '10px', color: 'var(--rose)' }}>Upload Failed</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '24px', fontSize: '14px' }}>{errorMsg}</p>
            <button className="btn btn-primary" onClick={() => setUploadState('idle')}>
              Try Again
            </button>
          </div>
        ) : (
          /* Success state */
          <div className="card card-glow animate-scale-in" style={{ padding: '32px' }}>
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                marginBottom: '24px', paddingBottom: '20px',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <CheckCircle2 size={28} color="var(--emerald)" />
              <div>
                <div style={{ fontSize: '16px', fontWeight: 600 }}>Profile Extracted!</div>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{fileName}</div>
              </div>
            </div>

            {parsedCV && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '28px' }}>
                <ProfileRow label="Name" value={parsedCV.name ?? '—'} />
                <ProfileRow label="Email" value={parsedCV.email ?? '—'} />
                <ProfileRow label="Career Level" value={parsedCV.career_level ?? '—'} />
                <ProfileRow label="Experience" value={parsedCV.years_of_experience != null ? `${parsedCV.years_of_experience} years` : '—'} />
                <ProfileRow label="Education" value={parsedCV.education ?? '—'} />
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                    Skills Detected
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {parsedCV.skills.slice(0, 8).map((s) => (
                      <span key={s} className="chip chip-skill">{s}</span>
                    ))}
                    {parsedCV.skills.length > 8 && (
                      <span className="chip chip-neutral">+{parsedCV.skills.length - 8} more</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleContinue}>
              Looks Good! Set Preferences
              <span style={{ marginLeft: '4px' }}>→</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', width: '100px', flexShrink: 0, paddingTop: '2px' }}>
        {label}
      </div>
      <div style={{ fontSize: '14px', color: 'var(--text-primary)', fontWeight: 500 }}>{value}</div>
    </div>
  );
}
