-- Analytics schema (PostgreSQL)

CREATE TYPE region_code AS ENUM ('MB', 'MN', 'MT');

CREATE TABLE draws (
    id          BIGSERIAL PRIMARY KEY,
    draw_date   DATE NOT NULL,
    region      region_code NOT NULL DEFAULT 'MB',
    station     TEXT,
    label       TEXT,
    source      TEXT NOT NULL DEFAULT 'xskt',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_draws_mb_day ON draws (draw_date) WHERE region = 'MB';
CREATE UNIQUE INDEX uq_draws_mn_mt ON draws (draw_date, region, COALESCE(station, ''))
    WHERE region IN ('MN', 'MT');
CREATE INDEX idx_draws_date ON draws (draw_date DESC);
CREATE INDEX idx_draws_region_date ON draws (region, draw_date DESC);

CREATE TABLE prizes (
    id           BIGSERIAL PRIMARY KEY,
    draw_id      BIGINT NOT NULL REFERENCES draws (id) ON DELETE CASCADE,
    slot_index   SMALLINT NOT NULL,
    prize_level  TEXT NOT NULL,
    prize_order  SMALLINT NOT NULL DEFAULT 0,
    number       TEXT NOT NULL,
    last_two     CHAR(2) NOT NULL,
    first_digit  CHAR(1),
    last_digit   CHAR(1),
    UNIQUE (draw_id, slot_index)
);

CREATE INDEX idx_prizes_draw_id ON prizes (draw_id);
CREATE INDEX idx_prizes_last_two ON prizes (last_two);
CREATE INDEX idx_prizes_level ON prizes (prize_level);

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL UNIQUE,
    email         TEXT,
    display_name  TEXT,
    access_token  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chot_predictions (
    id           BIGSERIAL PRIMARY KEY,
    draw_date    DATE NOT NULL,
    email        TEXT NOT NULL,
    name         TEXT,
    lo           TEXT[] NOT NULL DEFAULT '{}',
    lodau        TEXT[] NOT NULL DEFAULT '{}',
    lodit        TEXT[] NOT NULL DEFAULT '{}',
    lobt         TEXT,
    dedau        TEXT[] NOT NULL DEFAULT '{}',
    dedit        TEXT[] NOT NULL DEFAULT '{}',
    debt         TEXT,
    rank         INT NOT NULL DEFAULT 0,
    ratio_de     TEXT,
    ratio_lo     TEXT,
    ratio_lobt   TEXT,
    ratio_debt   TEXT,
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (draw_date, email)
);

CREATE INDEX idx_chot_date ON chot_predictions (draw_date DESC);

CREATE TABLE trends (
    id         BIGSERIAL PRIMARY KEY,
    draw_date  DATE NOT NULL UNIQUE,
    lotto      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE caudep_snapshots (
    id         BIGSERIAL PRIMARY KEY,
    draw_date  DATE NOT NULL UNIQUE,
    data       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE import_checkpoints (
    job_name    TEXT PRIMARY KEY,
    last_date   DATE,
    stats       JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Loto hits per day (MB): refresh after bulk import
CREATE MATERIALIZED VIEW mv_loto_daily AS
SELECT
    d.draw_date,
    p.last_two AS loto,
    COUNT(*)::INT AS hit_count
FROM draws d
JOIN prizes p ON p.draw_id = d.id
WHERE d.region = 'MB'
GROUP BY d.draw_date, p.last_two;

CREATE UNIQUE INDEX uq_mv_loto_daily ON mv_loto_daily (draw_date, loto);

CREATE OR REPLACE FUNCTION refresh_loto_views()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_loto_daily;
EXCEPTION
    WHEN OTHERS THEN
        REFRESH MATERIALIZED VIEW mv_loto_daily;
END;
$$;

-- Prediction engine (SPEC v1.0)
CREATE TABLE IF NOT EXISTS prediction_runs (
    id            BIGSERIAL PRIMARY KEY,
    target_date   DATE NOT NULL,
    as_of_date    DATE NOT NULL,
    target_type   TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    params        JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (target_date, target_type, model_name)
);

CREATE TABLE IF NOT EXISTS prediction_items (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES prediction_runs (id) ON DELETE CASCADE,
    rank            SMALLINT NOT NULL,
    value           TEXT NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    UNIQUE (run_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_date ON prediction_runs (target_date DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_items_run ON prediction_items (run_id);

CREATE TABLE IF NOT EXISTS backtest_reports (
    id            BIGSERIAL PRIMARY KEY,
    target_type   TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    period_from   DATE NOT NULL,
    period_to     DATE NOT NULL,
    top_k         SMALLINT NOT NULL,
    metrics       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prizes_last_two_draw ON prizes (last_two, draw_id);
CREATE INDEX IF NOT EXISTS idx_draws_mb_date ON draws (draw_date) WHERE region = 'MB';
