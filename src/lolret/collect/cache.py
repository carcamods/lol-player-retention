"""A `RiotEndpoints` that answers from the store first and only calls the API on a miss.

Every 200 and 404 is stored, so a re-run of the same config sends no request twice. That is
what makes a multi-day collection resumable. Failed requests are recorded and retried on the
next run.
"""

from urllib.parse import urlencode

from lolret.collect.store import Store, endpoint_name
from lolret.riot.client import Params, RiotClient, RiotEndpoints, RiotRequestError, RiotResponse


def cache_key(routing: str, path: str, params: Params | None) -> str:
    query = urlencode(sorted((params or {}).items()))
    return f"{routing}{path}?{query}" if query else f"{routing}{path}"


class CachedRiot(RiotEndpoints):
    def __init__(self, client: RiotClient, store: Store) -> None:
        self._client = client
        self._store = store
        self.hits = 0
        self.misses = 0

    async def get(self, routing: str, path: str, params: Params | None = None) -> RiotResponse:
        key = cache_key(routing, path, params)
        cached = self._store.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        try:
            response = await self._client.get(routing, path, params)
        except RiotRequestError as exc:
            self._store.record_failure(key, str(exc))
            raise
        self._store.put(key, endpoint_name(path), response)
        return response
