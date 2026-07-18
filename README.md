# Discord Cultivation Bot

This is a simple beginner-friendly Discord bot foundation for a cultivation-style game.

## Project structure
- main.py: starts the bot and handles the !ping command
- database.py: creates the SQLite database and players table
- data/: stores the SQLite file
- requirements.txt: Python packages needed for the bot

## Setup
1. Install dependencies:
   pip install -r requirements.txt
2. Set your bot token:
   set DISCORD_TOKEN=your_bot_token_here
3. Start the bot:
   python main.py

## Notes
- This step only includes the basic bot and database setup.
- No game features are added yet.
