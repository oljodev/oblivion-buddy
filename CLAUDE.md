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

No lint or test commands are configured — testing is manual.

## Architecture

Oblivion Buddy is a Discord bot for a Minecraft SMP community, built with `discord.py`. It uses the **Cog system** for feature isolation.

### Entry Point

`main.py` auto-discovers and loads all cogs from `./cogs/`. Both flat files (`cogs/file.py`) and subdirectories (`cogs/subfolder/file.py`) are supported. Each cog must export `async def setup(bot)`. Slash commands are synced to a single guild on startup.

### Cog Modules

| Path | Purpose |
|---|---|
| `features_with_minecraft/` | Server status (60s RCON poll), give/restart commands |
| `advanced_analytics/` | JSON-backed message/voice/MC login tracking, daily score |
| `leveling_system/` | XP leveling, role rewards, rank cards via `easy_pil` |
| `giveaway/` | Giveaway lifecycle (start, enter, reroll) |
| `ticket/` | Support tickets in private threads |
| `poll/` | Timed polls with reaction tracking |
| `log/` | Boost notifications, crash/restart event logging |
| `welcome/` | Welcome/goodbye image cards |
| `security_and_filters/` | App verification with approve/kick/ban flow |

### Data Persistence

No database — all state lives in JSON files inside the cog directories (e.g. `leveling_system/level_tracking.json`, `giveaway/giveaways.json`). Load/save helpers are co-located with each cog.

### RCON Integration

Minecraft server communication uses `aiomcrcon`. RCON credentials and server IP come from `.env`. Connection errors are caught and logged but do not crash the bot.

### Configuration

All config is via `.env`:
```
DISCORD_TOKEN=
RCON_PASS=
RCON_IP=
RCON_PORT=
```

Discord IDs (guild, channels, roles) are hardcoded as module-level constants in each cog — this is intentional for a single-server bot.

### Key Patterns

- Background jobs use `@tasks.loop()` (status refresh every 60s, RCON player poll every 15m)
- Role-based auth is checked inline; unauthorized users get silent failure
- Giveaway JSON writes use atomic temp-file replace to avoid corruption
- Comments throughout the codebase are in Norwegian
