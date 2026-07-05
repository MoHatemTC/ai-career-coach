import { apiClient } from './client';
import type { MarketTrendsOut, LabeledCount } from '../types/trends';

export const trendsApi = {
  getAll: (): Promise<MarketTrendsOut> => apiClient.get('/trends'),
  getSkills: (limit = 20): Promise<LabeledCount[]> => apiClient.get(`/trends/skills?limit=${limit}`),
};
