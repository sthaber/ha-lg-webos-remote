"""Read current TV state for an LG webOS TV and emit JSON on stdout.

Used by an HA `command_line` sensor to mirror the TV's true state.
Connection parameters are pulled from the webostv config entry in HA
storage so the script doesn't need to be edited when the TV is re-paired.
"""

from __future__ import annotations

import asyncio
import json
import sys

CONFIG_ENTRIES = "/config/.storage/core.config_entries"


def get_tv_creds() -> tuple[str, str]:
    with open(CONFIG_ENTRIES) as f:
        data = json.load(f)
    for entry in data["data"]["entries"]:
        if entry["domain"] == "webostv":
            d = entry["data"]
            return d["host"], d["client_secret"]
    raise RuntimeError("no webostv config entry")


async def main() -> int:
    from aiowebostv import WebOsClient

    host, key = get_tv_creds()
    client = WebOsClient(host, key, connect_timeout=2)
    out: dict[str, object] = {}
    try:
        await client.connect()
        pic = await client.request(
            "settings/getSystemSettings",
            {"category": "picture", "keys": ["energySaving", "eyeComfortMode"]},
        )
        ps = await client.request(
            "com.webos.service.tvpower/power/getPowerState", {}
        )
        out["energy_saving"] = pic["settings"]["energySaving"]
        out["eye_comfort_mode"] = pic["settings"]["eyeComfortMode"]
        out["power_state"] = ps.get("state")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
