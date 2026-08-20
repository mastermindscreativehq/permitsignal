-- 0007_add_case_reports.sql
-- Case Report History: stores generated PDF reports per application.
-- Each report is a versioned artifact linked to an application_number.
-- Source data (the leads table) is NEVER mutated by report generation.

CREATE TABLE IF NOT EXISTS public.case_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_number TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    generated_by TEXT NOT NULL DEFAULT 'api',
    pdf_base64 TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    checksum TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for fast lookup by application
CREATE INDEX IF NOT EXISTS idx_case_reports_application_number
    ON public.case_reports (application_number);

-- Composite index for version ordering
CREATE INDEX IF NOT EXISTS idx_case_reports_app_version
    ON public.case_reports (application_number, version DESC);

-- Row-level security: enabled but permissive for service-role access
ALTER TABLE public.case_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on case_reports"
    ON public.case_reports
    FOR ALL
    USING (true)
    WITH CHECK (true);
