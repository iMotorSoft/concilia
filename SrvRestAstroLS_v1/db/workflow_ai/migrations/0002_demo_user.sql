-- 0002_demo_user.sql
-- Idempotent seed for demo user + credentials + workspace membership

BEGIN;

-- Ensure pgcrypto for crypt()/gen_salt()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Credentials table
CREATE TABLE IF NOT EXISTS core_user_credentials (
  user_id       uuid PRIMARY KEY REFERENCES core_users(user_id) ON DELETE CASCADE,
  password_hash text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE
  v_user_id uuid;
  v_role_id uuid;
BEGIN
  INSERT INTO core_users (email, full_name)
  VALUES ('demo_concilia@imotorsoft.com', 'Demo Concilia')
  ON CONFLICT (email) DO UPDATE
    SET full_name = EXCLUDED.full_name
  RETURNING user_id INTO v_user_id;

  IF v_user_id IS NULL THEN
    SELECT user_id INTO v_user_id
    FROM core_users
    WHERE email = 'demo_concilia@imotorsoft.com';
  END IF;

  SELECT role_id INTO v_role_id
  FROM core_roles
  WHERE code = 'admin';

  INSERT INTO core_user_credentials (user_id, password_hash)
  VALUES (v_user_id, crypt('password', gen_salt('bf', 12)))
  ON CONFLICT (user_id) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        updated_at = now();

  INSERT INTO core_workspace_members (workspace_id, user_id, role_id)
  VALUES ('019b41b8-f629-7989-b4f0-190a4a49552e', v_user_id, v_role_id)
  ON CONFLICT (workspace_id, user_id) DO UPDATE
    SET role_id = EXCLUDED.role_id;
END $$;

COMMIT;
