from __future__ import annotations

from typing import Any
from typing import MutableMapping
from typing import Optional
from typing import Union

import app.objects.geolocation
import app.state.cache
import app.state.services
import app.state.sessions
import app.usecases.players
import app.utils
from app.objects.player import Player

cache: MutableMapping[Union[int, str], Player] = {}  # {name/id: player}

## create


## read


async def _fetch_user_info_sql(key: str, val: Any):  # TODO: type
    # WARNING: do not pass user input into `key`; sql injection
    return await app.state.services.database.fetch_one(
        "SELECT id, name, priv, pw_bcrypt, country, "
        "silence_end, clan_id, clan_priv, api_key "
        f"FROM users WHERE {key} = :{key}",
        {key: val},
    )


def _determine_argument_kv(
    player_id: Optional[int] = None,
    player_name: Optional[str] = None,
) -> tuple[str, Any]:
    if player_id is not None:
        return "id", player_id
    elif player_name is not None:
        return "safe_name", app.utils.make_safe_name(player_name)
    else:
        raise NotImplementedError


async def fetch(
    # support fetching from both args
    id: Optional[int] = None,
    name: Optional[str] = None,
) -> Player | None:
    arg_key, arg_val = _determine_argument_kv(id, name)

    # determine correct source
    if player := cache.get(arg_val):
        return player

    user_info = await _fetch_user_info_sql(arg_key, arg_val)

    if user_info is None:
        return None

    db_player_id = user_info["id"]

    achievements = await app.usecases.players.fetch_achievements(db_player_id)
    friends, blocks = await app.usecases.players.fetch_relationships(db_player_id)
    stats = await app.usecases.players.fetch_stats(db_player_id)

    # TODO: fetch player's recent scores

    # TODO: fetch player's utc offset?

    # TODO: fetch player's api key?

    user_info = dict(user_info)  # make mutable copy

    # get geoloc from country acronym
    country_acronym = user_info.pop("country")

    # TODO: store geolocation {ip:geoloc} store as a repository, store ip reference in other objects
    # TODO: should we fetch their last ip from db here, and update it if they login?
    geolocation_data: app.objects.geolocation.Geolocation = {
        # XXX: we don't have an ip here, so we can't lookup the geolocation
        "latitude": 0.0,
        "longitude": 0.0,
        "country": {
            "acronym": country_acronym,
            "numeric": app.objects.geolocation.OSU_COUNTRY_CODES[country_acronym],
        },
    }

    player = Player(
        **user_info,
        stats=stats,
        friends=friends,
        blocks=blocks,
        achievements=achievements,
        geoloc=geolocation_data,
        token=None,
    )

    # NOTE: this doesn't set session-specific data like
    # utc_offset, pm_private, login_time, tourney_client, client_details

    cache[player.id] = player
    cache[player.name] = player

    return player


## update


async def update_name(player_id: int, new_name: str) -> None:
    """Update a player's name to a new value, by id."""
    await app.state.services.database.execute(
        "UPDATE users SET name = :name, safe_name = :safe_name WHERE id = :user_id",
        {
            "name": new_name,
            "safe_name": app.utils.make_safe_name(new_name),
            "user_id": player_id,
        },
    )


## delete