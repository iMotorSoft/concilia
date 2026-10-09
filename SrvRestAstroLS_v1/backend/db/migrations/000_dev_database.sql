-- CREATE DATABASE requires autocommit, after role provisioning commits.
CREATE DATABASE concilia_fce OWNER concilia_owner;
REVOKE ALL ON DATABASE concilia_fce FROM PUBLIC;
GRANT CONNECT ON DATABASE concilia_fce TO concilia_app;
