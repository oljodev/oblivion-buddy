# Oblivion Buddy

## Configuration

Create a file named `.env` with your configuration.

Example:

```ini
DISCORD_TOKEN="discord-secret"
RCON_PASS="rcon-secret"
RCON_IP="192.168.2.3"
```

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
journalctl --user -feu obvlivion-buddy
```