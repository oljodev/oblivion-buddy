# Oblivion Buddy

Discord bot for the Oblivion SMP Minecraft community.

## Setup

### 1. Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/oljodev/oblivion-buddy.git
cd oblivion-buddy
uv sync          # installs Python and all dependencies
```

### 2. Create the Discord bot

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. Create an application → **Bot** → **Reset Token** and copy the token.
2. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent** — required for welcome/goodbye cards and auto-roles
   - **Message Content Intent** — required for XP from messages
3. Under **OAuth2 → URL Generator**, tick `bot` and `applications.commands`, give it
   the permissions below, and open the URL to invite it to your server:
   - Manage Server (to track invites for invite XP), Manage Roles, Kick Members, Ban Members
   - Create Instant Invite, Create Public/Private Threads, Manage Threads, Send Messages in Threads
   - View Channels, Send Messages, Embed Links, Attach Files, Add Reactions, Read Message History
4. In **Server Settings → Roles**, drag the bot's role **above** the roles it hands
   out (Member, Level roles, Connected Account), or it can't give them.

### 3. Secrets: `.env`

```sh
cp .env.example .env
```

Fill in `DISCORD_TOKEN` and the `RCON_*` settings. The other keys are optional —
leave them empty to turn those features off.

### 4. Server IDs: `server_config.toml` (only if this isn't the Oblivion SMP server)

The channel and role IDs default to the Oblivion SMP server. To run the bot in
your own server:

```sh
cp server_config.example.toml server_config.toml
```

Turn on **Developer Mode** in Discord (User Settings → Advanced), then right-click
your server, channels and roles → **Copy ID** and paste them into the file.

Some roles are looked up by **name** instead of ID — create them if you want the feature:

- `Level 5`, `Level 10`, … `Level 100` — level reward roles
- `Dev Team` — used by the XP test mode in `cogs/_shared/dev_mode.py`

### 5. Run

```sh
uv run main.py
```

On startup the bot logs every configured channel/role it can't find, e.g.
`channel welcome = 0 not found`. Fix those in `server_config.toml` and restart.

### Running as a service (optional)

`~/.config/systemd/user/oblivion-buddy.service`:

```ini
[Unit]
Description=Oblivion Buddy Discord bot
After=network-online.target

[Service]
WorkingDirectory=%h/oblivion-buddy
ExecStart=%h/.local/bin/uv run main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now oblivion-buddy
loginctl enable-linger $USER   # keep it running when you log out
```

## Development on server

Stop the service:

```sh
systemctl --user stop oblivion-buddy
```

Do your changes to the project. You may test it by running the project from e.g. VS Code using `uv run main.py`.

When you're done with development, start the service again:

```sh
systemctl --user start oblivion-buddy
```

If the service doesn't work, it can be restarted with:

```sh
systemctl --user restart oblivion-buddy
```

To see the service logs, run:

```sh
journalctl --user -feu oblivion-buddy
```