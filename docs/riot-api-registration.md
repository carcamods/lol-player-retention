# Riot API registration

How this project is registered with Riot, and the text submitted. The text will be reused for
a production-key application later (FR7).

## Key types and what this project uses

| Key | Expires | Rate limit (per region) | Used for |
|---|---|---|---|
| Development | Every 24 h | 20 / 1 s, 100 / 2 min | Recording test fixtures; collection until the personal key arrives |
| **Personal** | Never | 20 / 1 s, 100 / 2 min (no increases) | Data collection: `lolret collect` |
| Production | Never | From 500 / 10 s, 30,000 / 10 min | Only if a public live lookup is added (FR7) |

The personal key buys no extra throughput, only freedom from the daily expiry. Collection is
resumable, so a development key works too if it's regenerated daily.

Source: [Developer Portal docs](https://developer.riotgames.com/docs/portal),
[application process](https://developer.riotgames.com/application-process.html),
[general policies](https://developer.riotgames.com/policies/general).

## Personal key application

Submitted from the Developer Portal: **Register Product → Personal API Key**. Personal
projects skip the verification step and need no prototype, only a detailed description.

**Product name**

```
LoL Player Retention Research (lolret)
```

**Short description**

```
Personal, non-commercial data-science research project that models when ranked League of Legends players take long breaks from the game.
```

**Detailed description**

```
lolret is a personal, non-commercial data-science research project, built and run by one developer (me) as a portfolio case study. It studies player retention: given a ranked player's recent match history, how likely are they to stop playing for the next 28 days, and which patterns (session frequency, loss streaks, game length) tend to come before a break.

How the API is used
- Only I run the code, locally. The key is stored in an environment variable, never in code or in the repository.
- LEAGUE-V4 entries: to sample ranked Solo/Duo players across tiers (Iron to Diamond) in NA1, EUW1 and KR.
- MATCH-V5 match IDs (with startTime/endTime) and match details: each sampled player's recent match history.
- ACCOUNT-V1 by Riot ID: only to test predictions on my own account.
- Requests stay within the 20 per second / 100 per 2 minutes limits and honour Retry-After. Responses are cached, so nothing is requested twice. Expected volume: tens of thousands of requests per region, spread over several days.

Data handling
- Raw API responses stay on my machine. Nothing is sold or shared.
- Anything published is anonymised: player identifiers are replaced with salted hashes, and no Riot IDs, PUUIDs or summoner names are shown, so no player can be identified.

What gets published
- The source code on GitHub and a static write-up page with aggregate findings, model performance and a sample of anonymised example predictions. The page does not call the Riot API and offers no player lookup. If I later want a public live lookup, I will register a separate production application.

What it does not do
- No MMR/ELO estimation or alternative ranking, no player profiles, no betting, no monetization.
- The project carries Riot's legal disclaimer.
```

**Product URL** (if the form requires one): `https://github.com/carcamods`. The project repo
stays private until launch, and a private link would show reviewers a 404.

**Game focus:** League of Legends. **Product group:** the default group.

## Status

| Key | Status |
|---|---|
| Development | Active (regenerate daily from the dashboard) |
| Personal | Not yet submitted |
| Production | Not planned until FR7 |
