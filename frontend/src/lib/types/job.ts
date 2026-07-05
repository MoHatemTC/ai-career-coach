export interface JobOut {
  id: number;
  title: string;
  company: string;
  location?: string;
  city?: string;
  area?: string;
  description: string;
  required_skills: string[];
  experience_level?: string;
  work_mode?: string;
  salary_hidden?: boolean;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  salary_period?: string;
  source: string;
  url?: string;
  posted_date?: string;
  created_at: string;
}
