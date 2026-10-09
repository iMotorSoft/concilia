-- Versioned migration; transaction and checksum supplied by migrate.py.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO concilia_app;

CREATE TABLE public.seg_users (
    id uuid PRIMARY KEY,
    email text NOT NULL UNIQUE CHECK (email = lower(btrim(email))),
    password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    role text NOT NULL CHECK (role IN ('CONSULTA', 'OPERADOR', 'ADMINISTRADOR')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE public.seg_sessions (
    token_hash bytea PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    user_id uuid NOT NULL REFERENCES public.seg_users(id),
    csrf_hash bytea NOT NULL CHECK (octet_length(csrf_hash) = 32),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (absolute_expires_at <= created_at + interval '24 hours'),
    CHECK (absolute_expires_at > created_at)
);
CREATE INDEX seg_sessions_user_idx ON public.seg_sessions(user_id);

CREATE FUNCTION public.seg_revoke_user_sessions() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF NEW.role IS DISTINCT FROM OLD.role
       OR NEW.password_hash IS DISTINCT FROM OLD.password_hash
       OR (OLD.active AND NOT NEW.active) THEN
        UPDATE public.seg_sessions SET revoked_at = CURRENT_TIMESTAMP
        WHERE user_id = NEW.id AND revoked_at IS NULL;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.seg_revoke_user_sessions() FROM PUBLIC;
CREATE TRIGGER seg_user_session_revocation AFTER UPDATE ON public.seg_users
FOR EACH ROW EXECUTE FUNCTION public.seg_revoke_user_sessions();
CREATE TABLE public.seg_password_resets (
    token_hash bytea PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    user_id uuid NOT NULL REFERENCES public.seg_users(id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE TABLE public.seg_audit_events (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES public.seg_users(id),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    result text NOT NULL CHECK (result IN ('SUCCESS', 'DENIED', 'FAILURE')),
    reason text,
    correlation_id uuid NOT NULL,
    before_state jsonb,
    after_state jsonb
);
CREATE INDEX seg_audit_entity_idx ON public.seg_audit_events(entity_type, entity_id, occurred_at);
CREATE TABLE public.seg_rate_limits (
    key_hash bytea PRIMARY KEY CHECK (octet_length(key_hash) = 32),
    window_started_at timestamptz NOT NULL,
    attempts integer NOT NULL CHECK (attempts >= 0),
    blocked_until timestamptz
);

-- No blanket grants or ownership for runtime. Audit events are append-only.
GRANT SELECT, INSERT, UPDATE ON public.seg_users, public.seg_sessions,
    public.seg_password_resets, public.seg_rate_limits TO concilia_app;
GRANT SELECT, INSERT ON public.seg_audit_events TO concilia_app;
