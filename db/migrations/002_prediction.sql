-- Prediction engine tables (SPEC v1.0)

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

CREATE INDEX IF NOT EXISTS idx_prizes_last_two_draw
    ON prizes (last_two, draw_id);

CREATE INDEX IF NOT EXISTS idx_draws_mb_date
    ON draws (draw_date)
    WHERE region = 'MB';
