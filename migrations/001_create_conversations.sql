-- One row per question the agent answered. Written by db.py, read and flagged by the dashboard API.
CREATE TABLE IF NOT EXISTS conversations (
  id          SERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  question    TEXT        NOT NULL,
  area        TEXT,
  psi         INTEGER,
  answer      TEXT        NOT NULL,
  tools_used  TEXT[]      NOT NULL DEFAULT '{}',
  route       TEXT,
  flagged     BOOLEAN     NOT NULL DEFAULT false
);
