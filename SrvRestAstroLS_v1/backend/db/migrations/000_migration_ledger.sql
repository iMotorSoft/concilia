CREATE TABLE IF NOT EXISTS public.concilia_schema_migrations (
    version text PRIMARY KEY,
    sha256 text NOT NULL CHECK (length(sha256) = 64),
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
REVOKE ALL ON public.concilia_schema_migrations FROM PUBLIC;
