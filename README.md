# SoupBot

A silly Discord bot that runs on soup.

## Usage

### Requirements

- Either Docker or a Python 3.9 virtualenv on `venv/`
- A registered Discord bot with the following scopes:
  - bot
    - Read Messages/View Channels
    - Send Messages
    - Embed Links
    - Use External Emojis
    - Use External Stickers
    - Add Reactions
    - Manage Messages (optional)
- A Wit.AI application that parses `wit/datetime:datetime` entities (I've used the `wit/get_time` intent for this).
- sqlite3

### Setup

Create a SQLite database to `./discord_bot.db` (create by invoking `sqlite3` in the root directory):

```sql
CREATE TABLE users(id VARCHAR(24) PRIMARY KEY, tz TEXT, last_modified TEXT);
CREATE TABLE dinkdonk(server_id VARCHAR(24), user_id VARCHAR(24), count INTEGER, lifetime_count INTEGER, should_alert INTEGER DEFAULT FALSE, last_modified TEXT, PRIMARY KEY (server_id, user_id));
CREATE TABLE cross_dinkdonks(server_id VARCHAR(24), to_user_id VARCHAR(24), from_user_id VARCHAR(24), count INTEGER, last_modified TEXT, PRIMARY KEY (server_id, to_user_id, from_user_id));
CREATE TABLE dinkdonk_cache(server_id VARCHAR(24) PRIMARY KEY, value INTEGER);
CREATE TABLE availability(server_id VARCHAR(24), user_id VARCHAR(24), on_date VARCHAR(10), is_available INTEGER, description TEXT, last_modified TEXT, PRIMARY KEY (server_id, user_id, on_date));
.save discord_bot.db
```

If you're using Docker, create a Docker Compose deployment in `./compose.yaml` (deploy with `docker compose up --build -d`; optionally can set up a `systemctl` service that runs it on startup):

```yaml
services:
  soupbot:
    container_name: soupbot
    build:
      context: .
    environment:
      SOUPBOT_DISCORD_TOKEN: YOUR_DISCORD_TOKEN
      SOUPBOT_WIT_TOKEN: YOUR_WIT_AI_TOKEN
      SOUPBOT_CUSTOM_HELLO: "This is the message sent by SoupBot whenever you use the custom command $hello"
    volumes:
      - ./discord_bot.db:/usr/src/app/discord_bot.db
    restart: unless-stopped
```
