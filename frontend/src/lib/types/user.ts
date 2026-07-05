export interface ParsedCV {
  name?: string;
  email?: string;
  skills: string[];
  tools: string[];
  years_of_experience?: number;
  career_level?: string;
  education?: string;
  preferred_location?: string;
  completed_courses?: string[];
  projects?: string[];
  certifications?: string[];
}

export interface UserProfileOut {
  id: number;
  name: string;
  email?: string;
  years_of_experience: number;
  career_level: string;
  education?: string;
  preferred_location?: string;
  skills: string[];
  tools: string[];
  completed_courses: string[];
  projects: string[];
  certifications: string[];
  desired_roles: string[];
  job_titles: string[];
  job_categories: string[];
  workplace_settings: string[];
}

export interface ProfilePreferencesIn {
  desired_roles?: string[];
  job_titles?: string[];
  job_categories?: string[];
  workplace_settings?: string[];
  preferred_location?: string;
}
