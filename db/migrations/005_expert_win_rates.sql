-- Expert win rates (aggregated) + per-day pick outcomes (audit)

CREATE TABLE IF NOT EXISTS expert_win_rates (
    username      TEXT NOT NULL,
    pick_type     TEXT NOT NULL,
    period_label  TEXT NOT NULL,
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    hits          INT NOT NULL DEFAULT 0,
    total         INT NOT NULL DEFAULT 0,
    win_rate      NUMERIC(7,4) NOT NULL,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (username, pick_type, period_label)
);

CREATE INDEX IF NOT EXISTS idx_expert_win_rates_period
    ON expert_win_rates (period_label);

CREATE INDEX IF NOT EXISTS idx_expert_win_rates_user
    ON expert_win_rates (username);

CREATE TABLE IF NOT EXISTS expert_pick_results (
    target_date   DATE NOT NULL,
    username      TEXT NOT NULL,
    pick_type     TEXT NOT NULL,
    numbers       TEXT[] NOT NULL DEFAULT '{}',
    hit           BOOLEAN NOT NULL,
    draw_de       TEXT,
    evaluated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (target_date, username, pick_type)
);

CREATE INDEX IF NOT EXISTS idx_expert_pick_results_date
    ON expert_pick_results (target_date DESC);
