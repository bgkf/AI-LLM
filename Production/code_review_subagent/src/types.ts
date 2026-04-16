export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type Category = "security" | "logic" | "style" | "performance" | "testing" | "comments";
export type Verdict = "APPROVE" | "REQUEST_CHANGES" | "NEEDS_DISCUSSION";
export type ReviewMode = "file" | "diff";

export interface ReviewIssue {
  id: string;
  severity: Severity;
  category: Category;
  line: number | null;
  title: string;
  description: string;
  suggestion: string;
  code_example?: string;
}

export interface ReviewStats {
  total_issues: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface ReviewMetadata {
  language: string;
  review_mode: ReviewMode;
  lines_reviewed: number;
}

export interface ReviewResult {
  summary: string;
  verdict: Verdict;
  stats: ReviewStats;
  issues: ReviewIssue[];
  positive_highlights: string[];
  review_metadata: ReviewMetadata;
}
