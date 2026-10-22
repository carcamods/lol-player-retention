"""Riot routing values.

League data (league-v4) is served per platform, such as `na1`. Match data (match-v5) is
served per regional cluster, such as `americas`. Riot enforces rate limits separately for
each routing value, so a platform and its region have independent budgets.
"""

PLATFORM_REGION: dict[str, str] = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "me1": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "sg2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}


def region_for(platform: str) -> str:
    try:
        return PLATFORM_REGION[platform]
    except KeyError:
        raise ValueError(f"Unknown platform {platform!r}") from None


def base_url(routing: str) -> str:
    return f"https://{routing}.api.riotgames.com"
