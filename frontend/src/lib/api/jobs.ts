import { apiClient } from './client';
import type { JobOut } from '../types/job';

export const jobsApi = {
  list: (params: { source?: string; experience_level?: string; limit?: number; offset?: number } = {}): Promise<{ jobs: JobOut[]; total: number }> => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])
    ).toString();
    return apiClient.get(`/jobs${qs ? `?${qs}` : ''}`);
  },
};
