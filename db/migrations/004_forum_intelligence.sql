-- Forum intelligence: extension CollectSession + normalized picks

CREATE TABLE IF NOT EXISTS forum_sessions (
    target_date   DATE PRIMARY KEY,
    window_start  TIMESTAMPTZ,
    window_end    TIMESTAMPTZ,
    finalized_at  TIMESTAMPTZ,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS forum_user_picks (
    id            BIGSERIAL PRIMARY KEY,
    target_date   DATE NOT NULL,
    username      TEXT NOT NULL,
    pick_type     TEXT NOT NULL,
    numbers       TEXT[] NOT NULL DEFAULT '{}',
    forum         TEXT,
    post_id       TEXT,
    posted_at     TIMESTAMPTZ,
    raw_excerpt   TEXT,
    UNIQUE (target_date, username, pick_type)
);

CREATE INDEX IF NOT EXISTS idx_forum_user_picks_date
    ON forum_user_picks (target_date DESC);

CREATE INDEX IF NOT EXISTS idx_forum_user_picks_user
    ON forum_user_picks (username, target_date DESC);
