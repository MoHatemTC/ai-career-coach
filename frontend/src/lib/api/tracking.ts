import { apiClient } from './client';
import type { JobTrackingOut, TrackingStatus, TrackingHistoryOut, TrackingListResponse, ApplicationMaterialsResponse } from '../types/tracking';

export const trackingApi = {
  list: (userId: number): Promise<TrackingListResponse> => apiClient.get(`/tracking?user_id=${userId}`),
  getForJob: (jobId: number, userId: number): Promise<JobTrackingOut> =>
    apiClient.get(`/tracking/jobs/${jobId}?user_id=${userId}`),
  update: (jobId: number, userId: number, status: TrackingStatus): Promise<JobTrackingOut> =>
    apiClient.put(`/tracking/jobs/${jobId}`, { user_id: userId, status }),
  getHistory: (jobId: number, userId: number): Promise<TrackingHistoryOut> =>
    apiClient.get(`/tracking/jobs/${jobId}/history?user_id=${userId}`),
  getMaterials: (jobId: number, userId: number): Promise<ApplicationMaterialsResponse> =>
    apiClient.get(`/tracking/jobs/${jobId}/application-materials?user_id=${userId}`),
};
