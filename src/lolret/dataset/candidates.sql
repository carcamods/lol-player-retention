-- Candidate features (ADR 0013): one row per (player, cutoff), kept apart from features.sql
-- until the forward test decides whether they join the model. See docs/features.md.
--
-- Inputs: players, cutoffs, buckets, matches (see extract.py). Timestamps are naive UTC.
-- Same timing rules as features.sql (ADR 0006): weekly buckets that end at or before T, and
-- only games that ended at or before T. tests/test_dataset.py runs the leak guard on them.

WITH player_cutoffs AS (
    SELECT p.platform, p.puuid, c.cutoff
    FROM players AS p
    CROSS JOIN cutoffs AS c
),

-- Each of the 8 weeks before the cutoff next to the week before it.
weeks AS (
    SELECT
        pc.platform,
        pc.puuid,
        pc.cutoff,
        b.games,
        lag(b.games) OVER (
            PARTITION BY pc.platform, pc.puuid, pc.cutoff ORDER BY b.bucket_start
        ) AS games_week_before
    FROM player_cutoffs AS pc
    JOIN buckets AS b
        ON b.platform = pc.platform AND b.puuid = pc.puuid
        AND b.bucket_start >= pc.cutoff - INTERVAL 56 DAY AND b.bucket_end <= pc.cutoff
),

returns AS (
    SELECT
        platform,
        puuid,
        cutoff,
        count(*) FILTER (WHERE games > 0 AND games_week_before = 0)::INTEGER AS returns_8w
    FROM weeks
    GROUP BY platform, puuid, cutoff
),

-- The 20 most recent games that ended at or before the cutoff, as in features.sql.
recent AS (
    SELECT
        pc.platform,
        pc.puuid,
        pc.cutoff,
        m.game_end,
        m.summoner_level,
        m.teammates,
        row_number() OVER w AS rn,
        date_diff('second', lead(m.game_end) OVER w, m.game_start) / 3600.0 AS gap_hours
    FROM player_cutoffs AS pc
    JOIN matches AS m
        ON m.platform = pc.platform AND m.puuid = pc.puuid AND m.game_end <= pc.cutoff
    WINDOW w AS (
        PARTITION BY pc.platform, pc.puuid, pc.cutoff ORDER BY m.game_end DESC, m.match_id DESC
    )
    QUALIFY rn <= 20
),

recent_stats AS (
    SELECT
        platform,
        puuid,
        cutoff,
        date_diff('second', max(game_end), cutoff) / 86400.0 AS days_since_last_game,
        max(gap_hours) / 24.0 AS longest_gap_days,
        -- Account levels only go up, so the highest is the one at the most recent game.
        max(summoner_level) AS summoner_level
    FROM recent
    GROUP BY platform, puuid, cutoff
),

-- Teammates who were on the player's team in at least two of those games: likely premades.
mates AS (
    SELECT platform, puuid, cutoff, count(*) FILTER (WHERE n >= 2)::INTEGER AS repeated_teammates
    FROM (
        SELECT r.platform, r.puuid, r.cutoff, t.mate, count(*) AS n
        FROM recent AS r, unnest(r.teammates) AS t(mate)
        GROUP BY r.platform, r.puuid, r.cutoff, t.mate
    )
    GROUP BY platform, puuid, cutoff
)

SELECT
    pc.platform,
    pc.puuid,
    pc.cutoff,
    coalesce(rt.returns_8w, 0) AS returns_8w,
    s.longest_gap_days,
    -- How the current break compares with the longest one before it (floored at an hour).
    s.days_since_last_game / greatest(s.longest_gap_days, 1 / 24.0) AS break_vs_longest_gap,
    s.summoner_level,
    coalesce(mt.repeated_teammates, 0) AS repeated_teammates
FROM player_cutoffs AS pc
LEFT JOIN returns AS rt USING (platform, puuid, cutoff)
LEFT JOIN recent_stats AS s USING (platform, puuid, cutoff)
LEFT JOIN mates AS mt USING (platform, puuid, cutoff)
ORDER BY pc.platform, pc.puuid, pc.cutoff
