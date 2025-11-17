import os
import random
import discord
from discord.ext import commands

# --------------- CONFIG ---------------

BOT_PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# --------------- STATIC MAP POOL (YOUR LIST) ---------------

MAP_POOL = [
    "Foy",
    "Foy Night",
    "Hill 400",
    "Hurtgen Forest",
    "Hurtgen Forest Night",
    "Kursk",
    "Kursk Night",
    "Omaha Beach",
    "Omaha Beach Dusk",
    "PHL",
    "PHL Night",
    "Remagen",
    "Remagen Night",
    "Sainte-Mère-Église",
    "Sainte-Mère-Église Night",
    "Sainte-Marie-du-Mont",
    "Sainte-Marie-du-Mont Night",
    "Carentan",
    "Carentan Night",
    "Stalingrad",
    "Stalingrad Night",
    "Utah Beach",
    "Utah Beach Night",
    "El-Alamein",
    "El-Alamein Dusk",
    "Driel",
    "Driel Night",
    "Elsenborn Ridge",
    "Elsenborn Ridge Dawn",
    "Elsenborn Ridge Night",
    "Kharkov Night",
    "Mortain",
    "Mortain Overcast",
    "Mortain Dusk",
    "Smolensk",
    "Tobruk",
    "Tobruk Dawn",
    "Tobruk Dusk",
]

# One map-ban session per channel
map_ban_sessions = {}  # {channel_id: MapBanSession}


class MapBanSession:
    def __init__(self, channel_id, created_by, maps):
        self.channel_id = channel_id
        self.created_by = created_by  # discord.Member
        self.maps = maps[:]           # list of map names
        self.team1 = None             # discord.Member
        self.team2 = None             # discord.Member
        self.current_turn = None      # discord.Member
        self.status = "setup"         # "setup", "banning", "finished"

        # allowed_sides[team_id][map_name] = set of {"Allies","Axis"} still allowed for that team
        self.allowed_sides = {}
        # set of map names that are totally dead (no legal side assignments)
        self.fully_banned_maps = set()
        # list of dicts: {"map": ..., "side": ..., "by": member}
        self.ban_history = []

    # ---------- Team / sides setup ----------

    def initialize_allowed_sides(self):
        """Call once teams are set."""
        if not (self.team1 and self.team2):
            return
        self.allowed_sides = {
            self.team1.id: {m: {"Allies", "Axis"} for m in self.maps},
            self.team2.id: {m: {"Allies", "Axis"} for m in self.maps},
        }
        self.fully_banned_maps = set()
        self.ban_history = []

    def is_captain(self, member: discord.Member) -> bool:
        return member and (member == self.team1 or member == self.team2)

    def other_captain(self, member: discord.Member):
        if not self.is_captain(member):
            return None
        return self.team1 if member == self.team2 else self.team2

    # ---------- Map / side logic ----------

    def _legal_assignment(self, map_name: str, team1_side: str, team2_side: str) -> bool:
        """Check if this side pairing is legal for both teams on a map."""
        if not self.allowed_sides:
            return False
        t1 = self.allowed_sides.get(self.team1.id, {}).get(map_name, set())
        t2 = self.allowed_sides.get(self.team2.id, {}).get(map_name, set())
        return (team1_side in t1) and (team2_side in t2)

    def is_map_playable(self, map_name: str) -> bool:
        """Map is playable if at least one side assignment is legal."""
        if not self.allowed_sides:
            return True  # before banning starts, everything is playable
        return (
            self._legal_assignment(map_name, "Allies", "Axis") or
            self._legal_assignment(map_name, "Axis", "Allies")
        )

    def recompute_fully_banned(self):
        """Recalculate which maps are completely dead."""
        if not self.allowed_sides:
            self.fully_banned_maps = set()
            return

        dead = set()
        for m in self.maps:
            if not self.is_map_playable(m):
                dead.add(m)
        self.fully_banned_maps = dead

    def map_available_for_ban(self, map_name: str) -> bool:
        """A map is 'available for ban' if it's not fully dead and someone still has a side to ban."""
        if map_name in self.fully_banned_maps:
            return False
        if not self.allowed_sides:
            return True  # pre-init, treat as available
        any_bannable = False
        for team_id in (self.team1.id, self.team2.id):
            sides = self.allowed_sides.get(team_id, {}).get(map_name, set())
            if sides:  # any side left to ban
                any_bannable = True
                break
        return any_bannable

    def maps_still_available_for_ban(self):
        return [m for m in self.maps if self.map_available_for_ban(m)]

    # ---------- Ban handling ----------

    def find_map_partial(self, text: str, only_bannable: bool = True):
        """
        Case-insensitive partial map match.
        If only_bannable is True, restrict to maps still available for ban.
        """
        text = text.strip().lower()
        if not text:
            return None

        if only_bannable:
            candidates = [m for m in self.maps if self.map_available_for_ban(m)]
        else:
            candidates = self.maps[:]

        matches = [m for m in candidates if text in m.lower()]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            return "AMBIGUOUS"
        return matches[0]

    def register_ban(self, member: discord.Member, map_name: str, side: str):
        """
        Apply a ban: member refuses to play 'side' on 'map_name'.
        Returns (success: bool, msg: str)
        """
        if not self.allowed_sides:
            return False, "Internal error: allowed sides not initialized."

        team_id = member.id
        if team_id not in self.allowed_sides:
            return False, "You are not one of the captains for this session."

        sides_set = self.allowed_sides[team_id].get(map_name, set())
        if side not in sides_set:
            if not sides_set:
                return False, f"You have no sides left to ban on **{map_name}**."
            else:
                return False, f"You have already banned **{side}** on **{map_name}**."

        # Remove the side for this team on that map
        sides_set.remove(side)
        self.allowed_sides[team_id][map_name] = sides_set
        self.ban_history.append({"map": map_name, "side": side, "by": member})

        # Recompute which maps are fully dead
        self.recompute_fully_banned()
        return True, f"{member.display_name} banned **{map_name} – {side}**."

    def playable_maps(self):
        return [m for m in self.maps if m not in self.fully_banned_maps and self.is_map_playable(m)]

    def is_finished(self):
        """Finish when <= 1 playable map remains."""
        return len(self.playable_maps()) <= 1

    def get_final_map_and_sides(self):
        """
        When finished, determine final map and sides.
        If multiple playable maps left, pick one at random.
        For that map, pick a legal side assignment (random if both legal).
        """
        pmaps = self.playable_maps()
        if not pmaps:
            return None, None, None  # no map left
        final_map = pmaps[0] if len(pmaps) == 1 else random.choice(pmaps)

        # Determine legal assignments
        options = []
        if self._legal_assignment(final_map, "Allies", "Axis"):
            options.append(("Allies", "Axis"))
        if self._legal_assignment(final_map, "Axis", "Allies"):
            options.append(("Axis", "Allies"))

        if not options:
            # Shouldn't happen if playable_maps is correct, but just in case
            return final_map, None, None

        t1_side, t2_side = random.choice(options)
        return final_map, t1_side, t2_side


# --------------- HELPER FUNCTIONS ---------------

def format_list_as_bullets(items):
    if not items:
        return "*(none)*"
    return "\n".join(f"- {i}" for i in items)


async def send_session_status(ctx, session: MapBanSession, title="Map Ban Status"):
    embed = discord.Embed(title=title)

    team1_name = session.team1.display_name if session.team1 else "Not set"
    team2_name = session.team2.display_name if session.team2 else "Not set"

    embed.add_field(name="Team 1 Captain", value=team1_name, inline=True)
    embed.add_field(name="Team 2 Captain", value=team2_name, inline=True)
    embed.add_field(name="Status", value=session.status.capitalize(), inline=True)

    # Maps still available for ban
    if session.status == "banning" and session.allowed_sides:
        bannable = session.maps_still_available_for_ban()
        embed.add_field(
            name=f"Maps Still Available for Ban ({len(bannable)})",
            value=format_list_as_bullets(bannable),
            inline=False,
        )
    else:
        embed.add_field(
            name=f"Map Pool ({len(session.maps)})",
            value=format_list_as_bullets(session.maps),
            inline=False,
        )

    # Per-map side status (only once banning has started)
    if session.status in ("banning", "finished") and session.allowed_sides and session.team1 and session.team2:
        lines = []
        t1_id = session.team1.id
        t2_id = session.team2.id
        for m in session.maps:
            if m in session.fully_banned_maps:
                continue  # show in separate section
            if not session.is_map_playable(m):
                continue
            t1_sides = session.allowed_sides.get(t1_id, {}).get(m, set())
            t2_sides = session.allowed_sides.get(t2_id, {}).get(m, set())

            def fmt_sides(s):
                if not s:
                    return "None"
                if s == {"Allies", "Axis"}:
                    return "Allies/Axis"
                return "/".join(sorted(s))

            lines.append(
                f"{m} – {session.team1.display_name}: {fmt_sides(t1_sides)} | "
                f"{session.team2.display_name}: {fmt_sides(t2_sides)}"
            )

        embed.add_field(
            name="Playable Map Side Status",
            value="\n".join(lines) if lines else "*(none)*",
            inline=False,
        )

        # Fully banned maps
        dead = sorted(list(session.fully_banned_maps))
        if dead:
            embed.add_field(
                name=f"Fully Banned Maps ({len(dead)})",
                value=format_list_as_bullets(dead),
                inline=False,
            )

    # Whose turn?
    if session.status == "banning" and session.current_turn:
        embed.add_field(
            name="Current Turn",
            value=f"{session.current_turn.mention} – type `<map> <side>` "
                  f"(e.g. `foy allies`, `remagen axis`).",
            inline=False,
        )

    await ctx.send(embed=embed)


def parse_side(text: str):
    """
    Try to extract side from text. Returns "Allies" / "Axis" / None.
    """
    text = text.lower()
    tokens = text.split()

    side = None
    for tok in tokens:
        if tok in ("allies", "ally", "a"):
            side = "Allies"
            break
        if tok in ("axis", "x"):
            side = "Axis"
            break
    return side


def strip_side_from_text(text: str, side: str):
    """
    Remove side word(s) from text so we can match map.
    Very simple: drops tokens recognized as that side.
    """
    tokens = text.split()
    side_tokens_allies = {"allies", "ally", "a"}
    side_tokens_axis = {"axis", "x"}

    cleaned = []
    for tok in tokens:
        low = tok.lower()
        if side == "Allies" and low in side_tokens_allies:
            continue
        if side == "Axis" and low in side_tokens_axis:
            continue
        cleaned.append(tok)
    return " ".join(cleaned).strip()


# --------------- COMMANDS ---------------

@bot.command(name="mb_new")
async def mb_new(ctx):
    """
    Create a new map-ban session in this channel using the fixed map pool.
    Usage: !mb_new
    """
    if not MAP_POOL:
        await ctx.send("Map pool is empty. Ask an admin to edit the MAP_POOL list in the bot code.")
        return

    session = MapBanSession(channel_id=ctx.channel.id, created_by=ctx.author, maps=MAP_POOL)
    map_ban_sessions[ctx.channel.id] = session

    await ctx.send(
        f"🗺️ Map-ban session created by {ctx.author.mention}.\n"
        f"Using standard map pool ({len(MAP_POOL)} maps)."
    )
    await send_session_status(ctx, session, title="Map Ban Session Created")
    await ctx.send("Now set captains with: `!mb_teams @Captain1 @Captain2`")


@bot.command(name="mb_pool")
async def mb_pool(ctx):
    """
    Show the fixed map pool configured in the bot.
    Usage: !mb_pool
    """
    if not MAP_POOL:
        await ctx.send("Map pool is currently empty in the bot configuration.")
        return

    embed = discord.Embed(title="Standard Map Pool")
    embed.add_field(
        name=f"{len(MAP_POOL)} Maps",
        value=format_list_as_bullets(MAP_POOL),
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.command(name="mb_teams")
async def mb_teams(ctx, team1: discord.Member, team2: discord.Member):
    """
    Set the two captains.
    Usage: !mb_teams @Captain1 @Captain2
    """
    session = map_ban_sessions.get(ctx.channel.id)
    if not session:
        await ctx.send("No active map-ban session in this channel. Create one with `!mb_new` first.")
        return

    if session.status != "setup":
        await ctx.send("Teams can only be set while the session is in setup stage.")
        return

    session.team1 = team1
    session.team2 = team2
    session.initialize_allowed_sides()

    await ctx.send(
        f"✅ Captains set: {team1.mention} vs {team2.mention}\n"
        f"Start banning with `!mb_start`."
    )
    ctx = await bot.get_context(ctx.message)
    await send_session_status(ctx, session, title="Captains Set")


@bot.command(name="mb_start")
async def mb_start(ctx):
    """
    Start the banning phase (coin flip for who bans first).
    Usage: !mb_start
    """
    session = map_ban_sessions.get(ctx.channel.id)
    if not session:
        await ctx.send("No active map-ban session in this channel. Create one with `!mb_new` first.")
        return

    if session.status != "setup":
        await ctx.send("Map-ban session has already started or finished.")
        return

    if not (session.team1 and session.team2):
        await ctx.send("You must set both captains with `!mb_teams @Captain1 @Captain2` before starting.")
        return

    if not session.allowed_sides:
        session.initialize_allowed_sides()

    session.status = "banning"
    session.current_turn = random.choice([session.team1, session.team2])

    await ctx.send(
        f"🎲 Coin flip! {session.current_turn.mention} bans **first**.\n"
        f"Type `<map> <side>` (e.g. `foy allies`, `driel axis`)."
    )
    await send_session_status(ctx, session, title="Map Ban Started")


@bot.command(name="mb_status")
async def mb_status(ctx):
    """
    Show current map-ban status.
    Usage: !mb_status
    """
    session = map_ban_sessions.get(ctx.channel.id)
    if not session:
        await ctx.send("No active map-ban session in this channel.")
        return

    await send_session_status(ctx, session)


@bot.command(name="mb_cancel")
async def mb_cancel(ctx):
    """
    Cancel/reset the map-ban session in this channel.
    Usage: !mb_cancel
    """
    session = map_ban_sessions.get(ctx.channel.id)
    if not session:
        await ctx.send("No active map-ban session in this channel.")
        return

    # Only creator or admin can cancel
    if ctx.author != session.created_by and not ctx.author.guild_permissions.administrator:
        await ctx.send("Only the session creator or an admin can cancel this session.")
        return

    del map_ban_sessions[ctx.channel.id]
    await ctx.send("❌ Map-ban session cancelled and cleared for this channel.")


@bot.command(name="mb_undo")
async def mb_undo(ctx):
    """
    Undo the last ban.
    Usage: !mb_undo
    """
    session = map_ban_sessions.get(ctx.channel.id)
    if not session:
        await ctx.send("No active map-ban session in this channel.")
        return

    if not session.ban_history:
        await ctx.send("There are no bans to undo.")
        return

    if ctx.author != session.created_by and not ctx.author.guild_permissions.administrator:
        await ctx.send("Only the session creator or an admin can undo bans.")
        return

    last = session.ban_history.pop()
    map_name = last["map"]
    side = last["side"]
    member = last["by"]

    # Restore the side for that member
    if session.allowed_sides and member.id in session.allowed_sides:
        session.allowed_sides[member.id][map_name].add(side)

    # Recompute fully banned after undo
    session.recompute_fully_banned()

    await ctx.send(f"↩️ Undo: restored **{side}** on **{map_name}** for {member.mention}.")
    ctx2 = await bot.get_context(ctx.message)
    await send_session_status(ctx2, session, title="Map Ban Updated (Undo)")


# --------------- MESSAGE HANDLER (FREE-TEXT BANS) ---------------

@bot.event
async def on_message(message: discord.Message):
    # Ignore bots
    if message.author.bot:
        return

    channel_id = message.channel.id
    session = map_ban_sessions.get(channel_id)

    # Handle banning via free text
    if session and session.status == "banning":
        if message.author == session.current_turn:
            content = message.content.strip()
            # Ignore commands
            if not content.startswith(BOT_PREFIX):
                # Parse side
                side = parse_side(content)
                if not side:
                    await message.channel.send(
                        f"{message.author.mention} please include a side: "
                        f"`allies` or `axis`. Example: `foy allies`."
                    )
                else:
                    # Strip side words and match map from remaining text
                    map_text = strip_side_from_text(content, side)
                    if not map_text:
                        await message.channel.send(
                            f"{message.author.mention} I couldn't see a map name. "
                            f"Use `<map> <side>`, e.g. `driel allies`."
                        )
                    else:
                        chosen_map = session.find_map_partial(map_text, only_bannable=True)
                        if chosen_map is None:
                            await message.channel.send(
                                f"{message.author.mention} I couldn't match that to any map still available for ban. "
                                f"Check `!mb_status` for the current list."
                            )
                        elif chosen_map == "AMBIGUOUS":
                            await message.channel.send(
                                f"{message.author.mention} that text matches **multiple** maps. "
                                f"Please be more specific."
                            )
                        else:
                            # Apply ban
                            success, msg = session.register_ban(message.author, chosen_map, side)
                            if not success:
                                await message.channel.send(f"{message.author.mention} {msg}")
                            else:
                                await message.channel.send(f"🚫 {msg}")

                                # Check if finished
                                if session.is_finished():
                                    session.status = "finished"
                                    final_map, t1_side, t2_side = session.get_final_map_and_sides()
                                    if final_map is None:
                                        await message.channel.send(
                                            "All possible map/side combinations have been banned. "
                                            "No valid map remains."
                                        )
                                    else:
                                        await message.channel.send(
                                            f"✅ Map-ban complete!\n"
                                            f"Final Map: **{final_map}**\n"
                                            f"{session.team1.display_name}: **{t1_side}**\n"
                                            f"{session.team2.display_name}: **{t2_side}**"
                                        )
                                    ctx = await bot.get_context(message)
                                    await send_session_status(ctx, session, title="Final Map-Ban Result")
                                    await bot.process_commands(message)
                                    return
                                else:
                                    # Switch turn
                                    session.current_turn = session.other_captain(message.author)
                                    await message.channel.send(
                                        f"Next ban: {session.current_turn.mention} – "
                                        f"type `<map> <side>` (e.g. `remagen axis`)."
                                    )
                                    ctx = await bot.get_context(message)
                                    await send_session_status(ctx, session, title="Map Ban Updated")

    # Let normal commands run
    await bot.process_commands(message)


# --------------- BOT STARTUP ---------------

if __name__ == "__main__":
    # Put your bot token here or use environment variable DISCORD_BOT_TOKEN
    TOKEN = os.getenv("DISCORD_BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"

    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Error: set your Discord bot token in DISCORD_BOT_TOKEN env var or in the script.")
    else:
        bot.run(TOKEN)
