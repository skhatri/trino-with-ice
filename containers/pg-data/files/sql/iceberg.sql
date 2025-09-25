CREATE DATABASE lakehouse;

\c lakehouse

CREATE USER lakehouse_user WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN NOREPLICATION NOBYPASSRLS;
GRANT lakehouse_user to postgres;
GRANT CONNECT,CREATE ON DATABASE lakehouse TO lakehouse_user;

CREATE SCHEMA IF NOT EXISTS iceberg AUTHORIZATION lakehouse_user;

ALTER ROLE lakehouse_user IN DATABASE lakehouse SET search_path TO iceberg,"$user",public;

ALTER USER lakehouse_user WITH PASSWORD 'password';


CREATE TABLE IF NOT EXISTS iceberg.eplmatch
(
    teammatch       INTEGER,
    date            DATE,
    time            VARCHAR(255),
    comp            VARCHAR(255),
    round           VARCHAR(255),
    day             VARCHAR(255),
    venue           VARCHAR(255),
    result          VARCHAR(255),
    points          INTEGER,
    goals_for       DOUBLE PRECISION,
    goals_against   DOUBLE PRECISION,
    opponent        VARCHAR(255),
    xG              VARCHAR(255),
    xGA             VARCHAR(255),
    poss            VARCHAR(255),
    attendance      VARCHAR(255),
    captain         VARCHAR(255),
    formation       VARCHAR(255),
    referee         VARCHAR(255),
    match_report    VARCHAR(255),
    notes           VARCHAR(255),
    shots           VARCHAR(255),
    shots_on_target VARCHAR(255),
    dist            VARCHAR(255),
    penalty         VARCHAR(255),
    pkatt           VARCHAR(255),
    season          VARCHAR(255),
    team            VARCHAR(255),
    freekick        VARCHAR(255)
);


