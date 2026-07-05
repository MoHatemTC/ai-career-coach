export type TrackingStatus = 'reviewed' | 'saved' | 'shortlisted' | 'applied' | 'rejected' | 'ignored';

export interface JobTrackingOut {
  id: number;
  job_id: number;
  user_id: number;
  status: TrackingStatus;
  created_at: string;
  updated_at: string;
}

export interface TrackingEvent {
  id: number;
  user_id: number;
  job_id: number;
  from_status?: TrackingStatus | null;
  to_status: TrackingStatus;
  created_at: string;
}

export interface TrackingHistoryOut {
  job_id: number;
  user_id: number;
  events: TrackingEvent[];
}

export interface TrackingListResponse {
  items: JobTrackingOut[];
  total: number;
}

export interface AnalyzeMatchResponse {
  id: number;
  user_id: number;
  job_id: number;
  match_score: number;
  match_explanation: string;
  missing_skills: string[];
  strengths: string[];
  cv_tailoring_suggestion: string;
  cover_letter_draft: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CVTailoringResult {
  tailored_summary: string;
  highlighted_skills: string[];
  missing_skills: string[];
  bullet_point_suggestions: string[];
}

export interface CoverLetterResult {
  draft_content: string;
  tone_analysis: string;
}

export interface ApplicationResponse {
  candidate_id: number;
  job_id: number;
  cv_tailoring: CVTailoringResult;
  cover_letter: CoverLetterResult;
  status: string;
  disclaimer?: string;
}

export interface ApplicationMaterialsResponse {
  job_id: number;
  user_id: number;
  cv_tailoring_suggestion: CVTailoringResult | null;
  cover_letter_draft: CoverLetterResult | null;
  reviewed_at?: string | null;
}

export interface RecommendationJob {
  id: number;
  title: string;
  company: string;
  location: string;
  url?: string | null;
}

export interface RecommendationItem {
  job: RecommendationJob;
  total_score: number;
  explanation: string;
  strengths: string[];
  missing_skills: string[];
  vector_distance: number;
}

export interface RecommendationResponse {
  user_id: number;
  recommendations: RecommendationItem[];
}
