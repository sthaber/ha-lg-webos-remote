"""Read and write LG webOS TV settings.

Usage:
    tv.py                          print current TV state as JSON on stdout
    tv.py set CATEGORY KEY VALUE   change one setting

Connection details come from the webostv config entry in HA storage, so
nothing here needs editing when the TV is re-paired.

Writes can't go through settings/setSystemSettings directly: the TV answers
"401 insufficient permissions" because WRITE_SETTINGS is only granted to
manifests carrying an LG signature, and recent firmware blacklists the
public one. Instead the write rides on a notification alert. createAlert
accepts a luna:// URI as its close action, and closing the alert runs it.
This is the same mechanism bscpylgtv and newer aiowebostv use for luna
calls, and it needs only WRITE_NOTIFICATION_ALERT, which the TV grants to
ordinary clients.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

CONFIG_ENTRIES = Path("/config/.storage/core.config_entries")
LUNA_SET_SYSTEM_SETTINGS = "luna://com.webos.settingsservice/setSystemSettings"

# The write path builds a shell command, so keep arguments to plain tokens.
TOKEN = re.compile(r"^[A-Za-z0-9_.-]+$")


def tv_creds() -> tuple[str, str]:
    data = json.loads(CONFIG_ENTRIES.read_text())
    for entry in data["data"]["entries"]:
        if entry["domain"] == "webostv":
            return entry["data"]["host"], entry["data"]["client_secret"]
    raise RuntimeError("no webostv config entry")


async def connect(timeout: int, attempts: int = 1):
    """Open a connection, retrying if the TV refuses.

    The TV resets connections when several arrive close together, and every
    call here opens its own, so a write landing next to a poll can lose the
    race. Reads don't retry: a dropped poll just leaves the entities
    unavailable until the next one, five seconds later.
    """
    from aiowebostv import WebOsClient

    host, key = tv_creds()
    last_error: Exception | None = None
    for attempt in range(attempts):
        client = WebOsClient(host, key, connect_timeout=timeout)
        try:
            await client.connect()
            return client
        except Exception as err:
            last_error = err
            if attempt + 1 < attempts:
                await asyncio.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def luna_request(client, uri: str, params: dict) -> None:
    """Run a luna:// call by attaching it to an alert and closing the alert."""
    action = {"uri": uri, "params": params}
    alert = await client.request(
        "system.notifications/createAlert",
        {
            "message": " ",
            "buttons": [{"label": "", "onClick": uri, "params": params}],
            "onclose": action,
            "onfail": action,
        },
    )
    await client.request(
        "system.notifications/closeAlert", {"alertId": alert["alertId"]}
    )


async def read_state() -> dict[str, object]:
    out: dict[str, object] = {}
    client = None
    try:
        client = await connect(2)
        picture = await client.request(
            "settings/getSystemSettings",
            {"category": "picture", "keys": ["energySaving", "eyeComfortMode"]},
        )
        power = await client.request(
            "com.webos.service.tvpower/power/getPowerState", {}
        )
        out["energy_saving"] = picture["settings"]["energySaving"]
        out["eye_comfort_mode"] = picture["settings"]["eyeComfortMode"]
        out["power_state"] = power.get("state")
    except Exception as err:
        out["error"] = f"{type(err).__name__}: {err}"
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
    return out


async def write_setting(category: str, key: str, value: str) -> int:
    client = None
    try:
        client = await connect(5, attempts=4)
        await luna_request(
            client,
            LUNA_SET_SYSTEM_SETTINGS,
            {"category": category, "settings": {key: value}},
        )
    except Exception as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(json.dumps(asyncio.run(read_state())))
        return 0

    if args[0] != "set" or len(args) != 4:
        print(__doc__, file=sys.stderr)
        return 2

    category, key, value = args[1:]
    for name, arg in (("category", category), ("key", key), ("value", value)):
        if not TOKEN.match(arg):
            print(f"bad {name}: {arg!r}", file=sys.stderr)
            return 2

    return asyncio.run(write_setting(category, key, value))


if __name__ == "__main__":
    sys.exit(main())
