# Hell Let Loose Map Ban Bot

A Discord bot that handles per-side map bans for competitive Hell Let Loose matches.

## How to Run Locally

```bash
pip install -r requirements.txt
python map_ban_bot.py


Commands Overview
!mb_new

Create a new map-ban session in the current channel.

!mb_teams @Captain1 @Captain2

Assign the two captains for the session.

!mb_start

Start the map-ban and flip a coin for first ban.

!mb_status

Show current map-ban status (bannable maps, locks, fully banned maps, turn order).

!mb_pool

Show the full map pool the bot uses.

!mb_cancel

Cancel the current session (creator or admin only).

!mb_undo

Undo the last ban (creator or admin only).

!mb_help

Show the help menu and usage instructions.

!mb_guilds (bot owner only)

List the servers the bot is currently in.


#If you run into issues with Discord_Bot_Token use the following codes

# See what’s currently set
echo "$DISCORD_BOT_TOKEN"

# Clear it
unset DISCORD_BOT_TOKEN

# Optional: confirm it’s gone (should print a blank line)
echo "$DISCORD_BOT_TOKEN"

# Now run your bot
python map_ban_bot.py
