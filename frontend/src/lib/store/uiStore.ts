'use client';
import { create } from 'zustand';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface UIStoreState {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType) => void;
  removeToast: (id: number) => void;
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
}

let toastCounter = 0;

export const useUIStore = create<UIStoreState>((set) => ({
  toasts: [],
  addToast: (message, type = 'info') =>
    set((state) => ({ toasts: [...state.toasts, { id: ++toastCounter, message, type }] })),
  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  isSidebarOpen: true,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
}));

export function UIStoreProvider({ children }: { children: React.ReactNode }) {
  return children;
}
