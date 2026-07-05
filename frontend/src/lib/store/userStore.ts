'use client';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Session {
  user_id: number | null;
  name?: string;
  career_level?: string;
  onboarding_completed?: boolean;
}

interface UserStoreState {
  session: Session;
  isLoading: boolean;
  setSession: (session: Session) => void;
  clearSession: () => void;
  _setLoading: (loading: boolean) => void;
}

const EMPTY_SESSION: Session = { user_id: null };

export const useUserStore = create<UserStoreState>()(
  persist(
    (set) => ({
      session: EMPTY_SESSION,
      isLoading: true,
      setSession: (session) => set({ session }),
      clearSession: () => set({ session: EMPTY_SESSION }),
      _setLoading: (loading) => set({ isLoading: loading }),
    }),
    {
      name: 'career-coach-session',
      partialize: (state) => ({ session: state.session }),
      onRehydrateStorage: () => (state) => {
        state?._setLoading(false);
      },
    }
  )
);

export function UserStoreProvider({ children }: { children: React.ReactNode }) {
  return children;
}
