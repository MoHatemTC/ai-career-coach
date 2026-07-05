'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Briefcase,
  Sparkles,
  GitBranch,
  TrendingUp,
  User,
  Zap,
  ChevronLeft,
} from 'lucide-react';
import { useUIStore } from '@/lib/store/uiStore';
import { useUserStore } from '@/lib/store/userStore';
import { cx } from '@/lib/utils/score';

const navItems = [
  { href: '/dashboard',       icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/jobs',            icon: Briefcase,       label: 'Job Board' },
  { href: '/recommendations', icon: Sparkles,        label: 'AI Picks' },
  { href: '/pipeline',        icon: GitBranch,       label: 'My Pipeline' },
  { href: '/trends',          icon: TrendingUp,      label: 'Market Trends' },
  { href: '/profile',         icon: User,            label: 'Profile' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { isSidebarOpen, toggleSidebar } = useUIStore();
  const { session } = useUserStore();

  if (!isSidebarOpen) {
    return (
      <div
        style={{
          width: '60px',
          background: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          height: '100vh',
          position: 'sticky',
          top: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          paddingTop: '20px',
          gap: '4px',
          flexShrink: 0,
        }}
      >
        <button
          onClick={toggleSidebar}
          className="btn btn-ghost btn-icon"
          style={{ marginBottom: '16px', transform: 'rotate(180deg)' }}
        >
          <ChevronLeft size={18} />
        </button>
        {navItems.map(({ href, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cx('nav-item', pathname.startsWith(href) ? 'active' : '')}
            style={{ padding: '10px', justifyContent: 'center', width: '44px' }}
            title={navItems.find(n => n.href === href)?.label}
          >
            <Icon size={18} />
          </Link>
        ))}
      </div>
    );
  }

  return (
    <aside className="sidebar" style={{ padding: '20px 12px' }}>
      {/* Logo */}
      <div style={{ marginBottom: '32px', paddingLeft: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
              fontSize: '16px',
              background: 'linear-gradient(135deg, #818cf8, #6366f1)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Career Coach
          </span>
          <button
            onClick={toggleSidebar}
            className="btn btn-ghost btn-icon"
            style={{ marginLeft: 'auto' }}
          >
            <ChevronLeft size={16} />
          </button>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cx('nav-item', isActive ? 'active' : '')}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* User session */}
      {session && (
        <div
          style={{
            marginTop: 'auto',
            paddingTop: '24px',
            borderTop: '1px solid var(--border)',
          }}
        >
          <div
            style={{
              background: 'var(--surface-alt)',
              borderRadius: 'var(--radius)',
              padding: '12px',
              border: '1px solid var(--border)',
            }}
          >
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: 'var(--brand-dim)',
                border: '2px solid rgba(99,102,241,0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '14px',
                fontWeight: 700,
                color: 'var(--brand-light)',
                marginBottom: '8px',
              }}
            >
              {(session.name ?? 'U').charAt(0).toUpperCase()}
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {session.name ?? 'User'}
            </div>
            <div
              className="chip chip-skill"
              style={{ marginTop: '4px', fontSize: '11px' }}
            >
              {session.career_level}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
