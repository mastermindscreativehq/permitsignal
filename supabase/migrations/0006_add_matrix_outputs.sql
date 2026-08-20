-- 0006_add_matrix_outputs.sql
-- Matrix Center: stores generated outputs per applicant/profile.
-- Each output is a versioned artifact linked to an application_number.
-- Source data (the leads table) is NEVER mutated by Matrix operations.

CREATE TABLE IF NOT EXISTS public.matrix_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_number TEXT NOT NULL,
    instruction TEXT NOT NULL,
    output TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_draft BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for fast lookup by application
CREATE INDEX IF NOT EXISTS idx_matrix_outputs_application_number
    ON public.matrix_outputs (application_number);

-- Composite index for version ordering
CREATE INDEX IF NOT EXISTS idx_matrix_outputs_app_version
    ON public.matrix_outputs (application_number, version DESC);

-- Row-level security: enabled but permissive for service-role access
ALTER TABLE public.matrix_outputs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on matrix_outputs"
    ON public.matrix_outputs
    FOR ALL
    USING (true)
    WITH CHECK (true);
