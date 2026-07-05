export function cx(...classes: (string | undefined | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function formatSalary(min?: number, max?: number, currency = 'EGP', period?: string | null): string {
  if (!min && !max) return 'Not disclosed';
  const p = period ? `/${period}` : '';
  if (min && max) return `${min.toLocaleString()} - ${max.toLocaleString()} ${currency}${p}`;
  return `${(min || max)!.toLocaleString()} ${currency}${p}`;
}

export function scoreColor(score: number): string {
  if (score >= 70) return '#22AAA6';
  if (score >= 40) return '#FFD400';
  return '#E24B4A';
}

export function scoreLabel(score: number): string {
  if (score >= 70) return 'Strong match';
  if (score >= 40) return 'Partial match';
  return 'Weak match';
}

export function scoreClass(score: number): string {
  if (score >= 70) return 'score-high';
  if (score >= 40) return 'score-mid';
  return 'score-low';
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    reviewed: 'Reviewed', saved: 'Saved', shortlisted: 'Shortlisted',
    applied: 'Applied', rejected: 'Rejected', ignored: 'Ignored',
  };
  return labels[status] || status;
}

export function statusClass(status: string): string {
  return `status-${status}`;
}
