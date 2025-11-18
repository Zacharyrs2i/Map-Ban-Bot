import os
import random
import discord
from discord.ext import commands
from dotenv import find_dotenv, load_dotenv

# Load environment variables from .env (DISCORD_BOT_TOKEN)
import os
from dotenv import load_dotenv, find_dotenv

# --- ENV / TOKEN DEBUG SECTION ---

# Was the token already in the environment before we touched .env?
_token_present_before_dotenv = "DISCORD_BOT_TOKEN" in os.environ

# Which .env file will python-dotenv find (if any)?
_dotenv_path = find_dotenv(usecwd=True)
_dotenv_present_in_cwd = bool(_dotenv_path)

print("=== ENV DEBUG START ===")
print(f".env detected: {_dotenv_path if _dotenv_present_in_cwd else 'None found'}")
print(f"Token present before load_dotenv: {_token_present_before_dotenv}")

# Load .env (if path exists), otherwise let load_dotenv search default
_dotenv_loaded = load_dotenv(_dotenv_path or None)
print(f".env loaded: {_dotenv_loaded}")

_token_after = os.getenv("DISCORD_BOT_TOKEN")

if _token_after:
    masked = f"{_token_after[:4]}...{_token_after[-4:]}" if len(_token_after) > 8 else "too short to mask"
    print(f"DISCORD_BOT_TOKEN is SET (len={len(_token_after)}), value: {masked}")

    if _token_present_before_dotenv:
        print("Source guess: existing process environment (NOT from .env).")
    elif _dotenv_loaded and _dotenv_present_in_cwd:
        print(f"Source guess: .env file at: {_dotenv_path}")
    else:
        print("Source guess: unknown (could be system/user env, service config, etc.).")
else:
    print("DISCORD_BOT_TOKEN is NOT set after load_dotenv.")
    if not _dotenv_loaded:
        print("Warning: .env file not found or not loaded.")
print("=== ENV DEBUG END ===")


def reset_and_reload_token(dotenv_path=None):
    """
    Clear DISCORD_BOT_TOKEN from the current process env,
    then reload from the specified .env file (or auto-detected one).
    Call this BEFORE you call os.getenv('DISCORD_BOT_TOKEN') for real.
    """
    if "DISCORD_BOT_TOKEN" in os.environ:
        del os.environ["DISCORD_BOT_TOKEN"]
        print("Cleared DISCORD_BOT_TOKEN from process environment.")
    else:
        print("No DISCORD_BOT_TOKEN in process environment to clear.")

    # Reload from .env
    env_path = dotenv_path or find_dotenv(usecwd=True)
    if env_path:
        print(f"Reloading DISCORD_BOT_TOKEN from .env: {env_path}")
        load_dotenv(env_path, override=True)
    else:
        print("No .env file found to reload from.")
# --- END ENV / TOKEN DEBUG SECTION ---

# --------------- CONFIG ---------------

BOT_PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True  # we don't need members or presence intents

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

# Short aliases / nicknames for easier map matching (family-level)
ALIAS_MAP = {
    # Purple Heart Lane
    "phl": "PHL",
    "purple": "PHL",
    "purple heart": "PHL",
    "purple heart lane": "PHL",

    # Sainte-Mère-Église
    "sme": "Sainte-Mère-Église",
    "st mere": "Sainte-Mère-Église",
    "st mere eglise": "Sainte-Mère-Église",

    # Sainte-Marie-du-Mont
    "smdm": "Sainte-Marie-du-Mont",
    "stm": "Sainte-Marie-du-Mont",
    "st marie": "Sainte-Marie-du-Mont",
    "st marie du mont": "Sainte-Marie-du-Mont",

    # Carentan
    "car": "Carentan",

    # Hill 400
    "h400": "Hill 400",
    "hill400": "Hill 400",

    # Hurtgen Forest
    "hurtgen": "Hurtgen Forest",

    # El-Alamein
    "elal": "El-Alamein",
    "el al": "El-Alamein",

    # Driel
    "dri": "Driel",

    # Foy
    "foy": "Foy",

    # Mortain
    "mort": "Mortain",
}

# Variant keywords (shorthand for map variants)
VARIANT_KEYWORDS = {
    "night": "Night",
    "n": "Night",
    "dusk": "Dusk",
    "d": "Dusk",
    "dawn": "Dawn",
    "da": "Dawn",
    "overcast": "Overcast",
    "o": "Overcast",
}

# One map-ban session per channel
map_ban_sessions = {}  # {channel_id: MapBanSession}


# --------------- BOT EVENTS ---------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Connected to the following servers (guilds):")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id})")
    print(f"Total guilds: {len(bot.guilds)}")


# --------------- CORE SESSION CLASS ---------------

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

    # ---------- Map / side legality ----------

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

    # ---------- Variant helpers ----------

    @staticmethod
    def _is_base_map_name(name: str) -> bool:
        """Base map has no variant keyword in its name."""
        variants = ["Night", "Dusk", "Dawn", "Overcast"]
        return not any(v in name for v in variants)

    @staticmethod
    def _map_has_variant(name: str, variant):
        """Return True if map name matches the requested variant."""
        if variant is None:
            return True
        return variant in name

    # ---------- Ban searching / matching ----------

    def find_map_partial(self, text: str, variant=None, only_bannable: bool = True):
        """
        Case-insensitive map match with:
          - numeric index support (e.g. '1' = first bannable map)
          - alias support (PHL, SME, SMDM, etc.)
          - variant filtering (Night / Dusk / Dawn / Overcast)
          - partial text search as fallback.

        Returns:
          - None if no matches
          - map_name if exactly one match
          - "AMBIGUOUS" if multiple matches
        """
        text = text.strip().lower()
        if not text:
            return None

        # Candidates based on bannable state
        if only_bannable:
            candidates = [m for m in self.maps if self.map_available_for_ban(m)]
        else:
            candidates = self.maps[:]

        if not candidates:
            return None

        # 1) Numeric index support: '1', '2', etc. (1-based)
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
            return None

        # 2) Alias support
        if text in ALIAS_MAP:
            alias_target = ALIAS_MAP[text].lower()
            alias_matches = [
                m for m in candidates
                if alias_target in m.lower() and self._map_has_variant(m, variant)
            ]
            if len(alias_matches) == 1:
                return alias_matches[0]
            if len(alias_matches) > 1:
                # Try to prefer base maps if variant not specified
                if variant is None:
                    base_matches = [m for m in alias_matches if self._is_base_map_name(m)]
                    if len(base_matches) == 1:
                        return base_matches[0]
                return "AMBIGUOUS"

        # 3) Partial text search (with variant filtering)
        matches = [
            m for m in candidates
            if text in m.lower() and self._map_has_variant(m, variant)
        ]

        if len(matches) == 0:
            # If variant was specified and got no matches, try without variant as fallback
            if variant is not None:
                matches = [m for m in candidates if text in m.lower()]
                if not matches:
                    return None
            else:
                return None

        if len(matches) == 1:
            return matches[0]

        # If multiple matches and no variant specified, prefer base maps
        if variant is None:
            base_matches = [m for m in matches if self._is_base_map_name(m)]
            if len(base_matches) == 1:
                return base_matches[0]
            if len(base_matches) > 1:
                return "AMBIGUOUS"

        # Still ambiguous
        return "AMBIGUOUS"

    # ---------- Ban handling with side-lock rule ----------

    def register_ban(self, member: discord.Member, map_name: str, side: str):
        """
        Apply a ban: member refuses to play 'side' on 'map_name'.

        Updated rule we enforce:
        - If a team bans <side> on <map>, they refuse to play that side.
        - The opponent keeps their existing options; a map only becomes fully banned
          once **both** teams have banned the same side and no legal assignment
          remains.

        Returns (success: bool, msg: str)
        """
        if not self.allowed_sides:
            return False, "Internal error: allowed sides not initialized."

        if not (self.team1 and self.team2):
            return False, "Teams are not set for this session."

        team_id = member.id
        if team_id not in self.allowed_sides:
            return False, "You are not one of the captains for this session."

        # Current team and opponent
        if member == self.team1:
            other_team = self.team2
        elif member == self.team2:
            other_team = self.team1
        else:
            return False, "You are not one of the captains for this session."

        other_team_id = other_team.id

        # 1) Remove the banned side from this team's allowed set
        sides_set = self.allowed_sides[team_id].get(map_name, set())
        if side not in sides_set:
            if not sides_set:
                return False, f"You have no sides left to ban on **{map_name}**."
            else:
                return False, f"You have already banned **{side}** on **{map_name}**."

        sides_set.remove(side)
        self.allowed_sides[team_id][map_name] = sides_set

        # Record ban in history
        self.ban_history.append({"map": map_name, "side": side, "by": member})

        # 2) Recompute which maps are fully dead based on new side locks
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
            return final_map, None, None

        t1_side, t2_side = random.choice(options)
        return final_map, t1_side, t2_side


# --------------- HELPER FUNCTIONS ---------------

def format_list_as_bullets(items):
    if not items:
        return "*(none)*"
    return "\n".join(f"- {i}" for i in items)


def format_side_detail(allowed_set=None):
    """
    Show per-team side status with both sides visible.
    Example outputs:
    - "A: ✅  X: ✅"
    - "A: ❌  X: ✅"
    - "A: ❌  X: ❌"
    """
    if allowed_set is None:
        allowed_set = set()
    base_sides = ["Allies", "Axis"]
    parts = []
    for side_name, short in (("Allies", "A"), ("Axis", "X")):
        emoji = "✅" if side_name in allowed_set else "❌"
        parts.append(f"{short}: {emoji}")
    return "  ".join(parts)


def format_lock_text(allowed_set=None):
    """
    Return a human-readable lock description:
    - 'Allies/Axis'  -> fully open
    - 'Allies only'  -> locked to Allies
    - 'Axis only'    -> locked to Axis
    - 'No sides'     -> cannot play this map
    """
    if allowed_set is None:
        allowed_set = set()

    if not allowed_set:
        return "No sides"
    if allowed_set == {"Allies", "Axis"}:
        return "Allies/Axis"
    if allowed_set == {"Allies"}:
        return "Allies only"
    if allowed_set == {"Axis"}:
        return "Axis only"
    return "/".join(sorted(allowed_set))


async def send_session_status(target, session: MapBanSession, title="Map Ban Status"):
    embed = discord.Embed(title=title)

    team1_name = session.team1.display_name if session.team1 else "Not set"
    team2_name = session.team2.display_name if session.team2 else "Not set"

    embed.add_field(name="Team 1 Captain", value=team1_name, inline=True)
    embed.add_field(name="Team 2 Captain", value=team2_name, inline=True)
    embed.add_field(name="Status", value=session.status.capitalize(), inline=True)

    # Maps still available for ban
    if session.status == "banning" and session.allowed_sides:
        bannable = session.maps_still_available_for_ban()

        if bannable:
            numbered = []
            for i, name in enumerate(bannable):
                if session.team1 and session.team2:
                    t1_allowed = session.allowed_sides.get(session.team1.id, {}).get(name, set())
                    t2_allowed = session.allowed_sides.get(session.team2.id, {}).get(name, set())
                    t1_detail = format_side_detail(t1_allowed)
                    t2_detail = format_side_detail(t2_allowed)
                    numbered.append(
                        f"{i+1}) {name}\n"
                        f"  {session.team1.display_name}: {t1_detail}\n"
                        f"  {session.team2.display_name}: {t2_detail}"
                    )
                else:
                    numbered.append(f"{i+1}) {name}")
            value = "\n".join(numbered)
        else:
            value = "*(none)*"

        embed.add_field(
            name=f"Maps Still Available for Ban ({len(bannable)})",
            value=value,
            inline=False,
        )
    else:
        embed.add_field(
            name=f"Map Pool ({len(session.maps)})",
            value=format_list_as_bullets(session.maps),
            inline=False,
        )

    # Per-map side status (once banning has started)
    if session.status in ("banning", "finished") and session.allowed_sides and session.team1 and session.team2:
        lines = []
        t1_id = session.team1.id
        t2_id = session.team2.id
        for m in session.maps:
            if m in session.fully_banned_maps:
                continue
            if not session.is_map_playable(m):
                continue

            t1_allowed = session.allowed_sides.get(t1_id, {}).get(m, set())
            t2_allowed = session.allowed_sides.get(t2_id, {}).get(m, set())

            t1_detail = format_side_detail(t1_allowed)
            t2_detail = format_side_detail(t2_allowed)

            lines.append(
                f"{m}\n"
                f"  {session.team1.display_name}: {t1_detail}\n"
                f"  {session.team2.display_name}: {t2_detail}"
            )

        embed.add_field(
            name="Playable Map Side Status (A = Allies, X = Axis)",
            value="\n".join(lines) if lines else "*(none)*",
            inline=False,
        )

        # Side lock summary section (maps where either team is restricted)
        lock_lines = []
        for m in session.maps:
            if m in session.fully_banned_maps:
                continue
            if not session.is_map_playable(m):
                continue

            t1_allowed = session.allowed_sides.get(t1_id, {}).get(m, set())
            t2_allowed = session.allowed_sides.get(t2_id, {}).get(m, set())

            t1_lock = format_lock_text(t1_allowed)
            t2_lock = format_lock_text(t2_allowed)

            # Only show maps where at least one team isn't fully open
            if t1_lock != "Allies/Axis" or t2_lock != "Allies/Axis":
                lock_lines.append(
                    f"{m}\n"
                    f"  {session.team1.display_name}: {t1_lock}\n"
                    f"  {session.team2.display_name}: {t2_lock}"
                )

        if lock_lines:
            embed.add_field(
                name="Side Locks (maps with side restrictions)",
                value="\n".join(lock_lines),
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
            value=(
                f"{session.current_turn.mention} – type `<map> <side>` "
                f"(you can use number, alias, and variant, e.g. `1 allies`, `phl n axis`)."
            ),
            inline=False,
        )

    await target.send(embed=embed)


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


def strip_side_from_text(text: str, side):
    """
    Remove side word(s) from text so we can match map/variant.
    """
    if side is None:
        return text.strip()

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


def parse_variant(text: str):
    """
    Try to extract a variant (Night/Dusk/Dawn/Overcast) from text.
    Returns variant string or None.
    """
    tokens = text.lower().split()
    for tok in tokens:
        if tok in VARIANT_KEYWORDS:
            return VARIANT_KEYWORDS[tok]
    return None


def strip_variant_from_text(text: str, variant):
    """
    Remove variant tokens from text (e.g. 'night', 'n', 'dusk', etc.).
    """
    if variant is None:
        return text.strip()

    tokens = text.split()
    # Collect all tokens that map to this variant
    variant_tokens = {tok for tok, var in VARIANT_KEYWORDS.items() if var == variant}

    cleaned = []
    for tok in tokens:
        low = tok.lower()
        if low in variant_tokens:
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
    await ctx.send(
        "Now set captains with: `!mb_teams @Captain1 @Captain2`"
    )


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
        f"Type `<map> <side>` – you can use number, alias, and variant, e.g.:\n"
        f"`1 allies`, `phl axis`, `phl n axis`, `foy night a`."
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
    await send_session_status(ctx, session, title="Map Ban Updated (Undo)")


@bot.command(name="mb_guilds")
@commands.is_owner()
async def mb_guilds(ctx):
    """List the servers this bot is in (owner-only)."""
    lines = [f"- {g.name} (ID: {g.id})" for g in bot.guilds]
    text = "\n".join(lines) if lines else "I'm not in any servers somehow."
    await ctx.send(
        f"I'm currently in **{len(bot.guilds)}** servers:\n{text}"
    )


@bot.command(name="mb_help")
async def mb_help(ctx):
    """
    Show help for the HLL map-ban bot.
    Usage: !mb_help
    """
    embed = discord.Embed(
        title="HLL Map-Ban Help",
        description=(
            "This bot runs a per-side (Allies/Axis) map-ban for Hell Let Loose.\n"
            "Bans are done by captains typing messages like `phl allies` or `1 axis`."
        )
    )

    # Basic flow
    embed.add_field(
        name="Setup Flow",
        value=(
            "1. `!mb_new` – start a new map-ban session in this channel.\n"
            "2. `!mb_teams @Captain1 @Captain2` – set the two captains.\n"
            "3. `!mb_start` – coin flip for first ban and begin banning.\n"
            "4. Captains ban by typing `<map> <side>` on their turn.\n"
            "5. Bot auto-ends when only one playable map remains and assigns sides."
        ),
        inline=False,
    )

    # Ban syntax
    embed.add_field(
        name="How to Ban",
        value=(
            "**Always include a side**: `allies` / `axis` / `a` / `x`.\n"
            "Examples:\n"
            "• `1 allies` – ban Allies on map #1 in the bannable list.\n"
            "• `phl axis` – ban Axis on PHL.\n"
            "• `phl n axis` – ban Axis on **PHL Night**.\n"
            "• `foy night a` – ban Allies on **Foy Night**.\n\n"
            "You can use:\n"
            "• **Numbers**: `1 allies`, `3 axis` (see numbered list in the embed).\n"
            "• **Aliases**: `phl`, `sme`, `smdm`, `dri`, `foy`, etc.\n"
            "• **Variants**: `night/n`, `dusk/d`, `dawn/da`, `overcast/o`."
        ),
        inline=False,
    )

    # What the embed shows
    embed.add_field(
        name="Reading the Status Embed",
        value=(
            "After each ban the bot shows:\n"
            "• **Maps Still Available for Ban** – numbered list (you can use these numbers).\n"
            "• **Playable Map Side Status** – A/X grid with ✅/❌ per team.\n"
            "• **Side Locks** – maps where either team is locked to a specific side.\n"
            "• **Fully Banned Maps** – maps with no legal side assignments left.\n"
            "• **Current Turn** – who should ban next and what format to use."
        ),
        inline=False,
    )

    # Other commands
    embed.add_field(
        name="Other Commands",
        value=(
            "`!mb_status` – show current status.\n"
            "`!mb_pool` – show full map pool.\n"
            "`!mb_undo` – undo last ban (session creator or admin).\n"
            "`!mb_cancel` – cancel the session (session creator or admin).\n"
            "`!mb_guilds` – list servers (bot owner only)."
        ),
        inline=False,
    )

    await ctx.send(embed=embed)


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
                        f"`allies` or `axis`. Example: `1 allies`, `phl n axis`."
                    )
                else:
                    # Strip side and parse variant
                    text_no_side = strip_side_from_text(content, side)
                    variant = parse_variant(text_no_side)
                    text_no_side_variant = strip_variant_from_text(text_no_side, variant)

                    if not text_no_side_variant:
                        await message.channel.send(
                            f"{message.author.mention} I couldn't see a map name. "
                            f"Use `<map> <side>`, e.g. `1 allies`, `phl axis`, `phl night axis`."
                        )
                    else:
                        chosen_map = session.find_map_partial(
                            text_no_side_variant,
                            variant=variant,
                            only_bannable=True,
                        )
                        if chosen_map is None:
                            await message.channel.send(
                                f"{message.author.mention} I couldn't match that to any map still available for ban. "
                                f"Check `!mb_status` for the current list."
                            )
                        elif chosen_map == "AMBIGUOUS":
                            await message.channel.send(
                                f"{message.author.mention} that text matches **multiple** maps. "
                                f"Please be more specific or use the number shown in the list "
                                f"(e.g. `1 allies`)."
                            )
                        else:
                            # Apply ban
                            success, msg = session.register_ban(message.author, chosen_map, side)
                            if not success:
                                await message.channel.send(f"{message.author.mention} {msg}")
                            else:
                                # Normal ban message
                                await message.channel.send(f"🚫 {msg}")

                                # Lock info message
                                team1 = session.team1
                                team2 = session.team2
                                t1_allowed = session.allowed_sides.get(team1.id, {}).get(chosen_map, set())
                                t2_allowed = session.allowed_sides.get(team2.id, {}).get(chosen_map, set())

                                def lock_text(team, allowed):
                                    if not allowed:
                                        return f"{team.display_name} can no longer play **ANY** side on this map."
                                    if allowed == {"Allies"}:
                                        return f"{team.display_name} is now **locked to Allies** on **{chosen_map}**."
                                    if allowed == {"Axis"}:
                                        return f"{team.display_name} is now **locked to Axis** on **{chosen_map}**."
                                    return f"{team.display_name} can still play Allies or Axis on **{chosen_map}**."

                                t1_msg = lock_text(team1, t1_allowed)
                                t2_msg = lock_text(team2, t2_allowed)

                                await message.channel.send(
                                    f"🔒 **Side Locks Updated for {chosen_map}:**\n"
                                    f"- {t1_msg}\n"
                                    f"- {t2_msg}"
                                )

                                # If the map became fully banned, announce it
                                if chosen_map in session.fully_banned_maps:
                                    await message.channel.send(
                                        f"❌ **{chosen_map} is now FULLY BANNED** "
                                        f"(no legal side assignment remains)."
                                    )

                                # Check finish condition
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
                                            f"{team1.display_name}: **{t1_side}**\n"
                                            f"{team2.display_name}: **{t2_side}**"
                                        )
                                    await send_session_status(message.channel, session, title="Final Map-Ban Result")
                                    await bot.process_commands(message)
                                    return

                                # Switch turn
                                session.current_turn = session.other_captain(message.author)
                                await message.channel.send(
                                    f"Next ban: {session.current_turn.mention} – "
                                    f"type `<map> <side>` (e.g. `2 axis`, `phl a`, `phl n axis`)."
                                )

                                await send_session_status(message.channel, session, title="Map Ban Updated")

    # Let normal commands run
    await bot.process_commands(message)


# --------------- BOT STARTUP ---------------


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")

    token_length = len(token) if token else 0
    token_present_after_dotenv = "DISCORD_BOT_TOKEN" in os.environ
    token_added_by_dotenv = token_present_after_dotenv and not _token_present_before_dotenv
    token_source = "dotenv" if token_added_by_dotenv else "pre-existing environment" if token_present_after_dotenv else "missing"

    diagnostics = [
        "Environment diagnostics:",
        f"  .env path: {_dotenv_path if _dotenv_path else 'none'}",
        f"  .env present in cwd: {_dotenv_present_in_cwd}",
        f"  .env loaded: {_dotenv_loaded}",
        f"  token present before load: {_token_present_before_dotenv}",
        f"  token present after load: {token_present_after_dotenv}",
        f"  token added by dotenv: {token_added_by_dotenv}",
        f"  token source: {token_source}",
        f"  token length: {token_length}",
    ]

    print("\n".join(diagnostics))

    if token is None:
        print(
            "Error: DISCORD_BOT_TOKEN is missing. "
            "Set it in your environment or in a .env file as DISCORD_BOT_TOKEN=YOUR_TOKEN."
        )
        raise SystemExit(1)

    token = token.strip()
    if not token or token.upper() == "YOUR_BOT_TOKEN_HERE":
        print(
            "Error: DISCORD_BOT_TOKEN is empty or still the placeholder. "
            "Copy the exact Bot Token from the Discord developer portal."
        )
        raise SystemExit(1)

    bot.run(token)


if __name__ == "__main__":
    main()