# Oblivion Buddy

## Configuration

Create a file named `.env` with your configuration.

Example:

```ini
DISCORD_TOKEN="discord-secret"
RCON_PASS="rcon-secret"
RCON_IP="192.168.2.3"
```

## Discord setup

In the [Discord Developer Portal](https://discord.com/developers/applications),
under **Bot → Privileged Gateway Intents**, enable:

- **Server Members Intent** — required for welcome/goodbye cards and auto-roles
- **Message Content Intent** — required for XP from messages

Server-specific IDs (guild, channels, roles) live in `config.py`. If you run the
bot in another server, update `GUILD_ID` and the `Channel`/`Role` IDs there,
otherwise slash commands like `/rank` won't show up and welcome cards won't be sent.
The bot logs a warning on startup if the guild or welcome channel can't be found.

## How to run

```sh
uv run main.py
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