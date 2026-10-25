-- Match sequences for the neural nets (ADR 0004): the 20 most recent games that ENDED at or
-- before each cutoff, one row per (player, cutoff, game). rn = 1 is the most recent.
--
-- Inputs: players, cutoffs, matches (see extract.py). Timestamps are naive UTC. Same timing
-- rule as the match features in features.sql (ADR 0006): a game still running at T has no
-- result yet, so it isn't here. tests/test_dataset.py runs the leak guard on these rows too.

WITH player_cutoffs AS (
    SELECT p.platform, p.puuid, c.cutoff
    FROM players AS p
    CROSS JOIN cutoffs AS c
)

SELECT
    pc.platform,
    pc.puuid,
    pc.cutoff,
    row_number() OVER w AS rn,
    date_diff('second', m.game_end, pc.cutoff) / 3600.0 AS hours_before_cutoff,
    -- Hours between the previous game's end and this game's start; NULL for the oldest game.
    date_diff('second', lead(m.game_end) OVER w, m.game_start) / 3600.0 AS gap_hours,
    m.duration_s / 60.0 AS duration_min,
    m.win,
    m.kills,
    m.deaths,
    m.assists,
    m.remake,
    m.surrendered,
    m.queue_id,
    m.team_position,
    m.champion_id = lead(m.champion_id) OVER w AS same_champion
FROM player_cutoffs AS pc
JOIN matches AS m
    ON m.platform = pc.platform AND m.puuid = pc.puuid AND m.game_end <= pc.cutoff
WINDOW w AS (
    PARTITION BY pc.platform, pc.puuid, pc.cutoff ORDER BY m.game_end DESC, m.match_id DESC
)
QUALIFY rn <= 20
ORDER BY pc.platform, pc.puuid, pc.cutoff, rn
