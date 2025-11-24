# Telegram Broadcast Bot

## Overview
This is a Telegram bot for broadcasting messages to multiple chats. It allows an admin user to send any type of message (text, media, etc.) to all chats where the bot has been added. The bot provides an interactive interface for selecting which chats should receive each broadcast.

**Current State**: Fully configured and running in the Replit environment.

## Recent Changes
- **2024-11-24**: Initial setup in Replit environment
  - Installed Python 3.11 and dependencies
  - Configured environment secrets (BOT_TOKEN, ADMIN_USER_ID)
  - Created workflow to run the bot
  - Added .gitignore for Python project

## Project Architecture

### Language & Framework
- **Python 3.11** with python-telegram-bot library (v21.6)
- Uses async/await for all Telegram API interactions

### Structure
```
src/
├── main.py       - Main bot application with handlers and commands
└── storage.py    - Thread-safe JSON storage for chat records

data/
└── chats.json    - Stores information about chats the bot is in
```

### Key Features
1. **Automatic Chat Management**: Bot remembers chats it's added to and forgets removed chats
2. **Chat Control Commands**: `/chats`, `/enable`, `/disable`, `/forget` for managing chat list
3. **Broadcast Wizard**: `/broadcast` command starts interactive message broadcasting
4. **Message Copying**: Uses Telegram's `copyMessage` API to support all content types

### Commands
- `/start` - Welcome message
- `/help` - Show available commands
- `/chats` - List all chats (admin only)
- `/enable <chat_id>` - Enable chat for broadcasts (admin only)
- `/disable <chat_id>` - Disable chat from broadcasts (admin only)
- `/forget <chat_id>` - Remove chat from database (admin only)
- `/broadcast` - Start broadcast wizard (admin only)

### Environment Configuration
The bot requires two secrets (configured in Replit Secrets):
- `BOT_TOKEN` - Telegram bot token from @BotFather
- `ADMIN_USER_ID` - Telegram user ID of the bot admin

Optional environment variable:
- `CHAT_STORE_PATH` - Path to chats JSON file (defaults to `data/chats.json`)

### Data Storage
- Chat records are stored in `data/chats.json`
- Storage is thread-safe with RLock
- Each chat record includes: chat_id, title, chat_type, enabled status, and last update timestamp

## Workflow
- **Start Telegram Bot**: Runs `python -m src.main` to start the bot in polling mode
- Output type: Console (backend service)

## How to Use
1. Add the bot to your desired Telegram groups or channels
2. The bot will automatically save these chats
3. In a private chat with the bot, use `/broadcast` to start a broadcast
4. Send the message you want to broadcast
5. Select which chats should receive it using the interactive buttons
6. Confirm to send

## User Preferences
None specified yet.

## Notes
- Bot uses long polling (not webhooks) to receive updates
- All admin commands only work in private chats with the bot
- The ConversationHandler is used for the multi-step broadcast workflow
