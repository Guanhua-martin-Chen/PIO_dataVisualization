export type ForecastUpdateStatus =
  | "validated"
  | "validation_failed"
  | "queued"
  | "running"
  | "qa_failed"
  | "awaiting_approval"
  | "publishing"
  | "published"
  | "failed";

export type ForecastUpdateFile = {
  role: "capstone" | "hma_plan" | "gma_plan" | "kia_plan";
  filename: string;
  size_bytes: number;
  sha256: string;
  valid: boolean;
  summary: string;
  details: Record<string, unknown>;
};

export type ForecastUpdateJob = {
  job_id: string;
  status: ForecastUpdateStatus;
  created_at: string;
  updated_at: string;
  files: ForecastUpdateFile[];
  progress: { stage: string; percent: number; message: string };
  qa: {
    status: string;
    checks_passed: number;
    checks_total: number;
    checks: Array<{ check: string; passes: boolean }>;
  } | null;
  draft: {
    actual_data_through: string;
    forecast_start: string;
    forecast_end: string;
    registry_version: string;
    sponsor_workbook_filename: string;
    sponsor_workbook_sha256: string;
  } | null;
  approved_run_id: string | null;
  error: string | null;
};

export type ForecastUpdateJobEnvelope = { job: ForecastUpdateJob };
