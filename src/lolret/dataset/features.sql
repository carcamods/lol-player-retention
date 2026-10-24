-- Point-in-time examples: one row per (player, cutoff). See docs/features.md.
--
-- Inputs: players, cutoffs, buckets, matches (see extract.py). Timestamps are naive UTC.
--
-- What each part may read, relative to the cutoff T (ADR 0003, ADR 0006):
--   * Activity features: buckets that END at or before T. A game counts in the bucket where it
--     STARTED, so a game in progress at T is known to exist, but nothing after T is.
--   * Match features: only games that ENDED at or before T. A game still running at T has no
--     result yet.
--   * The label: only buckets inside (T, T + 28 days].
-- tests/test_dataset.py checks this: features from the full data must equal features from data
-- truncated at T.

WITH player_cutoffs AS (
    SELECT p.platform, p.puuid, p.tier, p.division, c.cutoff
    FROM players AS p
    CROSS JOIN cutoffs AS c
),

activity AS (
    SELECT
        pc.platform,
        pc.puuid,
        pc.cutoff,
        coalesce(sum(b.games) FILTER (
            WHERE b.bucket_start >= pc.cutoff - INTERVAL 7 DAY AND b.bucket_end <= pc.cutoff
        ), 0)::INTEGER AS games_0_7d,
        coalesce(sum(b.games) FILTER (
            WHERE b.bucket_start >= pc.cutoff - INTERVAL 14 DAY
              AND b.bucket_end <= pc.cutoff - INTERVAL 7 DAY
        ), 0)::INTEGER AS games_8_14d,
        coalesce(sum(b.games) FILTER (
            WHERE b.bucket_start >= pc.cutoff - INTERVAL 28 DAY
              AND b.bucket_end <= pc.cutoff - INTERVAL 14 DAY
        ), 0)::INTEGER AS games_15_28d,
        coalesce(sum(b.games) FILTER (
            WHERE b.bucket_start >= pc.cutoff - INTERVAL 56 DAY
              AND b.bucket_end <= pc.cutoff - INTERVAL 28 DAY
        ), 0)::INTEGER AS games_29_56d,
        count(*) FILTER (
            WHERE b.games > 0
              AND b.bucket_start >= pc.cutoff - INTERVAL 56 DAY AND b.bucket_end <= pc.cutoff
        )::INTEGER AS active_weeks_8w,
        -- Label inputs: the 28 days after the cutoff, and how much of them the data covers.
        coalesce(sum(b.games) FILTER (
            WHERE b.bucket_start >= pc.cutoff AND b.bucket_end <= pc.cutoff + INTERVAL 28 DAY
        ), 0)::INTEGER AS games_next_28d,
        coalesce(sum(date_diff('second', b.bucket_start, b.bucket_end)) FILTER (
            WHERE b.bucket_start >= pc.cutoff AND b.bucket_end <= pc.cutoff + INTERVAL 28 DAY
        ), 0)::BIGINT AS label_seconds_observed
    FROM player_cutoffs AS pc
    LEFT JOIN buckets AS b ON b.platform = pc.platform AND b.puuid = pc.puuid
    GROUP BY pc.platform, pc.puuid, pc.cutoff
),

-- The 20 most recent games that ended at or before the cutoff. rn = 1 is the most recent.
recent AS (
    SELECT
        pc.platform,
        pc.puuid,
        pc.cutoff,
        m.*  EXCLUDE (platform, puuid),
        row_number() OVER w AS rn,
        -- Hours between the previous game's end and this game's start.
        date_diff('second', lead(m.game_end) OVER w, m.game_start) / 3600.0 AS gap_hours
    FROM player_cutoffs AS pc
    JOIN matches AS m
        ON m.platform = pc.platform AND m.puuid = pc.puuid AND m.game_end <= pc.cutoff
    WINDOW w AS (PARTITION BY pc.platform, pc.puuid, pc.cutoff ORDER BY m.game_end DESC)
    QUALIFY rn <= 20
),

recent_stats AS (
    SELECT
        platform,
        puuid,
        cutoff,
        count(*)::INTEGER AS recent_games,
        date_diff('second', max(game_end), cutoff) / 86400.0 AS days_since_last_game,
        avg(win::INT) AS win_rate,
        avg(win::INT) FILTER (WHERE rn <= 5) AS win_rate_last5,
        -- Losses in a row up to the most recent game: the first win's position minus one.
        (coalesce(min(rn) FILTER (WHERE win), count(*) + 1) - 1)::INTEGER AS loss_streak,
        avg((kills + assists) / greatest(deaths, 1)) AS kda,
        avg(deaths) AS deaths_avg,
        avg(duration_s) / 60.0 AS duration_min_avg,
        avg(remake::INT) AS remake_share,
        avg((surrendered AND NOT win)::INT) AS surrendered_loss_share,
        avg((queue_id IN (420, 440))::INT) AS ranked_share,
        avg((queue_id = 450)::INT) AS aram_share,
        count(DISTINCT champion_id)::DOUBLE / count(*) AS champion_diversity,
        median(gap_hours) AS gap_hours_median,
        -- A session ends after a break of more than an hour. The last session starts at the
        -- most recent game that follows such a break (or that has no earlier game in view).
        (min(rn) FILTER (WHERE gap_hours > 1 OR gap_hours IS NULL))::INTEGER AS last_session_games
    FROM recent
    GROUP BY platform, puuid, cutoff
),

roles AS (
    SELECT platform, puuid, cutoff, max(n)::DOUBLE / sum(n) AS main_role_share
    FROM (
        SELECT platform, puuid, cutoff, team_position, count(*) AS n
        FROM recent
        WHERE team_position IS NOT NULL
        GROUP BY platform, puuid, cutoff, team_position
    )
    GROUP BY platform, puuid, cutoff
)

SELECT
    pc.platform,
    pc.puuid,
    pc.tier,
    pc.division,
    pc.cutoff,
    -- Eligible: played at least once in the 28 days before the cutoff (ADR 0006).
    (a.games_0_7d + a.games_8_14d + a.games_15_28d) > 0 AS eligible,
    -- Label: no game at all in the 28 days after the cutoff. NULL if that window isn't covered.
    CASE
        WHEN a.label_seconds_observed < 28 * 86400 THEN NULL
        ELSE a.games_next_28d = 0
    END AS churned,
    a.games_0_7d,
    a.games_8_14d,
    a.games_15_28d,
    a.games_29_56d,
    a.active_weeks_8w,
    coalesce(s.recent_games, 0) AS recent_games,
    s.days_since_last_game,
    s.win_rate,
    s.win_rate_last5,
    s.loss_streak,
    s.kda,
    s.deaths_avg,
    s.duration_min_avg,
    s.remake_share,
    s.surrendered_loss_share,
    s.ranked_share,
    s.aram_share,
    s.champion_diversity,
    s.gap_hours_median,
    s.last_session_games,
    r.main_role_share
FROM player_cutoffs AS pc
JOIN activity AS a USING (platform, puuid, cutoff)
LEFT JOIN recent_stats AS s USING (platform, puuid, cutoff)
LEFT JOIN roles AS r USING (platform, puuid, cutoff)
ORDER BY pc.platform, pc.puuid, pc.cutoff
