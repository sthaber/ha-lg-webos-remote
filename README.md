# ha-lg-webos-remote

A Home Assistant **package** that adds read+write controls for LG webOS TV
settings the built-in `webostv` integration doesn't surface:

| Entity | Reads | Writes |
| --- | --- | --- |
| `select.lg_webos_tv_power_saving_step` | TV's Energy Saving step (Auto / Off / Minimum / Medium / Maximum) | Sets `picture.energySaving` |
| `select.lg_webos_tv_hdmi_input` | Current source (from the `media_player` entity) | Calls `media_player.select_source` |
| `switch.lg_webos_tv_screen` | `'Active'` ↔ on, anything else ↔ off | Calls `turnOnScreen` / `turnOffScreen` |
| `switch.lg_webos_tv_eye_comfort_mode` | TV's Eye Comfort Mode | Sets `picture.eyeComfortMode` |

Pure YAML, no custom integration. The TV is polled every 5 s by a small
Python helper that piggybacks on `aiowebostv` (already installed by the
built-in `webostv` integration). Writes go through the built-in
`webostv.command` service.

Tested on an LG C5 (webOS 25). The setting keys are common across recent
LG OLEDs, so B / C / G series of similar vintage should work.

## Requirements

- The built-in [`webostv`](https://www.home-assistant.io/integrations/webostv/)
  integration is set up and paired with the TV.
- `default_config:` is enabled (loads the `command_line` integration).

## Install

```bash
cd /config
git clone https://github.com/sthaber/ha-lg-webos-remote.git
```

Then add this to `configuration.yaml`:

```yaml
homeassistant:
  packages:
    lg_webos_remote: !include ha-lg-webos-remote/lg_webos_remote.yaml
```

Restart HA. After the first 5 s poll cycle you should have these entities:

- `sensor.lg_webos_tv_state`
- `select.lg_webos_tv_power_saving_step`
- `select.lg_webos_tv_hdmi_input`
- `switch.lg_webos_tv_screen`
- `switch.lg_webos_tv_eye_comfort_mode`

## Configuration

Two spots in `lg_webos_remote.yaml` you may want to edit:

1. **`entity_id: media_player.lg_webos_tv`** — change throughout the file
   if your TV's `media_player` entity_id differs.
2. **HDMI input list** — `['PS5', 'AVR', 'Switch 2', 'Apple TV']` — change
   to match the labels you've set on your TV. (Find them in the TV's input
   menu, or read `media_player.lg_webos_tv` → `source_list` attribute in
   Developer Tools.)

The polling script reads host + client key from your existing `webostv`
config entry in `.storage/`, so no credentials need to be configured here.

## Dashboard

A working dashboard for these controls (paste into the raw editor of any
view):

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: heading
        heading: LG webOS TV
      - type: tile
        entity: media_player.lg_webos_tv
        name: Power
        icon: mdi:power
        tap_action:
          action: toggle
      - type: tile
        entity: select.lg_webos_tv_power_saving_step
        name: Power Saving Step
      - type: tile
        entity: switch.lg_webos_tv_screen
        name: Screen
        features:
          - type: toggle
      - type: tile
        entity: switch.lg_webos_tv_eye_comfort_mode
        name: Eye Comfort Mode
        features:
          - type: toggle
      - type: tile
        entity: select.lg_webos_tv_hdmi_input
        name: HDMI Input
```

When the TV is off, the four read-dependent entities go to `unavailable`
(their `availability:` template depends on the polling script reaching the
TV), and the dashboard tiles render greyed. The Power tile uses the stock
`media_player` entity so it can also turn the TV off; turning it on
requires Wake-on-LAN, which is out of scope for this package.

## How it works

- `scripts/read_lg_tv.py` connects via `aiowebostv` with the credentials
  cached in `.storage/`, fetches the three relevant settings in two SSAP
  requests, and prints the result as JSON.
- `sensor.lg_webos_tv_state` is a `command_line` sensor that runs the
  script every 5 s and exposes the JSON fields as state + attributes.
- The four `select`/`switch` entities are `template:` entities. Their
  `state:` reads from the sensor; their write paths call `webostv.command`
  with the appropriate luna URI + payload.
- `availability:` on each entity is keyed off whether the script's last
  poll succeeded, so they go `unavailable` together when the TV is off.

## Known limitations

- **No Wake-on-LAN.** The Power tile turns the TV off via the existing
  websocket; waking from off requires WoL set up separately. The path is
  documented in HA's docs.
- **Polling lag.** Changes made via the TV's own remote show up in HA
  within ~5 s (one `scan_interval`).
- **TruMotion sliders.** `truMotionMode` is readable via SSAP with
  `current_app: true`, but the per-slider `truMotionJudder` /
  `truMotionBlur` keys are not on LG's SSAP allowlist; writing them
  requires the [alert-hack technique][1] used by `aiopylgtv`, which
  doesn't return values (so they're write-only). Left out of this package.
- **Dolby Vision picture mode** hides some keys. The current `pictureMode`
  affects which settings the TV will return; if you find an entity stuck
  showing the wrong value, check whether the TV is in a Dolby HDR mode.

[1]: https://github.com/bendavid/aiopylgtv/blob/master/aiopylgtv/webos_client.py

## Extending

To add another simple read+write setting:

1. Find the SSAP key by probing `settings/getSystemSettings` with
   `{"category": "picture", "keys": ["<candidate>"]}` (or `"current_app":
   true` for keys outside the public allowlist).
2. Add the key to the `keys:` list in the script and to `json_attributes:`
   on the sensor.
3. Add a `template:` entity that reads from `state_attr('sensor.lg_webos_tv_state', '<your_attr>')`
   and writes via a `webostv.command` action.

## License

MIT — see [LICENSE](LICENSE).
