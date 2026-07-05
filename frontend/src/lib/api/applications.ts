import { apiClient } from './client';
import type { ApplicationResponse } from '../types/tracking';

export const applicationsApi = {
  generate: (userId: number, jobId: number): Promise<ApplicationResponse> =>
    apiClient.post('/applications/', { user_id: userId, job_id: jobId }),
};
