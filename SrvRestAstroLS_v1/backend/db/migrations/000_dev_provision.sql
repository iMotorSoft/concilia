-- Applied only to the postgres maintenance database by the DEV provisioning tool.
-- Placeholders rendered with psycopg.sql.Identifier / Literal, never string interpolation.
CREATE ROLE {owner} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {owner_password};
CREATE ROLE {app} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {app_password};
