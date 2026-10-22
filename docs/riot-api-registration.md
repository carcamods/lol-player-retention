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

The form field allows 1,500 characters; this text is about 1,320.

```
lolret is a personal, non-commercial data-science research project, built and run only by me as a portfolio case study. It studies player retention: how likely a ranked player is to stop playing for the next 28 days, and which patterns (session frequency, loss streaks, game length) come before a break.

API use
- Run locally by me only. The key lives in an environment variable, never in code.
- LEAGUE-V4 entries: sample ranked Solo/Duo players (Iron to Diamond) in NA1, EUW1 and KR.
- MATCH-V5 match IDs (startTime/endTime) and match details: each player's recent history.
- ACCOUNT-V1 by Riot ID: only to test on my own account.
- Stays within rate limits, honours Retry-After and caches responses. Tens of thousands of requests per region, over several days.

Data
- Raw responses stay on my machine. Nothing is sold or shared.
- Published results are anonymised (salted-hash IDs; no Riot IDs, PUUIDs or names), so no player can be identified.

Published
- Source code on GitHub and a static write-up with aggregate findings, model performance and anonymised example predictions. It does not call the API and has no player lookup. A public live lookup would get its own production application.

Not included: MMR/ELO estimation or ranking, player profiles, betting, monetization. Riot's legal disclaimer is shown.
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
