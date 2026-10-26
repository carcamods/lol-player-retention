# Production key application (draft)

A draft for the owner to submit on the [Riot Developer Portal](https://developer.riotgames.com/)
(Register Product → production). The project runs on a personal key today: 20 requests per
second and 100 per 2 minutes, per region. A production key starts at 500 requests per 10 seconds
and 30,000 per 10 minutes. Riot asks for a working product, a detailed description, compliance
with its policies, and a secured key; review time varies.

Submit it once the site is live, so the reviewers can see the product.

## Product name

LoL Player Retention

## Product URL

https://carcamods.github.io/lol-player-retention/ (site), with the code at
https://github.com/carcamods/lol-player-retention

## Description (paste)

LoL Player Retention studies when ranked League of Legends players stop playing, and whether
that can be predicted from what was knowable at the time. It is an open-source research and
portfolio project. Its public site shows an anonymised, frozen snapshot: for held-out players, the
predicted chance of stopping in the next 28 days next to what actually happened, the factors
behind each prediction, and an honest model card. A command-line tool lets a player check their
own churn risk with their own key.

How it uses the API:
- league-v4 entries (Ranked Solo/Duo, Iron to Diamond) to draw a random, reproducible sample of
  players per division.
- match-v5 match IDs by PUUID, one request per player per week, to count games and to label
  whether a player kept playing.
- match-v5 match details for each player's 20 most recent games before each prediction date.
- account-v1 by Riot ID, only in the command-line tool, for a player who looks themselves up.

Every response is cached locally and never requested twice. Calls run from a batch job on the
owner's machine, not from the website: the site is static, serves only the anonymised snapshot,
and makes no API calls. The key is read from a local environment file, sent only in the
X-Riot-Token header, and never published, logged or embedded in any client.

Privacy: no Riot ID, PUUID or match ID is published. Players appear only as "Player 0001"...,
numbered by a salted hash whose salt is discarded after each export. Every page shows Riot's
legal disclaimer.

Why a production key: the research needs larger samples. The current study uses 6,048 players
and a 4,700-player Bronze expansion that takes about 25 hours at personal-key rates. Larger,
more frequent samples (more tiers, more dates, longer history) would let the project test whether
churn becomes predictable with more data, and publish the answer, positive or negative.

Expected volume: batch collections of roughly 50 requests per sampled player, a few times a
year, well within the standard production limits.

## Notes for the owner

- The reviewers want products that help players. Lead with the self-check (`lolret predict`) and
  the public findings about when and why players stop.
- Personal keys can't power public products. The site makes no API calls, but registering the
  project as a product also settles any doubt about publishing data collected with this key.
- One key per product: this application covers this project only.
