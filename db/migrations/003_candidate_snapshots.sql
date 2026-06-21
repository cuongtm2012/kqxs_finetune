-- Candidate snapshots for audit (SPEC v4.2 Module 10)

CREATE TABLE IF NOT EXISTS candidate_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    target_date   DATE NOT NULL,
    as_of_date    DATE NOT NULL,
    target        TEXT NOT NULL,
    top           SMALLINT NOT NULL,
    min_filters   SMALLINT NOT NULL,
    sort          TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (target_date, target, top, min_filters, sort)
);

CREATE INDEX IF NOT EXISTS idx_candidate_snapshots_target_date
    ON candidate_snapshots (target_date DESC);

CREATE INDEX IF NOT EXISTS idx_candidate_snapshots_target
    ON candidate_snapshots (target, target_date DESC);
