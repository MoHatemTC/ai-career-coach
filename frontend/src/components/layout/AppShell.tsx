'use client';

import { ReactNode } from 'react';
import Sidebar from './Sidebar';
import { useUserStore } from '@/lib/store/userStore';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';

interface AppShellProps {
  children: ReactNode;
}

const PUBLIC_ROUTES = ['/', '/onboarding/upload', '/onboarding/preferences'];

export default function AppShell({ children }: AppShellProps) {
  const { session, isLoading } = useUserStore();
  const pathname = usePathname();
  const router = useRouter();

  const isPublicRoute = PUBLIC_ROUTES.some((r) => pathname === r);

  useEffect(() => {
    if (!isLoading && !session && !isPublicRoute) {
      router.replace('/onboarding/upload');
    }
  }, [isLoading, session, isPublicRoute, router]);

  if (isPublicRoute) {
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg)',
        }}
      >
        <div
          style={{
            width: '40px',
            height: '40px',
            border: '3px solid var(--border)',
            borderTopColor: 'var(--brand)',
            borderRadius: '50%',
          }}
          className="animate-spin"
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
        {children}
      </main>
    </div>
  );
}
