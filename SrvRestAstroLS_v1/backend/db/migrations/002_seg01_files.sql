-- Minimal permanent single-deployment catalog; annual dimensions belong to later phases.
CREATE TABLE public.seg_files (
    id uuid PRIMARY KEY,
    source text NOT NULL CHECK (source IN ('extracto', 'contable', 'sicom')),
    relative_path text NOT NULL UNIQUE CHECK (
        relative_path !~ '(^/|(^|/)\.\.(/|$))'
        AND relative_path ~ '^(incoming|canonical)/'),
    uploaded_by uuid NOT NULL REFERENCES public.seg_users(id),
    uploaded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'REVOKED')),
    parent_id uuid REFERENCES public.seg_files(id)
);
CREATE INDEX seg_files_actor_idx ON public.seg_files(uploaded_by, uploaded_at);
GRANT SELECT, INSERT ON public.seg_files TO concilia_app;
-- No automatic registration of historical storage objects.
