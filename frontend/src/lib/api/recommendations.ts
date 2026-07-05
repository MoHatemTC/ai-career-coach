import { apiClient } from './client';
import type { RecommendationResponse, AnalyzeMatchResponse } from '../types/tracking';

export const recommendationsApi = {
  get: (userId: number): Promise<RecommendationResponse> => apiClient.get(`/recommendations/${userId}`),
};

export const matchesApi = {
  analyze: (body: { user_id: number; job_id: number }): Promise<AnalyzeMatchResponse> =>
    apiClient.post('/matches/analyze', body),
};
