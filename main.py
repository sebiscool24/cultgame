import os
import random
import json
import time
from pathlib import Path

import discord
from discord.ext import commands

from data.realms import get_breakthrough_chance, get_next_realm, get_progression_requirement, get_realm_bonus, get_realm_display
from data.starter_items import STARTER_ITEM_RANK_CHANCES, get_item_pool, get_rank_chances
from data.traits import RARITY_WEIGHTS, get_bloodline_pool, get_bloodlines_by_rarity, get_origin_pool, get_origins_by_rarity, get_trait_pool
from data.stats_system import calculate_total_stats
from data.game_systems import generate_loot, battle as battle_system, add_xp as add_xp_game, set_cooldown, get_cooldown_remaining
from game_db_functions import (
    add_gear_to_inventory,
    get_player_game_data,
    set_equipped_gear,
    add_wallet_currency,
    get_wallet,
    get_bank_balance,
    deposit_to_bank,
    withdraw_from_bank,
    get_xp,
    set_xp,
    get_cooldowns,
    update_cooldowns,
)
from database import (
    add_starter_item,
    add_items_to_inventory,
    choose_starter_items,
    create_player,
    delete_player,
    get_player,
    get_inventory_items,
    get_item_by_id,
    get_starter_rolls_left,
    get_trait_rolls_left,
    initialize_database,
    player_exists,
    move_selected_starter_items_to_inventory,
    spend_qi,
    spend_trait_roll,
    update_player_realm,
    update_player_bloodline,
    update_player_origin,
    use_starter_roll,
)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set the DISCORD_TOKEN environment variable before running the bot.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# In-memory pending rolls. Rolls are only saved after pressing Confirm in standalone roll panels.
PENDING_TRAIT_ROLLS = {}
WEAPON_EMOJI = "Weapon"
ARMOR_EMOJI = "Armor"

WEAPON_RANK_EMOJI = {
    "F":  "<:w_F:1528216512417108040>",
    "E":  "<:w_E:1528216515327950880>",
    "D-": "<:w_Dm:1528216518297387072>",
    "D":  "<:w_D:1528216521590051000>",
    "D+": "<:w_Dp:1528216525276971118>",
    "C-": "<:w_Cm:1528216529164963960>",
    "C":  "<:w_C:1528216532469944460>",
    "C+": "<:w_Cp:1528216535770857472>",
    "B-": "<:w_Bm:1528216539264979016>",
    "B":  "<:w_B:1528216543110889615>",
    "B+": "<:w_Bp:1528216547011858432>",
    "A-": "<:w_Am:1528216550463508542>",
}

ARMOR_RANK_EMOJI = {
    "F":  "<:a_F:1528216554142044281>",
    "E":  "<:a_E:1528216557241634879>",
    "D-": "<:a_Dm:1528216560995664046>",
    "D":  "<:a_D:1528216564699103262>",
    "D+": "<:a_Dp:1528216568478171227>",
    "C-": "<:a_Cm:1528216572320026714>",
    "C":  "<:a_C:1528216575344115914>",
    "C+": "<:a_Cp:1528216578292715612>",
    "B-": "<:a_Bm:1528216582143344867>",
    "B":  "<:a_B:1528216586022813726>",
    "B+": "<:a_Bp:1528216589084659943>",
    "A-": "<:a_Am:1528216592171798738>",
}


def get_item_icon(item):
    rank = item.get("rank", "")
    item_type = item.get("type", "")
    if item_type == "weapon":
        return WEAPON_RANK_EMOJI.get(rank, "")
    elif item_type == "armor":
        return ARMOR_RANK_EMOJI.get(rank, "")
    return ""

# Commands that do NOT require a character to be created yet
NO_CHARACTER_COMMANDS = {"create", "ping", "help", "originhelp", "orginhelp", "ogrinhelp", "bloodlinehelp", "traithelp"}

@bot.before_invoke
async def require_character(ctx):
    if ctx.command and ctx.command.name not in NO_CHARACTER_COMMANDS:
        if not player_exists(str(ctx.author.id)):
            embed = discord.Embed(
                title="No Character",
                description="You need to create a character first.\nUse **!create** to begin your cultivation path.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            raise commands.CheckFailure("No character")
THEME_DARK = discord.Color.from_rgb(30, 30, 50)  # Dark purple-black
THEME_GOLD = discord.Color.from_rgb(218, 165, 32)  # Dark gold
THEME_CRIMSON = discord.Color.from_rgb(139, 35, 69)  # Crimson red
THEME_BRONZE = discord.Color.from_rgb(165, 130, 50)  # Bronze


def gear_label(item_type):
    return "Weapon" if item_type == "weapon" else "Armor" if item_type == "armor" else "Item"


def get_trait_emoji(trait):
    return ""


def get_trait_icon_file(trait):
    icon_path = trait.get("icon_path")
    if not icon_path:
        return None

    path = Path(icon_path)
    if not path.exists():
        return None

    return discord.File(path, filename=path.name)


def attach_trait_icon(embed, trait, *, image=True):
    icon_file = get_trait_icon_file(trait)
    if icon_file:
        if image:
            embed.set_image(url=f"attachment://{icon_file.filename}")
        else:
            embed.set_thumbnail(url=f"attachment://{icon_file.filename}")
    return icon_file


def get_item_emoji(item):
    return ""


def build_embed(title, description, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=description, color=color)
    return embed


def build_anime_header(title):
    return f"─── {title} ───"


def fit_embed_text(text, limit=1000):
    if len(text) <= limit:
        return text

    kept_lines = []
    current_length = len("...\n")
    for line in reversed(text.splitlines()):
        added_length = len(line) + 1
        if current_length + added_length > limit:
            break
        kept_lines.insert(0, line)
        current_length += added_length
    return "...\n" + "\n".join(kept_lines)


TRAIT_BONUS_LABELS = {
    "attack_percent": "Attack",
    "damage_percent": "Attack",
    "qi_gain_percent": "Qi Gain",
    "defense_percent": "Defense",
    "hp_percent": "HP",
    "luck_percent": "Luck",
    "critical_chance_percent": "Crit Chance",
    "dodge_chance_percent": "Dodge Chance",
    "cultivation_speed_percent": "Cultivation Speed",
    "loot_luck_percent": "Loot Luck",
    "omen_chance_percent": "Omen Chance",
    "sequence_authority_percent": "Sequence Authority",
    "damage_reduction_percent": "Damage Reduction",
    "lifesteal_percent": "Lifesteal",
    "counter_chance_percent": "Counter Chance",
    "fate_anchor_percent": "Fate Anchor",
    "concealment_percent": "Concealment",
    "madness_resistance_percent": "Madness Resistance",
    "breakthrough_reward_bonus_percent": "Breakthrough Reward",
    "unique_evolution_path": "Unique Evolution Path",
    "extra_breakthrough_reward": "Extra Breakthrough Reward",
    "unique_ability_later": "Unique Ability Later",
    "special_mechanic": "Special Mechanic",
}


def get_trait_bonus_label(key):
    return TRAIT_BONUS_LABELS.get(key, key.replace("_percent", "").replace("_", " ").title())


def format_trait_bonuses(bonuses):
    return ", ".join(
        f"{get_trait_bonus_label(key)}"
        if isinstance(value, bool)
        else
        f"{get_trait_bonus_label(key)} {value:+}%"
        if isinstance(value, (int, float))
        else f"{get_trait_bonus_label(key)}"
        for key, value in bonuses.items()
    )


def find_entry_by_name(pool, entry_name):
    if not entry_name:
        return None

    for entry in pool:
        if entry.get("name") == entry_name:
            return entry
    return None


def get_selected_starter_names(player):
    rolled_items = json.loads(player.get("starter_items", "[]"))
    inventory_items = player.get("inventory_items", [])
    game_data = get_player_game_data(player.get("user_id")) or {}
    equipped_weapon = game_data.get("equipped_weapon") or {}
    equipped_armor = game_data.get("equipped_armor") or {}
    weapon_id = player.get("starter_weapon")
    armor_id = player.get("starter_armor")

    weapon_name = get_item_display_name(equipped_weapon) if equipped_weapon else "None"
    armor_name = get_item_display_name(equipped_armor) if equipped_armor else "None"

    for item in inventory_items + rolled_items:
        if item.get("id") == weapon_id:
            weapon_name = get_item_display_name(item)
        if item.get("id") == armor_id:
            armor_name = get_item_display_name(item)

    return weapon_name, armor_name


def get_item_display_name(item):
    if not item:
        return "Unknown Item"
    if item.get("name"):
        return item["name"]
    item_type = item.get("type", "item").title()
    rank = item.get("rank", "?")
    short_id = str(item.get("id", "????"))[-4:]
    return f"{rank}-Rank {item_type} #{short_id}"


def get_item_rank(item):
    return item.get("rank", "?") if item else "?"


def get_all_inventory_items(user_id, player=None):
    player = player or get_player(str(user_id))
    old_inventory = player.get("inventory_items", []) if player else []
    game_data = get_player_game_data(str(user_id)) or {}
    gear_inventory = game_data.get("gear_inventory", []) or []
    return old_inventory + gear_inventory


def get_inventory_emoji_label(item):
    return f"{get_item_icon(item)} {get_item_display_name(item)} [{get_item_rank(item)}]"


def find_trait_by_name(trait_name):
    return find_entry_by_name(get_trait_pool(), trait_name)


def find_origin_by_name(origin_name):
    return find_entry_by_name(get_origin_pool(), origin_name) or find_trait_by_name(origin_name)


def find_bloodline_by_name(bloodline_name):
    return find_entry_by_name(get_bloodline_pool(), bloodline_name)


def get_player_trait_bonuses(player):
    origin_entry = find_origin_by_name(player.get("origin_name") or player.get("trait_name"))
    bloodline_entry = find_bloodline_by_name(player.get("bloodline_name"))
    combined = {}
    for entry in (origin_entry, bloodline_entry):
        if not entry:
            continue
        for key, value in entry.get("bonuses", {}).items():
            if isinstance(value, bool):
                combined[key] = combined.get(key, False) or value
            elif isinstance(value, (int, float)):
                combined[key] = combined.get(key, 0) + value
            else:
                combined[key] = value
    return combined, origin_entry, bloodline_entry


def roll_random_trait():
    return roll_random_from_pool(get_trait_pool())


def roll_random_from_pool(pool):
    rarity = random.choices(
        list(RARITY_WEIGHTS.keys()),
        weights=[RARITY_WEIGHTS[r] for r in RARITY_WEIGHTS.keys()],
        k=1,
    )[0]
    filtered = [entry for entry in pool if entry["rarity"] == rarity]
    if not filtered:
        return None
    return random.choice(filtered)


def roll_random_origin():
    return roll_random_from_pool(get_origin_pool())


def roll_random_bloodline():
    return roll_random_from_pool(get_bloodline_pool())


def build_trait_roll_message(trait, rolls_left):
    return (
        f"Trait Roll Result: {trait['name']} ({trait['rarity']})\n"
        f"Description: {trait['description']}\n"
        f"Bonuses: {format_trait_bonuses(trait['bonuses'])}\n"
        f"Trait Rolls Left: {rolls_left}\n"
        "Use Lock Trait to keep this trait, or Roll Again to spend another roll."
    )


def build_trait_roll_embed(trait, rolls_left, status_line):
    embed = discord.Embed(
        title="Trait Roll",
        description=build_anime_header("Spirit Trait Resonance"),
        color=THEME_GOLD,
    )
    embed.add_field(name="Trait", value=f"**{trait['name']}**", inline=True)
    embed.add_field(name="Rarity", value=trait["rarity"], inline=True)
    embed.add_field(name="Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="Lore", value=trait["description"], inline=False)
    embed.add_field(name="Blessings", value=format_trait_bonuses(trait["bonuses"]), inline=False)
    embed.set_footer(text=status_line)
    return embed


def build_origin_roll_embed(origin, rolls_left, status_line):
    embed = discord.Embed(
        title="Origin Roll",
        description=build_anime_header("Origin Awakening"),
        color=THEME_GOLD,
    )
    embed.add_field(name="Origin", value=f"**{origin['name']}**", inline=True)
    embed.add_field(name="Rarity", value=origin["rarity"], inline=True)
    embed.add_field(name="Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="Path", value=origin["description"], inline=False)
    embed.add_field(name="Active Effects", value=format_trait_bonuses(origin["bonuses"]), inline=False)
    embed.set_footer(text=status_line)
    return embed


def build_bloodline_roll_embed(bloodline, rolls_left, status_line):
    embed = discord.Embed(
        title="Bloodline Roll",
        description=build_anime_header("Bloodline Inheritance"),
        color=THEME_CRIMSON,
    )
    embed.add_field(name="Bloodline", value=f"**{bloodline['name']}**", inline=True)
    embed.add_field(name="Rarity", value=bloodline["rarity"], inline=True)
    embed.add_field(name="Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="Inheritance", value=bloodline["description"], inline=False)
    embed.add_field(name="Long-Term Effects", value=format_trait_bonuses(bloodline["bonuses"]), inline=False)
    embed.set_footer(text=status_line)
    return embed


def build_starter_roll_embed(item, roll_number, rolls_left, status_line):
    stats_text = ", ".join(f"{key}: +{value}" for key, value in item["stats"].items())
    item_icon = get_item_icon(item)
    item_label = f"{item_icon} **{item['name']}**" if item_icon else f"**{item['name']}**"
    embed = discord.Embed(
        title="Starter Gear Roll",
        description=build_anime_header("Spirit Armory Summon"),
        color=THEME_DARK,
    )
    embed.add_field(name="Roll", value=f"{roll_number}/10", inline=True)
    embed.add_field(name="Item", value=item_label, inline=True)
    embed.add_field(name="Rank", value=item["rank"], inline=True)
    embed.add_field(name="Type", value=item['type'].title(), inline=True)
    embed.add_field(name="Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="Stats", value=stats_text, inline=False)
    embed.set_footer(text=status_line)
    return embed


def roll_starter_candidate(user_id):
    if get_starter_rolls_left(user_id) <= 0:
        return None, None, None

    if not use_starter_roll(user_id):
        return None, None, None

    item_type = random.choice(["weapon", "armor"])
    rank = random.choices(
        list(STARTER_ITEM_RANK_CHANCES.keys()),
        weights=[STARTER_ITEM_RANK_CHANCES[r] for r in STARTER_ITEM_RANK_CHANCES.keys()],
        k=1,
    )[0]

    pool = [item for item in get_item_pool(item_type) if item["rank"] == rank]
    if not pool:
        return None, None, None

    rolled_item = random.choice(pool)
    item_summary = {
        "id": rolled_item["id"],
        "name": rolled_item["name"],
        "type": item_type,
        "rank": rolled_item["rank"],
        "description": rolled_item["description"],
        "stats": rolled_item["stats"],
    }
    add_starter_item(user_id, item_summary)

    rolls_left = get_starter_rolls_left(user_id)
    roll_number = 10 - rolls_left
    return item_summary, roll_number, rolls_left


def roll_bloodline_candidate(user_id):
    if get_starter_rolls_left(user_id) <= 0:
        return None, None

    if not use_starter_roll(user_id):
        return None, None

    bloodline = roll_random_bloodline()
    if bloodline is None:
        return None, None

    update_player_bloodline(user_id, bloodline["id"], bloodline["name"])
    rolls_left = get_starter_rolls_left(user_id)
    return bloodline, rolls_left


def get_loadout_items(player):
    starter_candidates = json.loads(player.get("starter_items", "[]"))
    if starter_candidates:
        return starter_candidates, True
    return get_all_inventory_items(player.get("user_id"), player), False


def build_starter_roll_message(item, roll_number, rolls_left):
    stats_text = ", ".join(f"{key}: +{value}" for key, value in item["stats"].items())
    return (
        f"Roll {roll_number}/10\n"
        f"You obtained: {get_item_emoji(item)} {item['name']}\n"
        f"Rank: {item['rank']}\n"
        f"Type: {get_item_emoji(item)} {item['type'].title()}\n"
        f"Stats: {stats_text}\n"
        f"Starter Rolls Left: {rolls_left}\n"
        "These are candidate items only. After all 10 rolls, keep exactly 1 weapon and 1 armor."
    )


def build_create_journey_embed(user_id, display_name):
    player = get_player(user_id)
    if player is None:
        return build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange())

    origin_rolls_left = player.get("trait_rolls_left", 0)
    bloodline_rolls_left = player.get("starter_rolls_left", 0)
    origin_name = player.get("origin_name") or "Unselected"
    bloodline_name = player.get("bloodline_name") or "Unselected"
    origin_entry = find_origin_by_name(origin_name)
    bloodline_entry = find_bloodline_by_name(bloodline_name)
    if origin_entry:
        origin_name = origin_entry["name"]
    if bloodline_entry:
        bloodline_name = bloodline_entry["name"]

    embed = discord.Embed(
        title="Create Character",
        description=(
            "Roll an Origin, roll a Bloodline, then create your cultivator."
        ),
        color=THEME_CRIMSON,
    )
    embed.add_field(name="Cultivator", value=display_name, inline=True)
    embed.add_field(name="Origin Rolls", value=f"**{origin_rolls_left}** remaining", inline=True)
    embed.add_field(name="Bloodline Rolls", value=f"**{bloodline_rolls_left}** remaining", inline=True)
    embed.add_field(name="Origin", value=origin_name, inline=False)
    embed.add_field(name="Bloodline", value=bloodline_name, inline=False)
    embed.set_footer(text="Origin -> Bloodline -> Create")
    return embed


def build_create_trait_panel_embed(display_name, trait, rolls_left):
    status = (
        "Press Continue to keep this origin and roll your bloodline."
        if rolls_left <= 0
        else "This origin is saved. Roll again or press Continue to keep it."
    )
    embed = build_origin_roll_embed(
        trait,
        rolls_left,
        status,
    )
    embed.title = f"Origin - {display_name}"
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    return embed


def build_create_bloodline_panel_embed(display_name, bloodline, rolls_left):
    status = (
        "Press Create to keep this bloodline and awaken your cultivator."
        if rolls_left <= 0
        else "This bloodline is saved. Roll again or press Create to keep it."
    )
    embed = build_bloodline_roll_embed(bloodline, rolls_left, status)
    embed.title = f"Bloodline - {display_name}"
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    return embed


def build_create_loadout_panel_embed(display_name, rolled_items, starter_finalize, starter_weapon_name, starter_armor_name):
    lines = []
    for index, item in enumerate(rolled_items, 1):
        stats_text = ", ".join(f"{key}: +{value}" for key, value in item.get("stats", {}).items())
        lines.append(f"{get_item_icon(item)} **{get_item_display_name(item)}** [{get_item_rank(item)}]\n└ {stats_text}\n")

    embed = discord.Embed(
        title="Loadout",
        description="Pick your saved starter equipment.\n\n",
        color=THEME_DARK,
    )
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="Items", value=items_text, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Equipped Weapon", value=starter_weapon_name, inline=True)
    embed.add_field(name="Equipped Armor", value=starter_armor_name, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.set_footer(
        text=(
            "Choose one weapon and one armor, then save."
            if starter_finalize
            else "Choose your equipped weapon and armor, then save."
        )
    )
    return embed


class CreateJourneyView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=900)
        self.author_id = author_id
        self.current_trait = None
        self.current_bloodline = None
        self.mode = "origin"
        self.current_loadout_items = []
        self.current_starter_finalize = False
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self._set_trait_buttons()

    async def _ensure_owner(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel belongs to a different player.", ephemeral=True)
            return False
        return True

    def _set_hub_buttons(self):
        self.clear_items()

        roll_trait_btn = discord.ui.Button(label="Origin", style=discord.ButtonStyle.primary)
        roll_trait_btn.callback = self.roll_trait_button
        self.add_item(roll_trait_btn)

        roll_starter_btn = discord.ui.Button(label="Bloodline", style=discord.ButtonStyle.primary)
        roll_starter_btn.callback = self.roll_starter_button
        self.add_item(roll_starter_btn)

        open_loadout_btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.success)
        open_loadout_btn.callback = self.open_loadout_button
        self.add_item(open_loadout_btn)

    def _set_trait_buttons(self):
        self.clear_items()

        reroll_trait_btn = discord.ui.Button(label="Roll Again", style=discord.ButtonStyle.primary)
        reroll_trait_btn.callback = self.roll_trait_button
        self.add_item(reroll_trait_btn)

        continue_btn = discord.ui.Button(label="Continue", style=discord.ButtonStyle.success)
        continue_btn.callback = self.continue_to_starter_button
        self.add_item(continue_btn)

    def _set_starter_buttons(self):
        self.clear_items()

        reroll_starter_btn = discord.ui.Button(label="Roll Again", style=discord.ButtonStyle.primary)
        reroll_starter_btn.callback = self.roll_starter_button
        self.add_item(reroll_starter_btn)

        continue_btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.success)
        continue_btn.callback = self.continue_to_loadout_button
        self.add_item(continue_btn)

    def _set_loadout_buttons(self):
        self.clear_items()

        weapon_options = []
        armor_options = []
        for index, item in enumerate(self.current_loadout_items, 1):
            option = discord.SelectOption(
                label=f"#{index} {get_item_display_name(item)} [{get_item_rank(item)}]",
                value=str(index),
                description=item.get("type", "unknown").title(),
            )
            if item.get("type") == "weapon":
                weapon_options.append(option)
            elif item.get("type") == "armor":
                armor_options.append(option)

        if weapon_options:
            weapon_select = discord.ui.Select(
                placeholder="Choose weapon",
                min_values=1,
                max_values=1,
                options=weapon_options,
            )
            weapon_select.callback = self.select_weapon_in_panel
            self.add_item(weapon_select)

        if armor_options:
            armor_select = discord.ui.Select(
                placeholder="Choose armor",
                min_values=1,
                max_values=1,
                options=armor_options,
            )
            armor_select.callback = self.select_armor_in_panel
            self.add_item(armor_select)

        confirm_btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm_loadout_in_panel
        self.add_item(confirm_btn)

    async def roll_trait_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        user_id = str(self.author_id)
        if not player_exists(user_id):
            await interaction.response.send_message(
                embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        if get_trait_rolls_left(user_id) <= 0 or not spend_trait_roll(user_id):
            await interaction.response.send_message(
                embed=build_embed("No Origin Rolls", "You have no origin rolls left.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        trait = roll_random_origin()
        if trait is None:
            await interaction.response.send_message(
                embed=build_embed("Origin Roll Failed", "No origin was found for that rarity.", discord.Color.red()),
                ephemeral=True,
            )
            return

        update_player_origin(user_id, trait["id"], trait["name"])
        PENDING_TRAIT_ROLLS.pop(user_id, None)
        self.current_trait = trait
        self.mode = "origin"
        self._set_trait_buttons()
        rolls_left = get_trait_rolls_left(user_id)
        embed = build_create_trait_panel_embed(interaction.user.display_name, trait, rolls_left)
        icon_file = attach_trait_icon(embed, trait)
        await interaction.response.edit_message(
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )

    async def continue_to_starter_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        user_id = str(self.author_id)
        player = get_player(user_id)
        if player is None:
            await interaction.response.send_message(
                embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        if not (player.get("origin_name") or player.get("trait_name")):
            await interaction.response.send_message("Roll an origin first.", ephemeral=True)
            return

        bloodline, rolls_left = roll_bloodline_candidate(user_id)
        self.mode = "bloodline"
        self._set_starter_buttons()

        if bloodline is None:
            await interaction.response.edit_message(
                embed=build_embed(
                    "Bloodline Complete",
                    "Bloodline rolls are complete. Press Create to awaken your cultivator.",
                    discord.Color.orange(),
                ),
                attachments=[],
                view=self,
            )
            return

        self.current_bloodline = bloodline
        embed = build_create_bloodline_panel_embed(interaction.user.display_name, bloodline, rolls_left)
        icon_file = attach_trait_icon(embed, bloodline)
        await interaction.response.edit_message(
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )

    async def roll_starter_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        user_id = str(self.author_id)
        if not player_exists(user_id):
            await interaction.response.send_message(
                embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        bloodline, rolls_left = roll_bloodline_candidate(user_id)
        if bloodline is None:
            self.mode = "bloodline"
            self._set_starter_buttons()
            await interaction.response.edit_message(
                embed=build_embed(
                    "Bloodline Complete",
                    "Bloodline rolls are complete. Press Create to awaken your cultivator.",
                    discord.Color.orange(),
                ),
                attachments=[],
                view=self,
            )
            return

        self.current_bloodline = bloodline
        self.mode = "bloodline"
        self._set_starter_buttons()
        embed = build_create_bloodline_panel_embed(interaction.user.display_name, bloodline, rolls_left)
        icon_file = attach_trait_icon(embed, bloodline)
        await interaction.response.edit_message(
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )

    async def continue_to_loadout_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        await self.open_loadout_button(interaction)

    async def open_loadout_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        player = get_player(str(self.author_id))
        if player is None:
            await interaction.response.send_message(
                embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        if not (player.get("origin_name") or player.get("trait_name")):
            await interaction.response.send_message(
                embed=build_embed("Missing Origin", "Roll an origin before creating your character.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        if not player.get("bloodline_name"):
            await interaction.response.send_message(
                embed=build_embed("Missing Bloodline", "Roll a bloodline before creating your character.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        self.mode = "complete"
        self.clear_items()

        help_text = (
            f"Origin: **{player.get('origin_name') or player.get('trait_name')}**\n"
            f"Bloodline: **{player.get('bloodline_name')}**\n\n"
            "**Next Steps:**\n"
            "• `!profile` - See your total stats & rank\n"
            "• `!origin` - Inspect your Origin\n"
            "• `!bloodline` - Inspect your Bloodline\n"
            "• `!gather` / `!hunt` / `!wander` - Get loot & XP\n"
            "• `!battle` / `!raid` - Combat challenges\n"
            "• `!level` - Check realm progression"
        )

        await interaction.response.edit_message(
            embed=build_embed(
                "Character Awakened",
                help_text,
                discord.Color.green(),
            ),
            attachments=[],
            view=None,
        )

    async def select_weapon_in_panel(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        self.selected_weapon_roll = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def select_armor_in_panel(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        self.selected_armor_roll = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def confirm_loadout_in_panel(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        if self.current_starter_finalize and get_starter_rolls_left(str(self.author_id)) > 0:
            await interaction.response.send_message(
                "Finish all 10 starter rolls first before confirming.",
                ephemeral=True,
            )
            return

        if self.selected_weapon_roll is None or self.selected_armor_roll is None:
            await interaction.response.send_message(
                "Select both a weapon and an armor first.",
                ephemeral=True,
            )
            return

        weapon_item = self.current_loadout_items[self.selected_weapon_roll - 1]
        armor_item = self.current_loadout_items[self.selected_armor_roll - 1]

        if weapon_item.get("type") != "weapon" or armor_item.get("type") != "armor":
            await interaction.response.send_message(
                "Invalid picks. Choose a weapon in the weapon menu and armor in the armor menu.",
                ephemeral=True,
            )
            return

        if self.current_starter_finalize:
            move_selected_starter_items_to_inventory(
                str(self.author_id),
                [weapon_item.get("id"), armor_item.get("id")],
            )

        choose_starter_items(str(self.author_id), weapon_item.get("id"), armor_item.get("id"))
        set_equipped_gear(str(self.author_id), weapon_item, armor_item)

        self.mode = "hub"
        self.current_loadout_items = []
        self.current_starter_finalize = False
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self._set_hub_buttons()

        help_text = (
            f"{WEAPON_EMOJI} Weapon: {get_item_display_name(weapon_item)} [{get_item_rank(weapon_item)}]\n"
            f"{ARMOR_EMOJI} Armor: {get_item_display_name(armor_item)} [{get_item_rank(armor_item)}]\n\n"
            "**🎯 Next Steps:**\n"
            "• `!profile` - See your total stats & rank\n"
            "• `!cd` - Check action cooldowns\n"
            "• `!inv` - View inventory & swap gear\n"
            "• `!gather` / `!hunt` / `!wander` - Get loot & XP\n"
            "• `!battle` / `!raid` - Combat challenges\n"
            "• `!level` - Check realm progression"
        )
        
        await interaction.response.edit_message(
            embed=build_embed(
                "Character Ready! ✨",
                help_text,
                discord.Color.green(),
            ),
            attachments=[],
            view=None,
        )

    async def back_to_hub_button(self, interaction: discord.Interaction):
        if not await self._ensure_owner(interaction):
            return

        self.current_trait = None
        self.current_loadout_items = []
        self.current_starter_finalize = False
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self.mode = "hub"
        self._set_hub_buttons()
        refreshed = build_create_journey_embed(str(self.author_id), interaction.user.display_name)
        await interaction.response.edit_message(embed=refreshed, attachments=[], view=self)


class TraitRollView(discord.ui.View):
    def __init__(self, author_id, trait):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.trait = trait

    @discord.ui.button(label="Lock Origin", style=discord.ButtonStyle.success)
    async def lock_trait(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for your roll.", ephemeral=True)
            return

        update_player_origin(str(self.author_id), self.trait["id"], self.trait["name"])
        PENDING_TRAIT_ROLLS.pop(str(self.author_id), None)

        for child in self.children:
            child.disabled = True

        embed = build_origin_roll_embed(
            self.trait,
            get_trait_rolls_left(str(self.author_id)),
            "Locked in successfully.",
        )
        icon_file = attach_trait_icon(embed, self.trait)

        await interaction.response.edit_message(
            content="Origin locked in.",
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.primary)
    async def roll_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for your roll.", ephemeral=True)
            return

        user_id = str(self.author_id)

        if get_trait_rolls_left(user_id) <= 0:
            await interaction.response.send_message(
                "You have no origin rolls left. Use Lock Origin to keep your current origin.",
                ephemeral=True,
            )
            return

        if not spend_trait_roll(user_id):
            await interaction.response.send_message(
                "You have no origin rolls left. Use Lock Origin to keep your current origin.",
                ephemeral=True,
            )
            return

        new_trait = roll_random_origin()
        if new_trait is None:
            await interaction.response.send_message("No origin was found for the roll.", ephemeral=True)
            return

        self.trait = new_trait
        PENDING_TRAIT_ROLLS[user_id] = new_trait

        rolls_left = get_trait_rolls_left(user_id)
        embed = build_origin_roll_embed(new_trait, rolls_left, "Use Lock Origin to keep this roll, or Roll Again.")
        icon_file = attach_trait_icon(embed, new_trait)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )


class BloodlineRollView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=300)
        self.author_id = author_id

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.primary)
    async def roll_again_bloodline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        user_id = str(self.author_id)
        bloodline, rolls_left = roll_bloodline_candidate(user_id)
        if bloodline is None:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                embed=build_embed(
                    "Bloodline Rolls Complete",
                    "No bloodline rolls left. Use !bloodline to inspect your inheritance.",
                    discord.Color.orange(),
                ),
                attachments=[],
                view=self,
            )
            return

        if rolls_left <= 0:
            for child in self.children:
                child.disabled = True

        embed = build_bloodline_roll_embed(
            bloodline,
            rolls_left,
            "All 10 rolls complete. Use !bloodline to inspect your inheritance."
            if rolls_left <= 0
            else "Press Roll Again to keep rolling.",
        )
        icon_file = attach_trait_icon(embed, bloodline)
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            attachments=[icon_file] if icon_file else [],
            view=self,
        )


class ResetCharacterView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=120)
        self.author_id = author_id

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        user_id = str(self.author_id)
        deleted = delete_player(user_id)
        PENDING_TRAIT_ROLLS.pop(user_id, None)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=(
                "Character deleted successfully. Use !create to start again."
                if deleted
                else "No character was found to delete."
            ),
            view=self,
        )

    @discord.ui.button(label="Keep Character", style=discord.ButtonStyle.secondary)
    async def keep_character(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Reset cancelled. Your character is unchanged.",
            view=self,
        )


class StarterRollView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=300)
        self.author_id = author_id

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.primary)
    async def roll_again_starter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        user_id = str(self.author_id)
        item, roll_number, rolls_left = roll_starter_candidate(user_id)
        if item is None:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                embed=build_embed(
                    "Starter Rolls Complete",
                    "No starter rolls left. Use !loadout to review candidates and keep 1 weapon + 1 armor.",
                    discord.Color.orange(),
                ),
                view=self,
            )
            return

        if rolls_left <= 0:
            for child in self.children:
                child.disabled = True

        await interaction.response.edit_message(
            content=None,
            embed=build_starter_roll_embed(
                item,
                roll_number,
                rolls_left,
                "All 10 rolls complete. Use !loadout to finalize 1 weapon + 1 armor."
                if rolls_left <= 0
                else "Press Roll Again to keep rolling.",
            ),
            view=self,
        )

    @discord.ui.button(label="Open Loadout", style=discord.ButtonStyle.secondary)
    async def open_starter_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Use !loadout to view items and finalize your 1 weapon + 1 armor.",
            ephemeral=True,
        )


class StarterSelectView(discord.ui.View):
    def __init__(self, author_id, rolled_items, is_starter_finalize):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.rolled_items = rolled_items
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self.is_starter_finalize = is_starter_finalize

        weapon_options = []
        armor_options = []

        for index, item in enumerate(rolled_items, 1):
            option = discord.SelectOption(
                label=f"#{index} {get_item_display_name(item)} [{get_item_rank(item)}]",
                value=str(index),
                description=item.get("type", "unknown").title(),
            )
            if item.get("type") == "weapon":
                weapon_options.append(option)
            elif item.get("type") == "armor":
                armor_options.append(option)

        if weapon_options:
            weapon_select = discord.ui.Select(
                placeholder="Choose your final weapon" if is_starter_finalize else "Choose weapon",
                min_values=1,
                max_values=1,
                options=weapon_options,
            )
            weapon_select.callback = self.select_weapon_callback
            self.add_item(weapon_select)

        if armor_options:
            armor_select = discord.ui.Select(
                placeholder="Choose your final armor" if is_starter_finalize else "Choose armor",
                min_values=1,
                max_values=1,
                options=armor_options,
            )
            armor_select.callback = self.select_armor_callback
            self.add_item(armor_select)

    async def select_weapon_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This selection is not for you.", ephemeral=True)
            return

        self.selected_weapon_roll = int(interaction.data["values"][0])
        await interaction.response.send_message(
            f"Weapon selected: roll #{self.selected_weapon_roll}.",
            ephemeral=True,
        )

    async def select_armor_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This selection is not for you.", ephemeral=True)
            return

        self.selected_armor_roll = int(interaction.data["values"][0])
        await interaction.response.send_message(
            f"Armor selected: roll #{self.selected_armor_roll}.",
            ephemeral=True,
        )

    @discord.ui.button(label="Equip Loadout", style=discord.ButtonStyle.success)
    async def confirm_starter_loadout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        if get_starter_rolls_left(str(self.author_id)) > 0 and self.is_starter_finalize:
            await interaction.response.send_message(
                "Finish all 10 starter rolls first before confirming.",
                ephemeral=True,
            )
            return

        if self.selected_weapon_roll is None or self.selected_armor_roll is None:
            await interaction.response.send_message(
                "Select both a weapon and an armor first.",
                ephemeral=True,
            )
            return

        weapon_item = self.rolled_items[self.selected_weapon_roll - 1]
        armor_item = self.rolled_items[self.selected_armor_roll - 1]

        if weapon_item.get("type") != "weapon" or armor_item.get("type") != "armor":
            await interaction.response.send_message(
                "Invalid picks. Choose a weapon in the weapon menu and armor in the armor menu.",
                ephemeral=True,
            )
            return

        if self.is_starter_finalize:
            move_selected_starter_items_to_inventory(
                str(self.author_id),
                [weapon_item.get("id"), armor_item.get("id")],
            )

        choose_starter_items(str(self.author_id), weapon_item.get("id"), armor_item.get("id"))
        set_equipped_gear(str(self.author_id), weapon_item, armor_item)

        for child in self.children:
            child.disabled = True

        loadout_message = (
            "Starter loadout confirmed via buttons.\n"
            if self.is_starter_finalize
            else "Loadout updated.\n"
        )

        await interaction.response.edit_message(
            content=loadout_message
            + f"Weapon: {get_item_display_name(weapon_item)} [{get_item_rank(weapon_item)}]\n"
            + f"Armor: {get_item_display_name(armor_item)} [{get_item_rank(armor_item)}]",
            view=self,
        )


@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(embed=build_embed("Pong", "Bot is online and responding.", discord.Color.green()))


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Command List",
        color=THEME_CRIMSON,
    )
    embed.add_field(name="Core", value="!ping\n!help\n!create\n!profile\n!use\n!reset", inline=True)
    embed.add_field(name="Origins", value="!origin\n!originhelp", inline=True)
    embed.add_field(name="Bloodlines", value="!bloodline\n!bloodlinehelp", inline=True)
    embed.add_field(name="Gear", value="!loadout\n!inv", inline=True)
    embed.add_field(name="Cultivation", value="!advance\n!level", inline=True)
    embed.add_field(name="Combat", value="!battle\n!raid", inline=True)
    embed.add_field(name="Economy", value="!gather\n!hunt\n!wander\n!balance\n!deposit\n!withdraw", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.set_footer(text="Use !create first before any other command.")
    await ctx.send(embed=embed)


@bot.command(name="create")
async def create_character(ctx):
    user_id = str(ctx.author.id)

    if player_exists(user_id):
        await ctx.send(embed=build_embed("Character Exists", "You already have a character. Use !profile to view it.", discord.Color.orange()))
        return

    created = create_player(user_id, ctx.author.display_name)
    if not created:
        await ctx.send(embed=build_embed("Create Failed", "Could not create your character. Please try again.", discord.Color.red()))
        return

    if not spend_trait_roll(user_id):
        await ctx.send(embed=build_embed("Create Failed", "Could not start your first origin roll. Please try again.", discord.Color.red()))
        return

    trait = roll_random_origin()
    if trait is None:
        await ctx.send(embed=build_embed("Origin Roll Failed", "No origin was found for that rarity.", discord.Color.red()))
        return

    update_player_origin(user_id, trait["id"], trait["name"])
    rolls_left = get_trait_rolls_left(user_id)
    view = CreateJourneyView(ctx.author.id)
    view.current_trait = trait
    embed = build_create_trait_panel_embed(ctx.author.display_name, trait, rolls_left)
    icon_file = attach_trait_icon(embed, trait)

    await ctx.send(
        embed=embed,
        file=icon_file,
        view=view,
    )


@bot.command(name="rollorigin", aliases=["rollorgin", "rollogrin", "rolltrait"])
async def roll_trait(ctx):
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    if get_trait_rolls_left(user_id) <= 0:
        await ctx.send(embed=build_embed("No Origin Rolls", "You have no origin rolls left.", discord.Color.orange()))
        return

    if not spend_trait_roll(user_id):
        await ctx.send(embed=build_embed("No Origin Rolls", "You have no origin rolls left.", discord.Color.orange()))
        return

    trait = roll_random_origin()
    if trait is None:
        await ctx.send(embed=build_embed("Origin Roll Failed", "No origin was found for that rarity.", discord.Color.red()))
        return

    PENDING_TRAIT_ROLLS[user_id] = trait
    rolls_left = get_trait_rolls_left(user_id)
    embed = build_origin_roll_embed(trait, rolls_left, "Use Lock Origin to keep this roll, or Roll Again.")
    icon_file = attach_trait_icon(embed, trait)

    await ctx.send(
        embed=embed,
        file=icon_file,
        view=TraitRollView(ctx.author.id, trait),
    )


@bot.command(name="reset")
async def reset_roll(ctx):
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    await ctx.send(
        embed=build_embed(
            "Reset Character ⚠️",
            "This will delete your character completely (trait, rolls, starter items, and progress).\nPress Confirm Delete to continue.",
            discord.Color.red(),
        ),
        view=ResetCharacterView(ctx.author.id),
    )


@bot.command(name="rollbloodline", aliases=["rollstarter"])
async def roll_starter(ctx):
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    bloodline, rolls_left = roll_bloodline_candidate(user_id)
    if bloodline is None:
        await ctx.send(
            embed=build_embed(
                "Bloodline Rolls Complete",
                "You have no bloodline rolls left. Use !bloodline to inspect your inheritance.",
                discord.Color.orange(),
            )
        )
        return

    embed = build_bloodline_roll_embed(
        bloodline,
        rolls_left,
        "All 10 rolls complete. Use !bloodline to inspect your inheritance."
        if rolls_left <= 0
        else "Press Roll Again to continue.",
    )
    icon_file = attach_trait_icon(embed, bloodline)
    if icon_file:
        await ctx.send(embed=embed, file=icon_file, view=BloodlineRollView(ctx.author.id))
    else:
        await ctx.send(embed=embed, view=BloodlineRollView(ctx.author.id))


@bot.command(name="loadout")
async def starter_inventory(ctx):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    rolled_items, starter_finalize = get_loadout_items(player)
    if not rolled_items:
        await ctx.send(embed=build_embed("Loadout ✨", "You do not have any items to equip yet.", discord.Color.orange()))
        return

    lines = []
    for index, item in enumerate(rolled_items, 1):
        stats_text = ", ".join(f"{key}: +{value}" for key, value in item.get("stats", {}).items())
        lines.append(f"{get_item_icon(item)} **{get_item_display_name(item)}** [{get_item_rank(item)}]\n└ {stats_text}\n")

    starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

    embed = discord.Embed(
        title="Loadout — Starter Candidates" if starter_finalize else "Loadout",
        color=THEME_DARK,
    )
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="Items", value=items_text, inline=False)
    embed.add_field(name="Equipped Weapon", value=starter_weapon_name, inline=True)
    embed.add_field(name="Equipped Armor", value=starter_armor_name, inline=True)
    embed.set_footer(text="Keep 1 weapon + 1 armor. Use dropdowns or !choosestarter <weapon_roll> <armor_roll>.")
    await ctx.send(embed=embed, view=StarterSelectView(ctx.author.id, rolled_items, starter_finalize))


@bot.command(name="inv", aliases=["inventory"])
async def inventory_view(ctx):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    gear_inventory = get_all_inventory_items(str(ctx.author.id), player)
    
    if not gear_inventory:
        await ctx.send(
            embed=build_embed(
                "Spiritual Armory Empty",
                "No treasures yet. Gain artifacts through !gather, !hunt, !wander, !battle, and !raid commands.",
                discord.Color.orange(),
            )
        )
        return

    lines = []
    for index, item in enumerate(gear_inventory, 1):
        stats_text = ", ".join(f"{key}: +{value}" for key, value in item.get("stats", {}).items())
        lines.append(f"{get_item_icon(item)} **{get_item_display_name(item)}** [{get_item_rank(item)}]\n└ {stats_text}\n")

    embed = discord.Embed(title="Armory", color=THEME_DARK)
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="Items", value=items_text, inline=False)
    embed.set_footer(text="Use !loadout to equip a weapon and armor for battle")
    await ctx.send(embed=embed)


@bot.command(name="choosestarter")
async def choose_starter(ctx, weapon_roll: int, armor_roll: int):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    rolled_items, starter_finalize = get_loadout_items(player)
    if not rolled_items:
        await ctx.send("You have no items recorded yet.")
        return

    if starter_finalize and get_starter_rolls_left(str(ctx.author.id)) > 0:
        await ctx.send(embed=build_embed("Starter Not Finished", "Finish all 10 starter rolls first before choosing your final weapon and armor.", discord.Color.orange()))
        return

    if weapon_roll < 1 or weapon_roll > len(rolled_items) or armor_roll < 1 or armor_roll > len(rolled_items):
        await ctx.send(embed=build_embed("Invalid Choice", "Invalid item numbers. Use !loadout or !inventory to view valid item indexes.", discord.Color.red()))
        return

    weapon_item = rolled_items[weapon_roll - 1]
    armor_item = rolled_items[armor_roll - 1]

    if weapon_item.get("type") != "weapon":
        await ctx.send(embed=build_embed("Invalid Weapon", f"The selected item is not a {WEAPON_EMOJI} weapon.", discord.Color.red()))
        return

    if armor_item.get("type") != "armor":
        await ctx.send(embed=build_embed("Invalid Armor", f"The selected item is not a {ARMOR_EMOJI} armor item.", discord.Color.red()))
        return

    choose_starter_items(str(ctx.author.id), weapon_item.get("id"), armor_item.get("id"))

    if get_starter_rolls_left(str(ctx.author.id)) <= 0 and player.get("starter_items_list", []):
        move_selected_starter_items_to_inventory(
            str(ctx.author.id),
            [weapon_item.get("id"), armor_item.get("id")],
        )

    set_equipped_gear(str(ctx.author.id), weapon_item, armor_item)

    await ctx.send(
        embed=build_embed(
            "Loadout Confirmed ✨",
            f"{WEAPON_EMOJI} Weapon: {get_item_display_name(weapon_item)} [{get_item_rank(weapon_item)}]\n"
            f"{ARMOR_EMOJI} Armor: {get_item_display_name(armor_item)} [{get_item_rank(armor_item)}]",
            discord.Color.green(),
        )
    )


@bot.command(name="advance")
async def advance(ctx):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    realm_name = player['realm']
    stage = player['realm_stage']
    requirement = get_progression_requirement(realm_name, stage)
    chance = get_breakthrough_chance(realm_name, stage)
    bonus = get_realm_bonus(realm_name)

    if player['qi'] < requirement:
        await ctx.send(embed=build_embed("🌠 Breakthrough Requirements", f"You need **{requirement} Qi** to advance.\nCurrent Qi: **{player['qi']}**\nBreakthrough chance: **{chance}%**", discord.Color.orange()))
        return

    if not spend_qi(str(ctx.author.id), requirement):
        await ctx.send(embed=build_embed("Insufficient Qi", "You do not have enough Qi to attempt this breakthrough.", discord.Color.red()))
        return

    success = random.randint(1, 100) <= chance
    if success:
        if stage >= 9:
            realm_name = get_next_realm(realm_name)
            next_stage = 1
        else:
            next_stage = stage + 1
            if next_stage > 9:
                realm_name = get_next_realm(realm_name)
                next_stage = 1

        update_player_realm(str(ctx.author.id), realm_name, next_stage)
        await ctx.send(embed=build_embed("✨ Breakthrough Success", f"Realm: **{get_realm_display(realm_name, next_stage)}**\nBonus: **{bonus}**", discord.Color.green()))
    else:
        await ctx.send(embed=build_embed("🌫️ Breakthrough Failed", f"You spent **{requirement} Qi**.\nBreakthrough chance: **{chance}%**", discord.Color.red()))


# ============================================================================
# GAME SYSTEM COMMANDS
# ============================================================================

from data.game_systems import (
    generate_loot,
    add_xp,
    get_xp_for_next_realm,
    battle,
    calculate_combat_stats,
    create_gear_item,
    format_hp_bar,
    get_cooldown_remaining,
    simulate_combat_round,
    set_cooldown,
)
from data.stats_system import (
    calculate_total_stats,
    get_trait_bonuses,
    format_stats,
    calculate_rank_from_stats,
)
from game_db_functions import (
    get_player_game_data,
    add_gear_to_inventory,
    get_cooldowns,
    update_cooldowns,
    get_xp as db_get_xp,
    set_xp,
    get_base_stats,
    add_wallet_currency,
    get_wallet,
    get_bank_balance,
    deposit_to_bank,
    withdraw_from_bank,
)


@bot.command(name="profile")
async def player_profile(ctx):
    """Show player profile with stats from equipment and traits."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    player = get_player(user_id)
    game_data = get_player_game_data(user_id)

    if not game_data:
        await ctx.send(
            embed=build_embed(
                "Data Error",
                "Could not load your game data.",
                discord.Color.red(),
            )
        )
        return

    # Calculate total stats
    base_stats = game_data["base_stats"]
    equipped_weapon = game_data["equipped_weapon"]
    equipped_armor = game_data["equipped_armor"]
    
    trait_bonuses, origin_entry, bloodline_entry = get_player_trait_bonuses(player)

    total_stats = calculate_total_stats(base_stats, equipped_weapon, equipped_armor, trait_bonuses)
    rank_display, rank_letter = calculate_rank_from_stats(total_stats)

    realm_display = get_realm_display(player["realm"], player["realm_stage"])
    origin_display = player.get("origin_name") or player.get("trait_name") or "None"
    bloodline_display = player.get("bloodline_name") or "None"
    if origin_entry:
        origin_display = f"{origin_entry['name']} ({origin_entry['rarity']})"
    if bloodline_entry:
        bloodline_display = f"{bloodline_entry['name']} ({bloodline_entry['rarity']})"

    # Build profile embed with user avatar
    embed = discord.Embed(
        title=f"🏯 Cultivator Profile",
        description=build_anime_header("Your Cultivation Status"),
        color=THEME_DARK,
    )
    
    avatar_url = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    embed.set_author(name=ctx.author.display_name, icon_url=avatar_url)
    trait_icon_file = attach_trait_icon(embed, origin_entry, image=False) if origin_entry else None
    if not trait_icon_file:
        embed.set_thumbnail(url=avatar_url)
    
    xp = db_get_xp(user_id)
    next_realm_xp = get_xp_for_next_realm(player["realm_stage"])
    progress_pct = int((xp / next_realm_xp) * 100) if next_realm_xp > 0 else 0

    # Identity row
    embed.add_field(name="Cultivator", value=f"{ctx.author.mention}\n**{player['character_name']}**", inline=True)
    embed.add_field(name="Realm", value=realm_display, inline=True)
    embed.add_field(name="Rank", value=rank_display, inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.add_field(name="XP", value=f"{xp:,} / {next_realm_xp:,}", inline=True)
    embed.add_field(name="Progress", value=f"{progress_pct}%", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.add_field(
        name="Combat Stats",
        value=(
            f"**Damage** — {total_stats['damage']}\n"
            f"**HP** — {total_stats['hp']}\n"
            f"**Defense** — {total_stats['defense']}"
        ),
        inline=True
    )
    embed.add_field(
        name="\u200b",
        value=(
            f"**Speed** — {total_stats['speed']}\n"
            f"**Luck** — {total_stats['luck']}\n"
            f"**Armor** — {total_stats['armor']}"
        ),
        inline=True
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    weapon_name = "None"
    weapon_stats = ""
    armor_name = "None"
    armor_stats = ""

    if equipped_weapon:
        weapon_icon = WEAPON_RANK_EMOJI.get(equipped_weapon.get('rank', ''), '')
        weapon_name = f"{weapon_icon} {equipped_weapon.get('rank')} {equipped_weapon.get('name')}"
        weapon_stats = "\n" + ", ".join(f"{k} +{v}" for k, v in equipped_weapon.get("stats", {}).items())
    if equipped_armor:
        armor_icon = ARMOR_RANK_EMOJI.get(equipped_armor.get('rank', ''), '')
        armor_name = f"{armor_icon} {equipped_armor.get('rank')} {equipped_armor.get('name')}"
        armor_stats = "\n" + ", ".join(f"{k} +{v}" for k, v in equipped_armor.get("stats", {}).items())

    embed.add_field(name="Weapon", value=f"{weapon_name}{weapon_stats}", inline=True)
    embed.add_field(name="Armor", value=f"{armor_name}{armor_stats}", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.add_field(name="Origin", value=origin_display, inline=True)
    embed.add_field(name="Bloodline", value=bloodline_display, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.set_footer(text="!origin  |  !bloodline  |  !inv  |  !cd")
    if trait_icon_file:
        await ctx.send(embed=embed, file=trait_icon_file)
    else:
        await ctx.send(embed=embed)


@bot.command(name="gather")
async def gather_loot(ctx):
    """Gather resources and loot. High chance of low-tier items."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    # Check cooldown
    cooldowns = get_cooldowns(user_id)
    on_cooldown, remaining = get_cooldown_remaining(cooldowns, "gather")
    if on_cooldown:
        await ctx.send(
            embed=build_embed(
                "On Cooldown",
                f"You can gather again in **{int(remaining)}** seconds.",
                discord.Color.orange(),
            )
        )
        return

    # Generate loot
    loot_items, xp_earned, currency_earned = generate_loot("gather")
    
    # Add to inventory and wallet
    add_gear_to_inventory(user_id, loot_items)
    add_wallet_currency(user_id, currency_earned)
    
    # Add XP
    player = get_player(user_id)
    xp = get_xp(user_id)
    new_xp, new_realm, leveled_up = add_xp_game(xp, player["realm_stage"], xp_earned)
    set_xp(user_id, new_xp)
    
    if leveled_up and new_realm != player["realm_stage"]:
        update_player_realm(user_id, player["realm"], new_realm)

    # Set cooldown (30 seconds)
    cooldowns = set_cooldown(cooldowns, "gather", 30)
    update_cooldowns(user_id, cooldowns)

    loot_text = "" if not loot_items else "\n".join([f"• {item['rank']} {item['type'].title()}: **{item['id']}**" for item in loot_items])
    loot_section = f"\n\nResources Absorbed:\n{loot_text}" if loot_text else ""
    level_up_msg = f"\n✨ **Realm Up!** Now at stage {new_realm}!" if leveled_up else ""
    
    embed = discord.Embed(title="⛩️ Meditation Complete", color=THEME_GOLD)
    embed.add_field(name="⚡ Spiritual Power", value=f"**+{xp_earned}** XP", inline=True)
    embed.add_field(name="🪙 Spirit Coins", value=f"**+{currency_earned}**", inline=True)
    if level_up_msg:
        embed.add_field(name="\u200b", value=level_up_msg.strip(), inline=False)
    embed.set_footer(text="!gather again in 30s")
    await ctx.send(embed=embed)


@bot.command(name="hunt")
async def hunt_loot(ctx):
    """Cultivate through combat trials. Steady cultivation rewards."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    # Check cooldown
    cooldowns = get_cooldowns(user_id)
    on_cooldown, remaining = get_cooldown_remaining(cooldowns, "hunt")
    if on_cooldown:
        await ctx.send(
            embed=build_embed(
                "On Cooldown",
                f"You can hunt again in **{int(remaining)}** seconds.",
                discord.Color.orange(),
            )
        )
        return

    # Generate loot
    loot_items, xp_earned, currency_earned = generate_loot("hunt")
    
    # Add to inventory and wallet
    add_gear_to_inventory(user_id, loot_items)
    add_wallet_currency(user_id, currency_earned)
    
    # Add XP
    player = get_player(user_id)
    xp = get_xp(user_id)
    new_xp, new_realm, leveled_up = add_xp_game(xp, player["realm_stage"], xp_earned)
    set_xp(user_id, new_xp)
    
    if leveled_up and new_realm != player["realm_stage"]:
        update_player_realm(user_id, player["realm"], new_realm)

    # Set cooldown (60 seconds)
    cooldowns = set_cooldown(cooldowns, "hunt", 60)
    update_cooldowns(user_id, cooldowns)

    loot_text = "\n".join([f"• {item['rank']} {item['type'].title()}: **{item['id']}**" for item in loot_items])
    level_up_msg = f"\n✨ **Realm Up!** Now at stage {new_realm}!" if leveled_up else ""
    
    embed = discord.Embed(title="⛩️ Cultivation Trial Complete", color=THEME_GOLD)
    embed.add_field(name="⚡ Spiritual Power", value=f"**+{xp_earned}** XP", inline=True)
    embed.add_field(name="🪙 Spirit Coins", value=f"**+{currency_earned}**", inline=True)
    if level_up_msg:
        embed.add_field(name="\u200b", value=level_up_msg.strip(), inline=False)
    embed.set_footer(text="!hunt again in 60s")
    await ctx.send(embed=embed)


@bot.command(name="wander")
async def wander_loot(ctx):
    """Wander the lands. Rare chance at high-tier loot with medium-high XP."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    # Check cooldown
    cooldowns = get_cooldowns(user_id)
    on_cooldown, remaining = get_cooldown_remaining(cooldowns, "wander")
    if on_cooldown:
        await ctx.send(
            embed=build_embed(
                "On Cooldown",
                f"You can wander again in **{int(remaining)}** seconds.",
                discord.Color.orange(),
            )
        )
        return

    # Generate loot
    loot_items, xp_earned, currency_earned = generate_loot("wander")
    
    # Add to inventory and wallet
    add_gear_to_inventory(user_id, loot_items)
    add_wallet_currency(user_id, currency_earned)
    
    # Add XP
    player = get_player(user_id)
    xp = get_xp(user_id)
    new_xp, new_realm, leveled_up = add_xp_game(xp, player["realm_stage"], xp_earned)
    set_xp(user_id, new_xp)
    
    if leveled_up and new_realm != player["realm_stage"]:
        update_player_realm(user_id, player["realm"], new_realm)

    # Set cooldown (120 seconds)
    cooldowns = set_cooldown(cooldowns, "wander", 120)
    update_cooldowns(user_id, cooldowns)

    loot_text = "\n".join([f"• {item['rank']} {item['type'].title()}: **{item['id']}**" for item in loot_items])
    level_up_msg = f"\n✨ **Realm Up!** Now at stage {new_realm}!" if leveled_up else ""
    
    await ctx.send(
        embed=build_embed(
            "� Forbidden Lands Traversed",
            f"**+{xp_earned} Spiritual Power** | **+{currency_earned}** Spirit Coins\n\nLegendary Treasures:\n{loot_text}{level_up_msg}",
            THEME_GOLD,
        )
    )


class BattleTurnView(discord.ui.View):
    def __init__(self, author_id, player, player_stats, difficulty):
        super().__init__(timeout=180)
        self.author_id = int(author_id)
        self.user_id = str(author_id)
        self.player = player
        self.player_stats = player_stats
        self.difficulty = difficulty
        self.round_count = 0
        self.finished = False
        self.turn_summary = "Click **Attack** to take your turn."

        difficulty_multiplier = {"normal": 1.0, "hard": 1.3, "raid": 1.6}.get(difficulty, 1.0)
        self.enemy_stats = calculate_combat_stats(
            {
                "damage": int(player_stats["damage"] * difficulty_multiplier * 0.8),
                "defense": int(player_stats["defense"] * difficulty_multiplier * 0.8),
                "luck": int(player_stats["luck"] * difficulty_multiplier * 0.7),
                "speed": int(player_stats["speed"] * difficulty_multiplier * 0.9),
                "armor": int(player_stats["armor"] * difficulty_multiplier * 0.8),
                "hp": int((50 + player_stats.get("armor", 0) * 2) * difficulty_multiplier),
            }
        )
        self.player_combat = calculate_combat_stats(player_stats)
        self.player_health = self.player_combat["health"]
        self.enemy_health = self.enemy_stats["health"]

    def build_embed(self, title=None, color=None):
        enemy_name = "Raid Calamity" if self.difficulty == "raid" else "Wild Cultivator"
        embed = discord.Embed(
            title=title or ("Raid Encounter" if self.difficulty == "raid" else "Battle Encounter"),
            description=build_anime_header("Turn-Based Combat"),
            color=color or (THEME_CRIMSON if self.difficulty == "raid" else THEME_DARK),
        )
        embed.add_field(name="Your HP", value=f"`{format_hp_bar(self.player_health, self.player_combat['health'])}`", inline=False)
        embed.add_field(name=f"{enemy_name} HP", value=f"`{format_hp_bar(self.enemy_health, self.enemy_stats['health'])}`", inline=False)
        embed.add_field(
            name="Combat",
            value=(
                f"Your ATK **{self.player_combat['attack']}** / DEF **{self.player_combat['defense']}**\n"
                f"Enemy ATK **{self.enemy_stats['attack']}** / DEF **{self.enemy_stats['defense']}**"
            ),
            inline=False,
        )
        embed.add_field(name="Current Turn", value=fit_embed_text(self.turn_summary, 950), inline=False)
        embed.set_footer(text="Press Attack to take your next turn" if not self.finished else "Fight ended")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This fight is not yours.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True

    def _disable_buttons(self):
        self.finished = True
        for child in self.children:
            child.disabled = True

    def _roll_rewards(self):
        if self.difficulty == "raid":
            xp_earned = random.randint(100, 150)
            currency_earned = random.randint(100, 250)
            loot_chance = 0.85
        else:
            xp_earned = random.randint(40, 80)
            currency_earned = random.randint(60, 150)
            loot_chance = 0.7

        loot = (
            create_gear_item(random.choice(["D", "C", "B"]), random.choice(["weapon", "armor"]))
            if random.random() < loot_chance
            else None
        )
        return xp_earned, currency_earned, loot

    def _grant_rewards(self):
        xp_earned, currency_earned, loot = self._roll_rewards()
        if loot:
            add_gear_to_inventory(self.user_id, [loot])
        add_wallet_currency(self.user_id, currency_earned)

        xp = get_xp(self.user_id)
        new_xp, new_realm, leveled_up = add_xp_game(xp, self.player["realm_stage"], xp_earned)
        set_xp(self.user_id, new_xp)
        if leveled_up and new_realm != self.player["realm_stage"]:
            update_player_realm(self.user_id, self.player["realm"], new_realm)

        reward_lines = [f"XP **+{xp_earned}**", f"Spirit Coins **+{currency_earned}**"]
        if loot:
            reward_lines.append(f"Loot **{get_item_display_name(loot)} [{get_item_rank(loot)}]**")
        if leveled_up:
            reward_lines.append(f"Realm Up: stage **{new_realm}**")
        return "\n".join(reward_lines)

    def _player_attack(self):
        logs = ["**Your Turn**"]
        healing = 0

        if random.random() * 100 <= self.enemy_stats["dodge_chance"]:
            logs.append("The enemy dodges your attack.")
            return 0, healing, logs

        blocked = max(0, self.enemy_stats.get("defense", 0) // 2)
        damage = max(1, self.player_combat["attack"] - blocked)
        if random.random() * 100 < self.player_combat["crit_chance"]:
            damage = int(damage * 1.5)
            logs.append(f"You strike. Enemy DEF blocks **{blocked}**. Critical hit for **{damage}** damage.")
        else:
            logs.append(f"You strike. Enemy DEF blocks **{blocked}**. Dealt **{damage}** damage.")

        if random.random() * 100 < self.player_combat.get("omen_chance_percent", 0):
            omen_damage = max(1, self.player_combat["attack"] // 2)
            damage += omen_damage
            logs.append(f"Omen fulfilled: **+{omen_damage}** unavoidable damage.")

        if self.player_combat.get("lifesteal_percent", 0):
            healing = int(damage * self.player_combat["lifesteal_percent"] / 100)
            if healing > 0:
                logs.append(f"Lifesteal restores **{healing}** HP.")

        return damage, healing, logs

    def _enemy_attack(self):
        logs = ["**Enemy Turn**"]

        if random.random() * 100 <= self.player_combat["dodge_chance"]:
            logs.append("You dodge the enemy attack.")
            return 0, 0, logs

        blocked = max(0, self.player_combat.get("defense", 0) // 2)
        damage = max(1, self.enemy_stats["attack"] - blocked)
        if random.random() * 100 < self.enemy_stats["crit_chance"]:
            damage = int(damage * 1.5)
            logs.append(f"Enemy attacks. Your DEF blocks **{blocked}**. Critical hit for **{damage}** damage.")
        else:
            logs.append(f"Enemy attacks. Your DEF blocks **{blocked}**. You take **{damage}** damage.")

        reduction = self.player_combat.get("damage_reduction_percent", 0)
        if reduction:
            reduced_by = int(damage * reduction / 100)
            damage -= reduced_by
            logs.append(f"Damage reduction prevents **{reduced_by}** damage.")

        counter_damage = 0
        if random.random() * 100 < self.player_combat.get("counter_chance_percent", 0):
            counter_damage = max(1, self.player_combat["attack"] // 2)
            logs.append(f"Countered through fate for **{counter_damage}** damage.")

        return damage, counter_damage, logs

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            await interaction.response.send_message("This fight is already over.", ephemeral=True)
            return

        self.round_count += 1
        turn_lines = [f"**Round {self.round_count}**"]

        player_damage, healing, player_logs = self._player_attack()
        turn_lines.extend(player_logs)
        self.enemy_health = max(0, self.enemy_health - player_damage)
        self.player_health = min(
            self.player_combat["health"],
            max(0, self.player_health + healing),
        )

        if self.enemy_health <= 0:
            self._disable_buttons()
            rewards = self._grant_rewards()
            turn_lines.append("**Victory.**")
            self.turn_summary = "\n".join(turn_lines)
            embed = self.build_embed("Opponent Defeated" if self.difficulty != "raid" else "Calamity Subdued", THEME_GOLD)
            embed.add_field(name="Rewards", value=rewards, inline=False)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        enemy_damage, counter_damage, enemy_logs = self._enemy_attack()
        turn_lines.extend(enemy_logs)
        self.player_health = max(0, self.player_health - enemy_damage)
        self.enemy_health = max(0, self.enemy_health - counter_damage)

        if self.enemy_health <= 0:
            self._disable_buttons()
            rewards = self._grant_rewards()
            turn_lines.append("**Victory.**")
            self.turn_summary = "\n".join(turn_lines)
            embed = self.build_embed("Opponent Defeated" if self.difficulty != "raid" else "Calamity Subdued", THEME_GOLD)
            embed.add_field(name="Rewards", value=rewards, inline=False)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        if self.player_health <= 0:
            self._disable_buttons()
            turn_lines.append("**Defeat.**")
            self.turn_summary = "\n".join(turn_lines)
            await interaction.response.edit_message(
                embed=self.build_embed("Defeated" if self.difficulty != "raid" else "Overwhelmed by Calamity", THEME_CRIMSON),
                view=self,
            )
            return

        self.turn_summary = "\n".join(turn_lines)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


@bot.command(name="battle")
async def combat_battle(ctx):
    """Engage in combat with an enemy."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    # Check cooldown
    cooldowns = get_cooldowns(user_id)
    on_cooldown, remaining = get_cooldown_remaining(cooldowns, "battle")
    if on_cooldown:
        await ctx.send(
            embed=build_embed(
                "On Cooldown",
                f"You can battle again in **{int(remaining)}** seconds.",
                discord.Color.orange(),
            )
        )
        return

    # Get player stats
    game_data = get_player_game_data(user_id)
    player = get_player(user_id)
    trait_bonuses, _, _ = get_player_trait_bonuses(player)
    player_stats = calculate_total_stats(
        game_data["base_stats"],
        game_data["equipped_weapon"],
        game_data["equipped_armor"],
        trait_bonuses,
    )

    view = BattleTurnView(ctx.author.id, player, player_stats, "normal")
    await ctx.send(embed=view.build_embed(), view=view)

    cooldowns = set_cooldown(cooldowns, "battle", 90)
    update_cooldowns(user_id, cooldowns)


@bot.command(name="raid")
async def combat_raid(ctx):
    """Engage in a harder raid combat for greater rewards."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    # Check cooldown
    cooldowns = get_cooldowns(user_id)
    on_cooldown, remaining = get_cooldown_remaining(cooldowns, "raid")
    if on_cooldown:
        await ctx.send(
            embed=build_embed(
                "On Cooldown",
                f"You can raid again in **{int(remaining)}** seconds.",
                discord.Color.orange(),
            )
        )
        return

    # Get player stats
    game_data = get_player_game_data(user_id)
    player = get_player(user_id)
    trait_bonuses, _, _ = get_player_trait_bonuses(player)
    player_stats = calculate_total_stats(
        game_data["base_stats"],
        game_data["equipped_weapon"],
        game_data["equipped_armor"],
        trait_bonuses,
    )

    view = BattleTurnView(ctx.author.id, player, player_stats, "raid")
    await ctx.send(embed=view.build_embed(), view=view)

    cooldowns = set_cooldown(cooldowns, "raid", 180)
    update_cooldowns(user_id, cooldowns)


@bot.command(name="cd")
async def show_cooldowns(ctx):
    """Show all active cooldowns."""
    user_id = str(ctx.author.id)
    
    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return
    
    cooldowns = get_cooldowns(user_id)
    current_time = time.time()
    
    cooldown_info = []
    for cmd in ["gather", "hunt", "wander", "battle", "raid"]:
        if cmd in cooldowns:
            remaining = cooldowns[cmd] - current_time
            if remaining > 0:
                cooldown_info.append(f"**{cmd.title()}**: {int(remaining)}s")
            else:
                cooldown_info.append(f"**{cmd.title()}**: Ready")
        else:
            cooldown_info.append(f"**{cmd.title()}**: Ready")
    
    ready = [c for c in cooldown_info if "Ready" in c]
    waiting = [c for c in cooldown_info if "Ready" not in c]

    embed = discord.Embed(title="Cultivation Cooldowns", color=THEME_DARK)
    if ready:
        embed.add_field(name="Ready", value="\n".join(ready), inline=True)
    if waiting:
        embed.add_field(name="Cooling Down", value="\n".join(waiting), inline=True)
    embed.set_footer(text="Spiritual energy recovers when timers reach zero")
    await ctx.send(embed=embed)


def get_trait_power_rating(rarity):
    """Get visual rating for how good a trait is."""
    ratings = {
        "Common": "⭐☆☆☆☆ (Modest)",
        "Uncommon": "⭐⭐☆☆☆ (Decent)",
        "Normal": "⭐⭐⭐☆☆ (Good)",
        "Great": "⭐⭐⭐⭐☆ (Powerful)",
        "Amazing": "⭐⭐⭐⭐☆ (Excellent)",
        "Legendary": "⭐⭐⭐⭐⭐ (Legendary)",
        "Celestial": "⭐⭐⭐⭐⭐ (Celestial - Elite)",
        "Godworthy": "⭐⭐⭐⭐⭐ (Godworthy - S-Tier)",
        "Empyrean": "⭐⭐⭐⭐⭐ (Empyrean - Apex)",
    }
    return ratings.get(rarity, "Unknown")


def get_trait_rarity_tier(rarity):
    """Get tier rating (1-8) for trait rarity."""
    tiers = {
        "Common": 1,
        "Uncommon": 2,
        "Normal": 3,
        "Great": 4,
        "Amazing": 5,
        "Legendary": 6,
        "Celestial": 7,
        "Godworthy": 8,
        "Empyrean": 9,
    }
    return tiers.get(rarity, 0)


def format_trait_bonuses_detailed(trait):
    """Format complete trait information for display."""
    bonuses = trait.get("bonuses", {})
    bonus_text = ""
    
    for key, value in bonuses.items():
        if isinstance(value, bool):
            if value:
                label = get_trait_bonus_label(key)
                bonus_text += f"• {label}\n"
        elif key.endswith("_multiplier") and isinstance(value, (int, float)):
            label = get_trait_bonus_label(key.replace("_multiplier", ""))
            bonus_text += f"• {label} Multiplier: **{value:.2f}x**\n"
        elif isinstance(value, (int, float)):
            label = get_trait_bonus_label(key)
            if key.endswith("_percent"):
                bonus_text += f"• {label} **{value:+}%**\n"
            else:
                bonus_text += f"• {label} **{value:+}**\n"
    
    return bonus_text if bonus_text else "No bonuses"


async def show_path_entry(ctx, entry, entry_type):
    rarity = entry.get("rarity", "Unknown")
    description = entry.get("description", "No description available.")
    power_rating = get_trait_power_rating(rarity)
    rarity_tier = get_trait_rarity_tier(rarity)
    bonus_text = format_trait_bonuses_detailed(entry)

    embed = discord.Embed(
        title=f"{entry['name']} - {rarity} {entry_type}",
        description=description,
        color=discord.Color.gold() if rarity_tier >= 6 else discord.Color.blue(),
    )
    icon_file = attach_trait_icon(embed, entry)

    embed.add_field(name="Rarity Tier", value=f"{rarity_tier}/9", inline=True)
    embed.add_field(name="Power Rating", value=power_rating, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Effects", value=bonus_text.strip(), inline=False)
    embed.add_field(name="Role", value="Major active growth/combat identity with tradeoffs." if entry_type == "Origin" else "Subtle long-term scaling with no downside.", inline=False)
    embed.set_footer(text=f"{entry_type} ID: {entry.get('id', 'unknown')}")

    if icon_file:
        await ctx.send(embed=embed, file=icon_file)
    else:
        await ctx.send(embed=embed)


@bot.command(name="origin", aliases=["orgin", "ogrin", "origininfo", "orgininfo", "ogrininfo", "trait", "traitinfo"])
async def show_origin(ctx):
    """Show detailed information about your current Origin."""
    user_id = str(ctx.author.id)
    player = get_player(user_id)

    if player is None:
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    origin_name = player.get("origin_name") or player.get("trait_name")
    if not origin_name:
        await ctx.send(
            embed=build_embed(
                "No Origin Selected",
                "You haven't selected an origin yet. Use !create to begin.",
                discord.Color.orange(),
            )
        )
        return

    origin = find_origin_by_name(origin_name)
    if not origin:
        await ctx.send(
            embed=build_embed(
                "Origin Not Found",
                f"Could not find origin '{origin_name}'.",
                discord.Color.red(),
            )
        )
        return

    await show_path_entry(ctx, origin, "Origin")


@bot.command(name="bloodline", aliases=["bloodlineinfo"])
async def show_bloodline(ctx):
    """Show detailed information about your current Bloodline."""
    user_id = str(ctx.author.id)
    player = get_player(user_id)

    if player is None:
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    bloodline_name = player.get("bloodline_name")
    if not bloodline_name:
        await ctx.send(
            embed=build_embed(
                "No Bloodline Selected",
                "You haven't selected a bloodline yet. Use !create to begin.",
                discord.Color.orange(),
            )
        )
        return

    bloodline = find_bloodline_by_name(bloodline_name)
    if not bloodline:
        await ctx.send(
            embed=build_embed(
                "Bloodline Not Found",
                f"Could not find bloodline '{bloodline_name}'.",
                discord.Color.red(),
            )
        )
        return

    await show_path_entry(ctx, bloodline, "Bloodline")


def build_rarity_help_embed(title, entry_type, pool_getter):
    rarity_order = [
        ("Common", "Tier 1", "Most likely"),
        ("Uncommon", "Tier 2", "Slightly rarer"),
        ("Normal", "Tier 3", "Solid pull"),
        ("Great", "Tier 4", "Strong pull"),
        ("Amazing", "Tier 5", "Rare multi-stat pull"),
        ("Legendary", "Tier 6", "High-end path"),
        ("Celestial", "Tier 7", "Elite fate-bending path"),
        ("Godworthy", "Tier 8", "Extremely rare apex-adjacent path"),
        ("Empyrean", "Tier 9", "Highest rarity, almost never seen"),
    ]

    total_weight = sum(RARITY_WEIGHTS.values())
    lines = []
    for rarity, tier, note in rarity_order:
        weight = RARITY_WEIGHTS.get(rarity, 0)
        chance = (weight / total_weight) * 100 if total_weight else 0
        count = len(pool_getter(rarity))
        lines.append(f"**{tier} - {rarity}**: {chance:.3f}% ({count} {entry_type}s)\n- {note}")

    embed = discord.Embed(
        title=title,
        description="From most common to rarest:",
        color=THEME_GOLD,
    )
    embed.add_field(name="Rarity Order", value="\n\n".join(lines), inline=False)
    embed.add_field(
        name="Roll Rules",
        value="Same rarity chances as before. You get 10 rolls during !create.",
        inline=False,
    )
    embed.set_footer(text="Use !create to roll your path")
    return embed


@bot.command(name="originhelp", aliases=["orginhelp", "ogrinhelp", "traithelp"])
async def origin_help(ctx):
    """Explain Origin rarity order and roll odds."""
    embed = build_rarity_help_embed("Origin Rarity Guide", "Origin", get_origins_by_rarity)
    embed.add_field(name="Origin Role", value="Origins are major always-active paths with big stat impact and tradeoffs.", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="bloodlinehelp")
async def bloodline_help(ctx):
    """Explain Bloodline rarity order and roll odds."""
    embed = build_rarity_help_embed("Bloodline Rarity Guide", "Bloodline", get_bloodlines_by_rarity)
    embed.add_field(name="Bloodline Role", value="Bloodlines are subtle long-term passives with no downside, focused on growth, luck, and scaling.", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="use")
async def use_menu(ctx):
    """Show health, level, rank, and future consumable actions."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    player = get_player(user_id)
    game_data = get_player_game_data(user_id)
    if not game_data:
        await ctx.send(embed=build_embed("Data Error", "Could not load your game data.", discord.Color.red()))
        return

    trait_bonuses, _, _ = get_player_trait_bonuses(player)
    total_stats = calculate_total_stats(
        game_data["base_stats"],
        game_data["equipped_weapon"],
        game_data["equipped_armor"],
        trait_bonuses,
    )
    max_health = total_stats.get("hp", 50) + total_stats.get("armor", 0) * 2
    rank_display, _ = calculate_rank_from_stats(total_stats)
    xp = db_get_xp(user_id)
    next_realm_xp = get_xp_for_next_realm(player["realm_stage"])
    progress_pct = int((xp / next_realm_xp) * 100) if next_realm_xp > 0 else 0
    realm_display = get_realm_display(player["realm"], player["realm_stage"])

    embed = discord.Embed(
        title="Use Menu",
        description=build_anime_header("Combat Supplies"),
        color=THEME_DARK,
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    embed.add_field(
        name="Health",
        value=f"`{format_hp_bar(max_health, max_health)}`\nCurrent fights start at full HP.",
        inline=False,
    )
    embed.add_field(name="Level", value=f"{realm_display}\nXP **{xp:,}/{next_realm_xp:,}** ({progress_pct}%)", inline=True)
    embed.add_field(name="Rank", value=rank_display, inline=True)
    embed.add_field(name="Potions", value="No usable potions yet. Healing items will appear here once added.", inline=False)
    embed.set_footer(text="Future: !use potion will heal you when consumables are added")
    await ctx.send(embed=embed)


@bot.command(name="level", aliases=["cult"])
async def show_level(ctx):
    """Show current level/realm and XP progress."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    player = get_player(user_id)
    xp = db_get_xp(user_id)
    next_realm_xp = get_xp_for_next_realm(player["realm_stage"])
    realm_display = get_realm_display(player["realm"], player["realm_stage"])

    # Calculate progress bar
    progress_pct = int((xp / next_realm_xp) * 100) if next_realm_xp > 0 else 0
    progress_bar_length = 20
    filled = int((progress_pct / 100) * progress_bar_length)
    bar = "█" * filled + "░" * (progress_bar_length - filled)

    embed = discord.Embed(title="Cultivation Progress", color=THEME_GOLD)
    embed.add_field(name="Realm", value=realm_display, inline=True)
    embed.add_field(name="Stage", value=str(player["realm_stage"]), inline=True)
    embed.add_field(name="XP", value=f"**{xp:,}** / **{next_realm_xp:,}**", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(
        name="Progress",
        value=f"{bar}  **{progress_pct}%**",
        inline=False,
    )
    embed.set_footer(text="Use !advance to attempt a breakthrough")
    await ctx.send(embed=embed)




@bot.command(name="balance", aliases=["bal"])
async def show_balance(ctx):
    """Show wallet and bank balance."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    wallet = get_wallet(user_id)
    bank = get_bank_balance(user_id)
    total = wallet + bank

    embed = discord.Embed(title="Spirit Treasury", color=THEME_GOLD)
    embed.add_field(name="Wallet", value=f"**{wallet:,}**", inline=True)
    embed.add_field(name="Bank", value=f"**{bank:,}**", inline=True)
    embed.add_field(name="Total", value=f"**{total:,}**", inline=True)
    embed.add_field(name="\u200b", value="Spirit Coins", inline=False)
    embed.set_footer(text="!deposit  |  !withdraw  |  !dep all  |  !with all")
    await ctx.send(embed=embed)


@bot.command(name="deposit", aliases=["dep"])
async def deposit_coins(ctx, amount: str = None):
    """Deposit coins from wallet to bank."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    wallet = get_wallet(user_id)

    if amount is None or amount == "":
        await ctx.send(
            embed=build_embed(
                "Invalid Amount",
                "Use: !deposit <amount> or !deposit all (or !dep <amount>)",
                discord.Color.orange(),
            )
        )
        return

    # Handle "all" keyword
    if amount.lower() == "all":
        amount_int = wallet
    else:
        try:
            amount_int = int(amount)
        except ValueError:
            await ctx.send(
                embed=build_embed(
                    "Invalid Amount",
                    f"'{amount}' is not a valid number. Use: !deposit <amount> or !deposit all",
                    discord.Color.orange(),
                )
            )
            return

    if amount_int <= 0:
        await ctx.send(
            embed=build_embed(
                "Invalid Amount",
                "Amount must be greater than 0.",
                discord.Color.orange(),
            )
        )
        return

    if amount_int > wallet:
        await ctx.send(
            embed=build_embed(
                "Insufficient Funds",
                f"You only have **{wallet:,}** Spirit Coins in your wallet.",
                discord.Color.orange(),
            )
        )
        return

    success = deposit_to_bank(user_id, amount_int)

    if success:
        new_wallet = get_wallet(user_id)
        new_bank = get_bank_balance(user_id)
        await ctx.send(
            embed=build_embed(
                "💳 Deposited Successfully",
                f"**+{amount_int:,}** → Bank\n\nWallet: **{new_wallet:,}** | Bank: **{new_bank:,}**",
                THEME_GOLD,
            )
        )
    else:
        await ctx.send(
            embed=build_embed(
                "Deposit Failed",
                "An error occurred. Please try again.",
                discord.Color.red(),
            )
        )


@bot.command(name="withdraw", aliases=["with"])
async def withdraw_coins(ctx, amount: str = None):
    """Withdraw coins from bank to wallet."""
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(
            embed=build_embed(
                "No Character",
                "You do not have a character yet. Use !create first.",
                discord.Color.orange(),
            )
        )
        return

    bank = get_bank_balance(user_id)

    if amount is None or amount == "":
        await ctx.send(
            embed=build_embed(
                "Invalid Amount",
                "Use: !withdraw <amount> or !withdraw all (or !with <amount>)",
                discord.Color.orange(),
            )
        )
        return

    # Handle "all" keyword
    if amount.lower() == "all":
        amount_int = bank
    else:
        try:
            amount_int = int(amount)
        except ValueError:
            await ctx.send(
                embed=build_embed(
                    "Invalid Amount",
                    f"'{amount}' is not a valid number. Use: !withdraw <amount> or !withdraw all",
                    discord.Color.orange(),
                )
            )
            return

    if amount_int <= 0:
        await ctx.send(
            embed=build_embed(
                "Invalid Amount",
                "Amount must be greater than 0.",
                discord.Color.orange(),
            )
        )
        return

    if amount_int > bank:
        await ctx.send(
            embed=build_embed(
                "Insufficient Funds",
                f"You only have **{bank:,}** Spirit Coins in your bank.",
                discord.Color.orange(),
            )
        )
        return

    success = withdraw_from_bank(user_id, amount_int)

    if success:
        new_wallet = get_wallet(user_id)
        new_bank = get_bank_balance(user_id)
        await ctx.send(
            embed=build_embed(
                "💰 Withdrawn Successfully",
                f"**+{amount_int:,}** → Wallet\n\nWallet: **{new_wallet:,}** | Bank: **{new_bank:,}**",
                THEME_GOLD,
            )
        )
    else:
        await ctx.send(
            embed=build_embed(
                "Withdrawal Failed",
                "An error occurred. Please try again.",
                discord.Color.red(),
            )
        )


def main():
    initialize_database()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()

