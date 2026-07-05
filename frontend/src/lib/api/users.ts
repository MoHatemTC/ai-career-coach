import { apiClient } from './client';
import type { UserProfileOut, ParsedCV, ProfilePreferencesIn } from '../types/user';

export const cvApi = {
  upload: async (file: File): Promise<{ user_id: number | null; parsed_cv: ParsedCV }> => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/cv', formData);
  },
};

export const usersApi = {
  getProfile: (userId: number): Promise<UserProfileOut> => apiClient.get(`/users/${userId}`),
  updatePreferences: (userId: number, prefs: ProfilePreferencesIn): Promise<UserProfileOut> =>
    apiClient.patch(`/users/${userId}/preferences`, prefs),
};
