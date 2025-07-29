import discord
import json
import re
import os
import itertools
import random
import math
from dotenv import load_dotenv
from collections import defaultdict
from wcwidth import wcswidth
from discord.ext import commands

# ******** ENV VALUES *****************
load_dotenv()  # Loads the variables from .env into environment

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable.")

RESULTS_CHANNEL_ID = 1397883760497917992  # Replace with your results channel ID
REGISTRATION_CHANNEL_ID = 1397883682072563843  # Optional: channel for registration
UPDATE_CHANNEL_ID = 1398407241031352401  # Dedicated channel for persistent update messages
# *************************************

REGISTRATION_FILE = "data/teams.json"
RESULTS_FILE = "data/results.json"
TOURNAMENT_STATE_FILE = "data/tournament_state.json"
UPDATE_MSGS_FILE = "data/update_msgs.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

score_line_re = re.compile(r"Red:\s*(\d+)\s*\|\s*Blue\s*(\d+)", re.IGNORECASE)
clan_line_re = re.compile(r"Clan:\s*(.+)")

def update_knockout_bracket_with_results(bracket, results):
    def norm(t):
        return t.strip().lower().replace("_", "\\") if t else None

    # Map normalized team sets to winners (normalized)
    match_winners = {}
    for res in results:
        r_clan = norm(res['red_clan'])
        b_clan = norm(res['blue_clan'])
        winner = norm(res['winner'])
        teams_set = frozenset({r_clan, b_clan})
        match_winners[teams_set] = winner

    print("=== Updating Knockout Bracket with Results ===")
    for round_idx in range(len(bracket) - 1):
        current_round = bracket[round_idx]
        next_round = bracket[round_idx + 1]

        winners_in_round = []

        print(f"Round {round_idx+1} current matches:")
        for m, (t1, t2) in enumerate(current_round, 1):
            print(f"  Match {m}: {t1} vs {t2}")

        for (t1, t2) in current_round:
            t1_norm = norm(t1)
            t2_norm = norm(t2)

            if t2 is None:
                print(f"  Bye detected, {t1} advances automatically")
                winners_in_round.append(t1)
                continue
            if t1 is None:
                print(f"  Bye detected, {t2} advances automatically")
                winners_in_round.append(t2)
                continue

            teams_set = frozenset({t1_norm, t2_norm})
            winner_norm = match_winners.get(teams_set)

            if winner_norm is None:
                print(f"  No result for match: {t1} vs {t2}")
                winners_in_round.append(None)
            else:
                if winner_norm == t1_norm:
                    print(f"  Winner of match {t1} vs {t2} is {t1}")
                    winners_in_round.append(t1)
                elif winner_norm == t2_norm:
                    print(f"  Winner of match {t1} vs {t2} is {t2}")
                    winners_in_round.append(t2)
                else:
                    print(f"  Unexpected winner name '{winner_norm}' for match {t1} vs {t2}")
                    winners_in_round.append(None)

        print(f"Winners after round {round_idx+1}: {winners_in_round}")
        print(f"Next round ({round_idx+2}) matches before update: {next_round}")

        # Make sure winners_in_round has enough elements (pad with None if needed)
        expected_winners = len(next_round) * 2
        if len(winners_in_round) < expected_winners:
            winners_in_round.extend([None] * (expected_winners - len(winners_in_round)))

        for i in range(len(next_round)):
            pos = i * 2
            t1 = winners_in_round[pos] if pos < len(winners_in_round) else None
            t2 = winners_in_round[pos + 1] if pos + 1 < len(winners_in_round) else None
            next_round[i] = (t1, t2)

        print(f"Next round ({round_idx+2}) matches after update: {next_round}")
    print("=== Knockout Bracket update complete ===\n")

def normalize_name(name):
    return name.strip().lower().replace("_", "\\")

# -- Load/save helpers --

def load_teams():
    try:
        raw = json.load(open(REGISTRATION_FILE))
        normalized = {}
        for k, v in raw.items():
            n = normalize_name(k)
            normalized[n] = {"display_name": k, **v}
        return normalized
    except FileNotFoundError:
        return {}

def save_teams(data):
    to_save = {info["display_name"]: {"captain": info["captain"], "members": info["members"]} for info in data.values()}
    with open(REGISTRATION_FILE, "w") as f:
        json.dump(to_save, f, indent=2)

def load_results():
    try:
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_results(data):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_tournament_state():
    try:
        with open(TOURNAMENT_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"phase": "registration", "groups": {}, "knockout_results": [], "qualifiers": []}

def save_tournament_state(state):
    with open(TOURNAMENT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_update_messages():
    if os.path.exists(UPDATE_MSGS_FILE):
        with open(UPDATE_MSGS_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def save_update_messages(data):
    with open(UPDATE_MSGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

teams = load_teams()
results = load_results()
tournament_state = load_tournament_state()

# -- Discord message helpers --

async def fetch_or_create_msg(channel, msg_key):
    data = load_update_messages()
    msg_id = data.get(msg_key)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            return msg
        except discord.NotFound:
            pass

    if msg_key == "teams_msg_id":
        content = "**Registered Teams:**\n_No teams registered yet._"
    elif msg_key == "results_msg_id":
        content = "**Tournament Results / Standings:**\n_No results yet._"
    else:
        content = "_Empty message_"

    msg = await channel.send(content)
    data[msg_key] = msg.id
    save_update_messages(data)
    return msg

async def update_teams_message():
    channel = bot.get_channel(UPDATE_CHANNEL_ID)
    if channel is None:
        print("Update channel not found!")
        return
    msg = await fetch_or_create_msg(channel, "teams_msg_id")

    if not teams:
        content = "**Registered Teams:**\n_No teams registered yet._"
    else:
        lines = ["**Registered Teams:**"]
        for norm_name, info in teams.items():
            members = ", ".join(m["name"] for m in info["members"])
            lines.append(f"- **{info['display_name']}**: {members}")
        content = "\n".join(lines)
    try:
        await msg.edit(content=content)
    except discord.HTTPException:
        pass

# -- Tournament helpers --

async def update_group_standings_and_schedule():
    group = tournament_state["groups"].get("GroupA")
    if not group:
        return "", ""

    standings = calculate_group_standings(group["matches"], group["teams"])
    standings_text = build_standings_text(standings)
    schedule_text = build_group_schedule_text(group["matches"])
    return standings_text, schedule_text

async def update_results_message(standings_text="", schedule_text="", bracket_text=""):
    channel = bot.get_channel(UPDATE_CHANNEL_ID)
    if channel is None:
        print("Update channel not found!")
        return
    msg = await fetch_or_create_msg(channel, "results_msg_id")

    content = f"**Tournament Results / Standings:**\n"
    if standings_text:
        content += f"```{standings_text}```\n"
    if schedule_text:
        content += f"{schedule_text}\n"
    if bracket_text:
        content += f"{bracket_text}\n"

    try:
        await msg.edit(content=content)
    except discord.HTTPException:
        pass

def calculate_group_standings(matches, teams_list):
    standings = {t: {"played":0,"wins":0,"draws":0,"losses":0,"points":0,"score_diff":0} for t in teams_list}
    for m in matches:
        if m["result"] is None:
            continue
        r = m["team1"]
        b = m["team2"]
        res = m["result"]
        r_score = res["red_score"]
        b_score = res["blue_score"]

        standings[r]["played"] += 1
        standings[b]["played"] += 1
        standings[r]["score_diff"] += r_score - b_score
        standings[b]["score_diff"] += b_score - r_score

        if r_score > b_score:
            standings[r]["wins"] += 1
            standings[r]["points"] += 3
            standings[b]["losses"] += 1
        elif b_score > r_score:
            standings[b]["wins"] += 1
            standings[b]["points"] += 3
            standings[r]["losses"] += 1
        else:
            standings[r]["draws"] += 1
            standings[b]["draws"] += 1
            standings[r]["points"] += 1
            standings[b]["points"] += 1

    return standings

def build_standings_text(standings):
    max_team_width = max(wcswidth(teams[t]["display_name"]) for t in standings)
    col_width = max(12, max_team_width)

    sorted_teams = sorted(standings.items(), key=lambda t: (t[1]["points"], t[1]["score_diff"]), reverse=True)
    lines = []
    lines.append(f"Pos | Team{' '*(col_width - 4)} | Pld | W | D | L | Pts | +/-")
    lines.append(f"--- | {'-'*col_width} | --- | - | - | - | --- | ---")
    for idx, (norm_team, s) in enumerate(sorted_teams, 1):
        display_name = teams[norm_team]["display_name"]
        padded_team = pad_to_width(display_name, col_width)
        lines.append(
            f"{idx:3} | {padded_team} | {s['played']:3} | {s['wins']:1} | {s['draws']:1} | {s['losses']:1} | {s['points']:3} | {s['score_diff']:3}"
        )
    return "\n".join(lines)

def pad_to_width(text, width):
    visual_len = wcswidth(text)
    if visual_len >= width:
        return text
    return text + " " * (width - visual_len)

def build_group_schedule_text(matches):
    lines = ["**Upcoming Group Matches (strikethrough = played):**"]
    for idx, match in enumerate(matches, start=1):
        t1 = teams[match["team1"]]["display_name"]
        t2 = teams[match["team2"]]["display_name"]
        if match["result"] is not None:
            r_s = match["result"]["red_score"]
            b_s = match["result"]["blue_score"]
            winner = match["result"]["winner"]
            lines.append(f"~~{idx}. {t1} vs {t2} [{r_s} - {b_s}] Winner: {winner}~~")
        else:
            lines.append(f"{idx}. {t1} vs {t2}")
    return "\n".join(lines)

# -- Scheduling --

def generate_partial_schedule(team_list, rounds):
    all_pairs = list(itertools.combinations(team_list, 2))
    random.shuffle(all_pairs)

    matches_assigned = []
    counts = defaultdict(int)

    for t1, t2 in all_pairs:
        if counts[t1] < rounds and counts[t2] < rounds:
            matches_assigned.append({"team1": t1, "team2": t2, "result": None})
            counts[t1] += 1
            counts[t2] += 1

    incomplete = [t for t in team_list if counts[t] < rounds]
    if incomplete:
        print(f"Warning: Could not assign {rounds} matches for all teams; teams with less matches: {incomplete}")

    return matches_assigned

def find_line_containing(lines, keyword):
    for i, line in enumerate(lines):
        plain = line.strip().strip("*").lower()
        if keyword.lower() in plain:
            return i
    return -1

# -- Knockout bracket generation --

def generate_knockout_bracket(qualifiers):
    """
    Generates a single elimination knockout bracket with byes if needed.
    Returns list of rounds, each round is a list of (team1, team2) tuples where team2 can be None for bye.
    """
    n = len(qualifiers)
    next_pow2 = 1
    while next_pow2 < n:
        next_pow2 <<= 1
    byes = next_pow2 - n

    seeds = qualifiers[:] + [None] * byes

    pairs = []
    for i in range(next_pow2 // 2):
        t1 = seeds[i]
        t2 = seeds[next_pow2 - 1 - i]
        pairs.append((t1, t2))

    rounds = [pairs]

    current_round_size = next_pow2 // 2
    while current_round_size > 1:
        current_round_size //= 2
        rounds.append([(None, None)] * current_round_size)

    return rounds

def bracket_to_string(rounds, results):
    lines = ["**Knockout Bracket:**"]
    match_index = 0

    def norm(t):
        return t if t is None else normalize_name(t)

    for rnd_i, rnd in enumerate(rounds, start=1):
        lines.append(f"\nRound {rnd_i}:")
        for t1_norm, t2_norm in rnd:
            m = None
            for res in results:
                r = normalize_name(res["red_clan"])
                b = normalize_name(res["blue_clan"])
                if {norm(t1_norm), norm(t2_norm)} == {r, b}:
                    m = res
                    break

            t1_display = teams[t1_norm]["display_name"] if t1_norm in teams else "BYE"
            t2_display = teams[t2_norm]["display_name"] if t2_norm in teams else "BYE"

            if m:
                lines.append(
                    f"  Match {match_index+1}: {t1_display} [{m['red_score']}] vs {t2_display} [{m['blue_score']}] -> Winner: {m['winner']}"
                )
            else:
                if t2_norm is None:
                    lines.append(f"  Match {match_index+1}: {t1_display} receives a bye.")
                else:
                    lines.append(f"  Match {match_index+1}: {t1_display} vs {t2_display} [Not played yet]")
            match_index += 1
    return "\n".join(lines)

# -- Commands --

@bot.command()
@commands.has_permissions(administrator=True)
async def reloadteams(ctx):
    global teams
    teams = load_teams()
    await ctx.send("Teams reloaded from file.")
    await update_teams_message()

@bot.command(name="register")
async def register(ctx, team_name: str, *members: discord.Member):
    global teams
    if ctx.channel.id == RESULTS_CHANNEL_ID:
        await ctx.send("Please use the dedicated registration channel to register teams.")
        return

    teams = load_teams()

    norm_name = normalize_name(team_name)
    if norm_name in teams:
        await ctx.send(f"Team **{team_name}** is already registered.")
        return

    if not members:
        await ctx.send("Please mention at least one team member (including captain).")
        return

    captain = members[0]
    member_list = members

    teams[norm_name] = {
        "display_name": team_name,
        "captain": {"id": captain.id, "name": captain.display_name},
        "members": [{"id": m.id, "name": m.display_name} for m in member_list]
    }

    save_teams(teams)
    await ctx.send(f"Team **{team_name}** registered!\nCaptain: {captain.mention}\nMembers: {', '.join(m.mention for m in member_list)}")

    await update_teams_message()

@bot.command()
@commands.has_permissions(administrator=True)
async def startgroups(ctx, rounds: int = 1):
    global tournament_state
    if tournament_state.get("phase") != "registration":
        await ctx.send("Groups already started or tournament not in registration phase.")
        return

    if len(teams) < 2:
        await ctx.send("Not enough teams registered to start the group stage.")
        return

    if rounds < 1:
        await ctx.send("Number of rounds must be at least 1.")
        return

    team_list = list(teams.keys())

    matches = generate_partial_schedule(team_list, rounds)

    tournament_state = {
        "phase": "group",
        "groups": {
            "GroupA": {
                "teams": team_list,
                "matches": matches
            }
        },
        "knockout_results": [],
        "qualifiers": []
    }
    save_tournament_state(tournament_state)

    await ctx.send(f"Group stage started with {len(team_list)} teams in GroupA, {rounds} rounds per team. Matches scheduled.")
    standings_text, schedule_text = await update_group_standings_and_schedule()
    await update_results_message(standings_text=standings_text, schedule_text=schedule_text)

@bot.command()
async def standings(ctx):
    if tournament_state.get("phase") != "group":
        await ctx.send("Group standings are only available during the group phase.")
        return

    group = tournament_state["groups"].get("GroupA")
    if not group:
        await ctx.send("No group data found.")
        return

    standings = calculate_group_standings(group["matches"], group["teams"])
    text = build_standings_text(standings)
    await ctx.send(f"```{text}```")

@bot.command()
@commands.has_permissions(administrator=True)
async def startknockout(ctx, qualify_count: str = "2/3"):
    global tournament_state
    if tournament_state.get("phase") != "group":
        await ctx.send("Knockout phase can only be started after the group phase.")
        return

    group = tournament_state["groups"].get("GroupA")
    if not group:
        await ctx.send("No group data found.")
        return

    standings = calculate_group_standings(group["matches"], group["teams"])
    sorted_teams = sorted(standings.items(),
                          key=lambda t: (t[1]["points"], t[1]["score_diff"]), reverse=True)

    total_teams = len(sorted_teams)

    try:
        if '/' in qualify_count:
            numerator, denominator = qualify_count.split('/')
            q = float(numerator) / float(denominator)
            num_qualify = math.floor(q * total_teams)
        elif '.' in qualify_count:
            q = float(qualify_count)
            num_qualify = math.floor(q * total_teams)
        else:
            num_qualify = int(qualify_count)
    except Exception:
        await ctx.send("Invalid qualifier count. Enter integer, fraction like '2/3', or decimal like '0.5'.")
        return
    
    if num_qualify < 1:
        await ctx.send("Must qualify at least one team.")
        return

    if num_qualify > total_teams:
        num_qualify = total_teams

    qualifiers = [team for team, _ in sorted_teams[:num_qualify]]

    tournament_state["phase"] = "knockout"
    tournament_state["qualifiers"] = qualifiers
    tournament_state["knockout_results"] = []
    save_tournament_state(tournament_state)

    await ctx.send(f"Group stage ended! Qualifiers for knockout phase: {', '.join(teams[t]['display_name'] for t in qualifiers)}")

    standings_text = build_standings_text(standings)
    schedule_text = build_group_schedule_text(group["matches"])

    bracket_rounds = generate_knockout_bracket(qualifiers)
    tournament_state["knockout_bracket"] = bracket_rounds
    save_tournament_state(tournament_state)

    bracket_text = bracket_to_string(bracket_rounds, [])
    await update_results_message(standings_text=standings_text, schedule_text=schedule_text, bracket_text=bracket_text)

@bot.event
async def on_message(message):
    print(f"Message from '{message.author}' (webhook_id={message.webhook_id}) in channel {message.channel.id}")
    print(f"Content:\n{message.content}\n---")

    await bot.process_commands(message)

    if message.channel.id != RESULTS_CHANNEL_ID:
        return

    if message.author == bot.user:
        return

    lines = message.content.splitlines()

    red_index = find_line_containing(lines, "Red Team:")
    blue_index = find_line_containing(lines, "Blue Team:")

    if red_index == -1 or blue_index == -1:
        return

    try:
        red_clan_line = lines[red_index + 1].strip().strip("*")
        blue_clan_line = lines[blue_index + 1].strip().strip("*")

        red_clan_match = clan_line_re.match(red_clan_line)
        blue_clan_match = clan_line_re.match(blue_clan_line)

        if not red_clan_match or not blue_clan_match:
            return

        red_clan = red_clan_match.group(1).strip().strip("*")
        blue_clan = blue_clan_match.group(1).strip().strip("*")

        score_line = None
        for line in reversed(lines):
            plain = line.strip().strip("*")
            if plain.lower().startswith("red:") and "blue" in plain.lower():
                score_line = plain
                break

        if not score_line:
            return

        score_match = score_line_re.match(score_line)
        if not score_match:
            return

        red_score = int(score_match.group(1))
        blue_score = int(score_match.group(2))

    except Exception:
        return

    red_clan_norm = normalize_name(red_clan)
    blue_clan_norm = normalize_name(blue_clan)

    phase = tournament_state.get("phase", "registration")

    if phase == "group":
        group = tournament_state["groups"].get("GroupA")
        if not group:
            return

        updated = False
        for match in group["matches"]:
            t1_norm = normalize_name(match["team1"])
            t2_norm = normalize_name(match["team2"])

            if {t1_norm, t2_norm} == {red_clan_norm, blue_clan_norm}:
                if red_clan_norm == t1_norm and blue_clan_norm == t2_norm:
                    match["result"] = {
                        "red_score": red_score,
                        "blue_score": blue_score,
                        "winner": match["team1"] if red_score > blue_score else match["team2"] if blue_score > red_score else "Draw"
                    }
                elif red_clan_norm == t2_norm and blue_clan_norm == t1_norm:
                    match["result"] = {
                        "red_score": blue_score,
                        "blue_score": red_score,
                        "winner": match["team1"] if blue_score > red_score else match["team2"] if red_score > blue_score else "Draw"
                    }
                else:
                    match["result"] = {
                        "red_score": red_score,
                        "blue_score": blue_score,
                        "winner": "Draw"
                    }
                updated = True
                break

        if not updated:
            await message.channel.send(f"Match result does not match scheduled group stage matches: {red_clan} vs {blue_clan}")
            return

        save_tournament_state(tournament_state)

        standings_text, schedule_text = await update_group_standings_and_schedule()
        await update_results_message(standings_text=standings_text, schedule_text=schedule_text)

        all_played = all(m["result"] is not None for m in group["matches"])
        if all_played:
            standings = calculate_group_standings(group["matches"], group["teams"])
            sorted_teams = sorted(standings.items(), key=lambda t: (t[1]["points"], t[1]["score_diff"]), reverse=True)

            fraction = 2/3  # Default qualifying fraction
            num_qualify = math.floor(fraction * len(sorted_teams))
            if num_qualify < 1:
                num_qualify = 1

            qualifiers = [team for team, _ in sorted_teams[:num_qualify]]

            tournament_state["phase"] = "knockout"
            tournament_state["qualifiers"] = qualifiers
            tournament_state["knockout_results"] = []
            save_tournament_state(tournament_state)

            channel = bot.get_channel(UPDATE_CHANNEL_ID)
            if channel:
                await channel.send(f"Group stage completed! Qualifiers: {', '.join(qualifiers)}")

            standings_text = build_standings_text(standings)
            schedule_text = build_group_schedule_text(group["matches"])

            bracket_rounds = generate_knockout_bracket(qualifiers)
            tournament_state["knockout_bracket"] = bracket_rounds
            save_tournament_state(tournament_state)

            bracket_text = bracket_to_string(bracket_rounds, [])
            await update_results_message(standings_text=standings_text, schedule_text=schedule_text, bracket_text=bracket_text)

    elif phase == "knockout":
        winner = None
        if red_score > blue_score:
            winner = red_clan
        elif blue_score > red_score:
            winner = blue_clan
        else:
            winner = "Draw"

        match_record = {
            "red_clan": red_clan,
            "blue_clan": blue_clan,
            "red_score": red_score,
            "blue_score": blue_score,
            "winner": winner
        }
        results.append(match_record)
        save_results(results)

        # Update knockout bracket progression with new results
        bracket_rounds = tournament_state.get("knockout_bracket", [])
        update_knockout_bracket_with_results(bracket_rounds, results)
        tournament_state["knockout_bracket"] = bracket_rounds
        save_tournament_state(tournament_state)

        group = tournament_state.get("groups", {}).get("GroupA")
        standings_text = ""
        schedule_text = ""
        if group:
            standings = calculate_group_standings(group["matches"], group["teams"])
            standings_text = build_standings_text(standings)
            schedule_text = build_group_schedule_text(group["matches"])

        bracket_text = bracket_to_string(bracket_rounds, results)
        await update_results_message(standings_text=standings_text, schedule_text=schedule_text, bracket_text=bracket_text)

bot.run(TOKEN)