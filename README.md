# ha-lg-webos-remote

A Home Assistant **package** that adds read+write controls for LG webOS TV
settings the built-in `webostv` integration doesn't surface:

| Entity | Reads | Writes |
| --- | --- | --- |
| `select.lg_webos_tv_power_saving_step` | TV's Energy Saving step (Auto / Off / Minimum / Medium / Maximum) | Sets `picture.energySaving` |
| `select.lg_webos_tv_hdmi_input` | Current source (from the `media_player` entity) | Calls `media_player.select_source` |
| `switch.lg_webos_tv_screen` | `'Active'` ↔ on, anything else ↔ off | Calls `turnOnScreen` / `turnOffScreen` |
| `switch.lg_webos_tv_eye_comfort_mode` | TV's Eye Comfort Mode | Sets `picture.eyeComfortMode` |

A YAML package plus a small Python script — no custom integration, no
HACS install. The script (`tv.py`) piggybacks on `aiowebostv` (already
installed by the built-in `webostv` integration) to read state from the TV
every 5 s, and also carries out the two settings writes.

I built this to change settings quickly that are otherwise deeply buried
in slow menus. In particular, the power saving step is really the only way
to adjust brightness globally across video modes. There are a slew of
horrible LG remotes on the iOS store but none of them that I looked at
seemed to allow adjusting these specific settings.

Tested on an LG C5 (webOS 25, firmware 33.31.69).

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
    lg_webos_remote: !include ha-lg-webos-remote/entities.yaml
```

Restart HA. After the first 5 s poll cycle you should have these entities:

- `sensor.lg_webos_tv_state`
- `select.lg_webos_tv_power_saving_step`
- `select.lg_webos_tv_hdmi_input`
- `switch.lg_webos_tv_screen`
- `switch.lg_webos_tv_eye_comfort_mode`

Note the package defines a `shell_command`, which is a new integration for
most configs, so a full restart is needed the first time — a
`template.reload` isn't enough.

## Configuration

Two spots in `entities.yaml` you may want to edit:

1. **`entity_id: media_player.lg_webos_tv`** — change throughout the file
   if your TV's `media_player` entity_id differs.
2. **HDMI input list** — `['PS5 Game Console', 'AVR', 'Switch 2', 'Apple OTT']` —
   change to match the labels you've set on your TV. These have to match the
   TV's labels exactly; if the active input isn't in the list, the entity
   reads `unknown`. (Find them in the TV's input menu, or read
   `media_player.lg_webos_tv` → `source_list` attribute in Developer Tools.)

The script reads host + client key from your existing `webostv`
config entry in `.storage/`, so no credentials need to be configured here.

## Dashboard

[`dashboard.yaml`](dashboard.yaml) is a full YAML-mode dashboard you can
either *register live* (recommended) or copy from.

**Register as a live dashboard.** Add to `configuration.yaml` (alongside
the `packages:` block):

```yaml
lovelace:
  mode: storage   # leave the default dashboard storage-managed
  dashboards:
    webos-tv:     # the URL path; YAML-mode dashboards must contain a hyphen
      mode: yaml
      filename: ha-lg-webos-remote/dashboard.yaml
      title: TV
      icon: mdi:television
      show_in_sidebar: true
      require_admin: false
```

After a restart, the dashboard appears in the sidebar and is read directly
from this file. `git pull`ing future changes shows up after another
restart (or a `lovelace.reload_resources` for asset-only changes).

**Copy as a snippet.** Open `dashboard.yaml`, extract the contents of
`views[0]`, and paste into a view's raw YAML editor (Edit Dashboard →
Take Control → raw config).

When the TV is off, the four read-dependent entities go to `unavailable`
(their `availability:` template depends on the polling script reaching the
TV), and the dashboard tiles render greyed. The Power tile uses the stock
`media_player` entity so it can also turn the TV off; turning it on
requires Wake-on-LAN, which is out of scope for this package.

## How it works

- `tv.py` connects via `aiowebostv` with the credentials cached in
  `.storage/`. With no arguments it fetches the three relevant settings in
  two SSAP requests and prints them as JSON; with
  `set <category> <key> <value>` it writes one setting.
- `sensor.lg_webos_tv_state` is a `command_line` sensor that runs the
  script every 5 s and exposes the JSON fields as state + attributes.
- The four `select`/`switch` entities are `template:` entities. Their
  `state:` reads from the sensor. Power saving step and eye comfort mode
  write via `shell_command.lg_webos_tv_set` → `tv.py set`; screen on/off
  writes via the `webostv.command` service; HDMI input writes via
  `media_player.select_source`.
- `availability:` on each entity is keyed off whether the script's last
  poll succeeded, so they go `unavailable` together when the TV is off.

### Why the settings writes don't use `webostv.command`

The TV answers `settings/setSystemSettings` with `401 insufficient
permissions` for every category. A webOS client sends a permission manifest
when it pairs, and the TV only honours `WRITE_SETTINGS` from a manifest
carrying an LG signature. Earlier versions of this package borrowed the
public `com.lge.test` signed manifest; firmware 33.31.69 blacklisted that
certificate (`403 Pairing rejected: blacklisted certificate detected`), so
that path is gone.

Instead, `tv.py` runs the write as a `luna://` call attached to a
notification alert. `system.notifications/createAlert` takes a luna URI and
parameters as the alert's close action, and `closeAlert` runs it. This needs
only `WRITE_NOTIFICATION_ALERT`, which the TV grants to ordinary clients, and
it's the same mechanism bscpylgtv and newer aiowebostv use for luna calls.
Because it takes two requests (the second needs the `alertId` from the
first), it can't be expressed as a single `webostv.command` call, hence the
`shell_command`.

## Known limitations

- **No Wake-on-LAN.** The Power tile turns the TV off via the existing
  websocket; waking from off requires WoL set up separately. The path is
  documented in HA's docs.
- **Polling lag.** Changes made via the TV's own remote show up in HA
  within ~5 s (one `scan_interval`). The write paths ask the sensor to
  refresh immediately, so the UI doesn't wait a full cycle.
- **The TV drops connections that arrive close together.** Every call opens
  its own websocket, so a write landing next to a poll can lose the race.
  Writes retry a few times; a lost read just leaves the entities
  unavailable until the next poll.

## Extending

To add another simple read+write setting:

1. Find the SSAP key by probing `settings/getSystemSettings` with
   `{"category": "picture", "keys": ["<candidate>"]}` (or `"current_app":
   true` for keys outside the public allowlist).
2. Add the key to the `keys:` list in `tv.py` and to `json_attributes:`
   on the sensor.
3. Add a `template:` entity that reads from `state_attr('sensor.lg_webos_tv_state', '<your_attr>')`
   and writes via `shell_command.lg_webos_tv_set`.

## License

MIT — see [LICENSE](LICENSE).
