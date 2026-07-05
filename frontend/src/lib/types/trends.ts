export interface LabeledCount {
  label: string;
  count: number;
}

export interface PostingVolumePoint {
  period: string;
  count: number;
}

export interface SalaryStat {
  currency: string;
  period?: string | null;
  count: number;
  min: number;
  max: number;
  avg: number;
}

export interface MarketTrendsOut {
  top_companies: LabeledCount[];
  experience_levels: LabeledCount[];
  work_types: LabeledCount[];
  top_categories: LabeledCount[];
  countries: LabeledCount[];
  job_types: LabeledCount[];
  posting_volume: PostingVolumePoint[];
  top_skills: LabeledCount[];
  salary_stats: SalaryStat[];
}
