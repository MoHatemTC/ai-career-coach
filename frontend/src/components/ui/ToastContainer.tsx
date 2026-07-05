'use client';

import { useUIStore } from '@/lib/store/uiStore';
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react';

const icons = {
  success: <CheckCircle2 size={18} style={{ color: 'var(--emerald)' }} />,
  error:   <XCircle     size={18} style={{ color: 'var(--rose)' }} />,
  info:    <Info        size={18} style={{ color: 'var(--brand-light)' }} />,
  warning: <AlertTriangle size={18} style={{ color: 'var(--amber)' }} />,
};

const borderColors = {
  success: 'rgba(16,185,129,0.3)',
  error:   'rgba(244,63,94,0.3)',
  info:    'rgba(99,102,241,0.3)',
  warning: 'rgba(245,158,11,0.3)',
};

export default function ToastContainer() {
  const { toasts, removeToast } = useUIStore();

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="toast"
          style={{ borderColor: borderColors[t.type] }}
        >
          {icons[t.type]}
          <span style={{ flex: 1, color: 'var(--text-primary)', fontSize: '14px' }}>
            {t.message}
          </span>
          <button
            onClick={() => removeToast(t.id)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-subtle)',
              padding: '2px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
