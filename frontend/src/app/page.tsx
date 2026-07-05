'use client';

import Link from 'next/link';
import { ArrowRight, Upload, Sparkles, TrendingUp, Zap, Brain, Target, FileText, CheckCircle2 } from 'lucide-react';

const features = [
  {
    icon: Brain,
    title: 'AI Job Matching',
    desc: 'Two-stage pipeline: vector similarity pre-filter + LLM re-ranking delivers your top 10 matches.',
    color: 'var(--brand)',
    glow: 'rgba(99,102,241,0.2)',
  },
  {
    icon: Target,
    title: 'Gap Analysis',
    desc: 'See exactly where you stand: score breakdown, strengths, missing skills, and actionable advice.',
    color: 'var(--emerald)',
    glow: 'rgba(16,185,129,0.2)',
  },
  {
    icon: FileText,
    title: 'Application Materials',
    desc: 'AI-generated tailored CV suggestions and cover letter drafts, ready for your human review.',
    color: 'var(--amber)',
    glow: 'rgba(245,158,11,0.2)',
  },
  {
    icon: TrendingUp,
    title: 'Market Intelligence',
    desc: 'Live market trends: top skills, salary stats, hiring companies, and posting volume charts.',
    color: '#3b82f6',
    glow: 'rgba(59,130,246,0.2)',
  },
];

const steps = [
  { n: '01', title: 'Upload Your CV', desc: 'Drop your PDF — AI parses it into a structured profile in seconds.' },
  { n: '02', title: 'Get AI Matches', desc: 'Receive ranked job recommendations scored by fit across skills, experience, and preferences.' },
  { n: '03', title: 'Apply with Confidence', desc: 'Generate tailored materials, track your pipeline, and land the right role.' },
];

export default function LandingPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      {/* Nav */}
      <nav
        className="glass"
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 50,
          padding: '16px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              background: 'var(--brand)',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(99,102,241,0.4)',
            }}
          >
            <Zap size={18} color="white" />
          </div>
          <span
            style={{
              fontFamily: "'Sora', sans-serif",
              fontWeight: 700,
              fontSize: '18px',
              background: 'linear-gradient(135deg, #818cf8, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Career Coach
          </span>
        </div>
        <Link href="/onboarding/upload" className="btn btn-primary btn-sm">
          Get Started <ArrowRight size={14} />
        </Link>
      </nav>

      {/* Hero */}
      <section
        className="hero-gradient"
        style={{
          padding: '120px 32px 100px',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Glow orbs */}
        <div
          style={{
            position: 'absolute',
            top: '10%',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '600px',
            height: '600px',
            background: 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: '30%',
            left: '15%',
            width: '300px',
            height: '300px',
            background: 'radial-gradient(circle, rgba(139,92,246,0.1) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: '20%',
            right: '15%',
            width: '300px',
            height: '300px',
            background: 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        <div style={{ position: 'relative', zIndex: 1, maxWidth: '800px', margin: '0 auto' }}>
          <div
            className="chip chip-skill animate-fade-in"
            style={{ display: 'inline-flex', marginBottom: '24px', fontSize: '13px' }}
          >
            <Sparkles size={12} /> AI-Powered Career Acceleration
          </div>

          <h1
            className="animate-fade-in-up"
            style={{
              fontSize: 'clamp(40px, 6vw, 72px)',
              fontWeight: 700,
              lineHeight: 1.1,
              marginBottom: '24px',
              letterSpacing: '-0.02em',
            }}
          >
            Land Your{' '}
            <span className="gradient-text">Dream Role</span>
            <br />
            with the Power of AI
          </h1>

          <p
            className="animate-fade-in-up stagger-2"
            style={{
              fontSize: '18px',
              color: 'var(--text-muted)',
              maxWidth: '600px',
              margin: '0 auto 40px',
              lineHeight: 1.7,
            }}
          >
            Upload your CV, get AI-ranked job matches, gap analysis, tailored application materials, and market intelligence — all in one place.
          </p>

          <div
            className="animate-fade-in-up stagger-3"
            style={{ display: 'flex', gap: '16px', justifyContent: 'center', flexWrap: 'wrap' }}
          >
            <Link href="/onboarding/upload" className="btn btn-primary btn-lg">
              <Upload size={18} />
              Upload Your CV
              <ArrowRight size={18} />
            </Link>
            <Link href="/trends" className="btn btn-secondary btn-lg">
              <TrendingUp size={18} />
              Explore Market
            </Link>
          </div>

          {/* Stats row */}
          <div
            className="animate-fade-in-up stagger-4"
            style={{
              display: 'flex',
              gap: '40px',
              justifyContent: 'center',
              marginTop: '64px',
              flexWrap: 'wrap',
            }}
          >
            {[
              { label: 'Jobs Indexed', value: '10,000+' },
              { label: 'Match Accuracy', value: '92%' },
              { label: 'Sources', value: 'Wuzzuf & more' },
            ].map(({ label, value }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div
                  style={{
                    fontSize: '28px',
                    fontWeight: 700,
                    fontFamily: "'Sora', sans-serif",
                    background: 'linear-gradient(135deg, #818cf8, #10b981)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                  }}
                >
                  {value}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section style={{ padding: '80px 32px', maxWidth: '1100px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '56px' }}>
          <h2 style={{ fontSize: '36px', marginBottom: '12px' }}>
            From CV to Offer in{' '}
            <span className="gradient-text">3 Steps</span>
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '16px' }}>
            A streamlined AI-powered workflow designed to get you hired faster.
          </p>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '24px',
          }}
        >
          {steps.map(({ n, title, desc }, i) => (
            <div
              key={n}
              className={`card animate-fade-in-up stagger-${i + 1}`}
              style={{ padding: '32px', position: 'relative', overflow: 'hidden' }}
            >
              <div
                style={{
                  position: 'absolute',
                  top: '-10px',
                  right: '20px',
                  fontSize: '72px',
                  fontWeight: 800,
                  fontFamily: "'Sora', sans-serif",
                  color: 'rgba(99,102,241,0.08)',
                  lineHeight: 1,
                  userSelect: 'none',
                }}
              >
                {n}
              </div>
              <div
                style={{
                  fontSize: '32px',
                  fontWeight: 800,
                  fontFamily: "'Sora', sans-serif",
                  color: 'rgba(99,102,241,0.5)',
                  marginBottom: '16px',
                }}
              >
                {n}
              </div>
              <h3 style={{ fontSize: '20px', marginBottom: '10px' }}>{title}</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '14px', lineHeight: 1.7 }}>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section
        style={{
          padding: '80px 32px',
          background: 'linear-gradient(180deg, transparent, rgba(17,24,39,0.8), transparent)',
        }}
      >
        <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: '56px' }}>
            <h2 style={{ fontSize: '36px', marginBottom: '12px' }}>
              Everything You Need to{' '}
              <span className="gradient-text">Succeed</span>
            </h2>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: '20px',
            }}
          >
            {features.map(({ icon: Icon, title, desc, color, glow }, i) => (
              <div
                key={title}
                className={`card card-interactive animate-fade-in-up stagger-${i + 1}`}
                style={{ padding: '28px', cursor: 'default' }}
              >
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: `rgba(0,0,0,0.3)`,
                    border: `1px solid ${color}40`,
                    boxShadow: `0 0 20px ${glow}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '20px',
                  }}
                >
                  <Icon size={24} color={color} />
                </div>
                <h3 style={{ fontSize: '17px', marginBottom: '10px' }}>{title}</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', lineHeight: 1.7 }}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section style={{ padding: '80px 32px', textAlign: 'center' }}>
        <div
          className="card card-glow"
          style={{
            maxWidth: '600px',
            margin: '0 auto',
            padding: '56px 40px',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.05))',
          }}
        >
          <CheckCircle2
            size={48}
            color="var(--brand-light)"
            style={{ marginBottom: '24px' }}
            className="animate-bounce-subtle"
          />
          <h2 style={{ fontSize: '32px', marginBottom: '16px' }}>
            Ready to Accelerate Your Career?
          </h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '32px', fontSize: '15px' }}>
            Upload your CV now — it takes 30 seconds and the AI does the rest.
          </p>
          <Link href="/onboarding/upload" className="btn btn-primary btn-lg">
            <Upload size={18} />
            Get Started Free
            <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          borderTop: '1px solid var(--border)',
          padding: '24px 32px',
          textAlign: 'center',
          color: 'var(--text-subtle)',
          fontSize: '13px',
        }}
      >
        Career Coach — AI-Powered Career Acceleration · Built with FastAPI + Next.js
      </footer>
    </div>
  );
}
