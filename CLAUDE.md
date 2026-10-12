# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
uv run main.py
```

Production runs as a systemd user service:
```bash
systemctl --user start|stop|restart oblivion-buddy
journalctl --user -feu oblivion-buddy
```

Lint with `uv run ruff check .` (config in `pyproject.toml`). There are no automated tests — testing is manual.

## Architecture

Oblivion Buddy is a Discord bot for a Minecraft SMP community, built with `discord.py`. It uses the **Cog system** for feature isolation.

### Entry Point

`main.py` auto-discovers and loads all cogs from `./cogs/`. Both flat files (`cogs/file.py`) and subdirectories (`cogs/subfolder/file.py`) are supported. Each cog must export `async def setup(bot)`. Slash commands are synced to a single guild on startup.

### Cog Modules

| Path | Purpose |
|---|---|
| `features_with_minecraft/` | Server status (60s RCON poll), `!give` command |
| `advanced_analytics/` | JSON-backed message/voice/MC login tracking, daily score |
| `leveling_system/` | XP leveling, role rewards, rank cards via `easy_pil` |
| `giveaway/` | Giveaway lifecycle (start, enter, reroll) |
| `ticket/` | Support tickets in private threads |
| `poll/` | Timed polls with reaction tracking |
| `log/` | Boost notifications, crash/restart event logging |
| `welcome/` | Welcome/goodbye image cards |
| `help/` | `/help` and `!help` — built from loaded commands; staff section only for staff |
| `security_and_filters/` | App verification with approve/kick/ban flow |

### Data Persistence

No database — all state lives in JSON files inside the cog directories (e.g. `leveling_system/level_tracking.json`, `giveaway/giveaways.json`). Load/save helpers are co-located with each cog.

### RCON Integration

Minecraft server communication uses `aiomcrcon`. RCON credentials and server IP come from `.env`. Connection errors are caught and logged but do not crash the bot.

### Configuration

`config.py` is the single source of configuration:
- Secrets and connection settings come from `.env` (see `.env.example`): `DISCORD_TOKEN`, `RCON_IP`, `RCON_PORT`, `RCON_PASS`, and optional `MINIGAME_DISCORD_TOKEN`, `GEMINI_API_KEY`, `CURSEFORGE_API_KEY`. Import them from `config` rather than calling `os.getenv` in cogs.
- Discord IDs are exposed as `GUILD_ID`, `Channel.*` and `Role.*`. Defaults are the Oblivion SMP IDs; an optional git-ignored `server_config.toml` (see `server_config.example.toml`) overrides them for other servers. When adding a channel/role, add it to the defaults in `config.py` and to the example file.
- On startup `main.py` logs every configured channel/role missing from the guild.

### Key Patterns

- Background jobs use `@tasks.loop()` (status refresh every 60s, RCON player poll every 15m)
- Role-based auth is checked inline; unauthorized users get silent failure
- All JSON persistence goes through `cogs/_shared/json_store.py`: `save_json()` writes atomically, `load_json()` moves a corrupt file aside (`*.corrupt-<timestamp>`) instead of silently overwriting it
- Hot-path data is kept in memory: analytics (`analytics_core`, flushed every 30s), staff stats (saved by its 60s loop), level tracking and pet ownership. On SIGTERM/SIGINT `main.py` unloads all cogs so their `cog_unload` can flush before exit
- Comments throughout the codebase are in Norwegian
