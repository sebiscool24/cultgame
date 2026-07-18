import os
import random
import json
import time

import discord
from discord.ext import commands

from data.realms import get_breakthrough_chance, get_next_realm, get_progression_requirement, get_realm_bonus, get_realm_display
from data.starter_items import STARTER_ITEM_RANK_CHANCES, get_item_pool, get_rank_chances
from data.traits import RARITY_WEIGHTS, get_trait_pool
from data.stats_system import calculate_total_stats
from data.game_systems import generate_loot, battle as battle_system, add_xp as add_xp_game, set_cooldown, get_cooldown_remaining
from game_db_functions import (
    add_gear_to_inventory,
    get_player_game_data,
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
    update_player_trait,
    use_starter_roll,
)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set the DISCORD_TOKEN environment variable before running the bot.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# In-memory pending trait rolls. A trait is only saved after pressing Confirm.
PENDING_TRAIT_ROLLS = {}
WEAPON_EMOJI = "⚔️"
ARMOR_EMOJI = "🛡️"
THEME_DARK = discord.Color.from_rgb(30, 30, 50)  # Dark purple-black
THEME_GOLD = discord.Color.from_rgb(218, 165, 32)  # Dark gold
THEME_CRIMSON = discord.Color.from_rgb(139, 35, 69)  # Crimson red
THEME_BRONZE = discord.Color.from_rgb(165, 130, 50)  # Bronze


def gear_emoji(item_type):
    return WEAPON_EMOJI if item_type == "weapon" else ARMOR_EMOJI if item_type == "armor" else "✨"


def get_trait_emoji(trait):
    return trait.get("emoji", "✨")


def get_item_emoji(item):
    return item.get("emoji", gear_emoji(item.get("type")))


def build_embed(title, description, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Cultivation Path | Heavenly Realms")
    return embed


def build_anime_header(title):
    return (
        "```\n"
        "═══════════════════════\n"
        f"  {title}\n"
        "═══════════════════════\n"
        "```"
    )


def format_trait_bonuses(bonuses):
    return ", ".join(
        f"{key.replace('_', ' ')} +{value}%"
        if isinstance(value, int)
        else f"{key.replace('_', ' ')}"
        for key, value in bonuses.items()
    )


def get_selected_starter_names(player):
    rolled_items = json.loads(player.get("starter_items", "[]"))
    inventory_items = player.get("inventory_items", [])
    weapon_id = player.get("starter_weapon")
    armor_id = player.get("starter_armor")

    weapon_name = "None"
    armor_name = "None"

    for item in inventory_items + rolled_items:
        if item.get("id") == weapon_id:
            weapon_name = item.get("name", "None")
        if item.get("id") == armor_id:
            armor_name = item.get("name", "None")

    return weapon_name, armor_name


def get_inventory_emoji_label(item):
    return f"{get_item_emoji(item)} {item['name']} [{item['rank']}]"


def find_trait_by_name(trait_name):
    if not trait_name:
        return None

    for trait in get_trait_pool():
        if trait.get("name") == trait_name:
            return trait
    return None


def roll_random_trait():
    traits = get_trait_pool()
    rarity = random.choices(
        list(RARITY_WEIGHTS.keys()),
        weights=[RARITY_WEIGHTS[r] for r in RARITY_WEIGHTS.keys()],
        k=1,
    )[0]
    filtered = [trait for trait in traits if trait["rarity"] == rarity]
    if not filtered:
        return None
    return random.choice(filtered)


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
        title=f"{get_trait_emoji(trait)} Trait Roll",
        description=build_anime_header("Spirit Trait Resonance"),
        color=THEME_GOLD,
    )
    embed.add_field(name=f"{get_trait_emoji(trait)} Trait", value=f"**{trait['name']}**", inline=True)
    embed.add_field(name="🌈 Rarity", value=trait["rarity"], inline=True)
    embed.add_field(name="🎲 Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="📜 Lore", value=trait["description"], inline=False)
    embed.add_field(name="✨ Blessings", value=format_trait_bonuses(trait["bonuses"]), inline=False)
    embed.set_footer(text=status_line)
    return embed


def build_starter_roll_embed(item, roll_number, rolls_left, status_line):
    stats_text = ", ".join(f"{key}: +{value}" for key, value in item["stats"].items())
    embed = discord.Embed(
        title=f"{get_item_emoji(item)} Starter Item Roll",
        description=build_anime_header("Spirit Armory Summon"),
        color=THEME_DARK,
    )
    embed.add_field(name="🎁 Roll", value=f"{roll_number}/10", inline=True)
    embed.add_field(name=f"{get_item_emoji(item)} Item", value=f"**{item['name']}**", inline=True)
    embed.add_field(name="🏷️ Rank", value=item["rank"], inline=True)
    embed.add_field(name="🧭 Type", value=f"{get_item_emoji(item)} {item['type'].title()}", inline=True)
    embed.add_field(name="🎲 Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="📈 Stats", value=stats_text, inline=False)
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


def get_loadout_items(player):
    starter_candidates = json.loads(player.get("starter_items", "[]"))
    if starter_candidates:
        return starter_candidates, True
    return player.get("inventory_items", []), False


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

    trait_rolls_left = player.get("trait_rolls_left", 0)
    starter_rolls_left = player.get("starter_rolls_left", 0)
    trait_name = player.get("trait_name") or "Unselected"
    trait_entry = find_trait_by_name(player.get("trait_name"))
    if trait_entry:
        trait_name = f"{get_trait_emoji(trait_entry)} {trait_name}"

    starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

    embed = discord.Embed(
        title="🌸 Cultivara Creation Hub",
        description=(
            "```\n"
            "╔══════════════════════════════════════╗\n"
            "║            ✦  ✧  ✦  ✧               ║\n"
            "║                                      ║\n"
            "║             /\\    /\\                ║\n"
            "║            /  \\__/  \\               ║\n"
            "║            \\  /  \\  /               ║\n"
            "║             \\/____\\/                ║\n"
            "║                                      ║\n"
            "║           SAKURA SPIRIT GATE         ║\n"
            "║                                      ║\n"
            "║         NEW CULTIVATOR SETUP         ║\n"
            "║                                      ║\n"
            "╚══════════════════════════════════════╝\n"
            "```\n"
            "\n"
            "**SETUP STEPS:**\n"
            "1️⃣ **Roll Trait** - Choose your spiritual foundation\n"
            "2️⃣ **Roll Starter** - Collect 10 pieces of gear\n"
            "3️⃣ **🔴 FINALIZE CHARACTER 🔴** - Click \"Open Loadout\" below to select 1 weapon + 1 armor and confirm"
        ),
        color=THEME_CRIMSON,
    )
    embed.add_field(name="🧑 Cultivator", value=display_name, inline=True)
    embed.add_field(name="🎲 Trait Rolls Left", value=str(trait_rolls_left), inline=True)
    embed.add_field(name="🎁 Starter Rolls Left", value=str(starter_rolls_left), inline=True)
    embed.add_field(name="✨ Current Trait", value=trait_name, inline=False)
    embed.add_field(name=f"{WEAPON_EMOJI} Equipped Weapon", value=starter_weapon_name, inline=True)
    embed.add_field(name=f"{ARMOR_EMOJI} Equipped Armor", value=starter_armor_name, inline=True)
    embed.set_footer(text="⚠️ You MUST finalize before using combat/loot commands!")
    return embed


def build_create_trait_panel_embed(display_name, trait, rolls_left):
    embed = build_trait_roll_embed(
        trait,
        rolls_left,
        "Tab: Trait Roll | Trait auto-applies each roll. Press Roll Trait to reroll or Back to Hub.",
    )
    embed.title = f"🎲 Trait Tab | {get_trait_emoji(trait)} {display_name}"
    return embed


def build_create_starter_panel_embed(display_name, item, roll_number, rolls_left):
    status = (
        "Tab: Starter Roll | All rolls complete. Open Loadout next."
        if rolls_left <= 0
        else "Tab: Starter Roll | Use Roll Starter again, or Back to Hub."
    )
    embed = build_starter_roll_embed(item, roll_number, rolls_left, status)
    embed.title = f"🎁 Starter Tab | {display_name}"
    return embed


def build_create_loadout_panel_embed(display_name, rolled_items, starter_finalize, starter_weapon_name, starter_armor_name):
    lines = []
    for index, item in enumerate(rolled_items, 1):
        stats_text = ", ".join(f"{key}: +{value}" for key, value in item.get("stats", {}).items())
        lines.append(f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}] - {stats_text}")

    embed = discord.Embed(
        title="🧰 Loadout Tab | Spirit Equipment",
        description=build_anime_header("Equipment Selection"),
        color=THEME_DARK,
    )
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="🗃️ Items", value=items_text, inline=False)
    embed.add_field(name=f"{WEAPON_EMOJI} Current Weapon", value=starter_weapon_name, inline=True)
    embed.add_field(name=f"{ARMOR_EMOJI} Current Armor", value=starter_armor_name, inline=True)
    embed.set_footer(
        text=(
            "Finalize your starter weapon + armor in this panel."
            if starter_finalize
            else "Swap your equipped weapon + armor in this panel."
        )
    )
    return embed


class CreateJourneyView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=900)
        self.author_id = author_id
        self.current_trait = None
        self.mode = "hub"
        self.current_loadout_items = []
        self.current_starter_finalize = False
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self._set_hub_buttons()

    async def _ensure_owner(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel belongs to a different player.", ephemeral=True)
            return False
        return True

    def _set_hub_buttons(self):
        self.clear_items()

        roll_trait_btn = discord.ui.Button(label="Roll Trait", emoji="🎲", style=discord.ButtonStyle.primary)
        roll_trait_btn.callback = self.roll_trait_button
        self.add_item(roll_trait_btn)

        roll_starter_btn = discord.ui.Button(label="Roll Starter", emoji="🎁", style=discord.ButtonStyle.success)
        roll_starter_btn.callback = self.roll_starter_button
        self.add_item(roll_starter_btn)

        open_loadout_btn = discord.ui.Button(label="Finalize Character ✅", emoji="⚔️", style=discord.ButtonStyle.danger)
        open_loadout_btn.callback = self.open_loadout_button
        self.add_item(open_loadout_btn)

    def _set_trait_buttons(self):
        self.clear_items()

        reroll_trait_btn = discord.ui.Button(label="Roll Trait", emoji="🎲", style=discord.ButtonStyle.primary)
        reroll_trait_btn.callback = self.roll_trait_button
        self.add_item(reroll_trait_btn)

        back_btn = discord.ui.Button(label="Back To Hub", emoji="🏠", style=discord.ButtonStyle.secondary)
        back_btn.callback = self.back_to_hub_button
        self.add_item(back_btn)

    def _set_starter_buttons(self):
        self.clear_items()

        reroll_starter_btn = discord.ui.Button(label="Roll Starter", emoji="🎁", style=discord.ButtonStyle.success)
        reroll_starter_btn.callback = self.roll_starter_button
        self.add_item(reroll_starter_btn)

        back_btn = discord.ui.Button(label="Back To Hub", emoji="🏠", style=discord.ButtonStyle.secondary)
        back_btn.callback = self.back_to_hub_button
        self.add_item(back_btn)

    def _set_loadout_buttons(self):
        self.clear_items()

        weapon_options = []
        armor_options = []
        for index, item in enumerate(self.current_loadout_items, 1):
            option = discord.SelectOption(
                label=f"#{index} {item['name']} [{item['rank']}]",
                value=str(index),
                description=item.get("type", "unknown").title(),
            )
            if item.get("type") == "weapon":
                weapon_options.append(option)
            elif item.get("type") == "armor":
                armor_options.append(option)

        if weapon_options:
            weapon_select = discord.ui.Select(
                placeholder="Choose your final weapon" if self.current_starter_finalize else "Choose weapon",
                min_values=1,
                max_values=1,
                options=weapon_options,
            )
            weapon_select.callback = self.select_weapon_in_panel
            self.add_item(weapon_select)

        if armor_options:
            armor_select = discord.ui.Select(
                placeholder="Choose your final armor" if self.current_starter_finalize else "Choose armor",
                min_values=1,
                max_values=1,
                options=armor_options,
            )
            armor_select.callback = self.select_armor_in_panel
            self.add_item(armor_select)

        confirm_btn = discord.ui.Button(label="Equip Loadout", emoji="✅", style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm_loadout_in_panel
        self.add_item(confirm_btn)

        back_btn = discord.ui.Button(label="Back To Hub", emoji="🏠", style=discord.ButtonStyle.secondary)
        back_btn.callback = self.back_to_hub_button
        self.add_item(back_btn)

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
                embed=build_embed("No Trait Rolls", "You have no trait rolls left.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        trait = roll_random_trait()
        if trait is None:
            await interaction.response.send_message(
                embed=build_embed("Trait Roll Failed", "No trait was found for that rarity.", discord.Color.red()),
                ephemeral=True,
            )
            return

        update_player_trait(user_id, trait["id"], trait["name"])
        PENDING_TRAIT_ROLLS.pop(user_id, None)
        self.current_trait = trait
        self.mode = "trait"
        self._set_trait_buttons()
        rolls_left = get_trait_rolls_left(user_id)
        await interaction.response.edit_message(
            embed=build_create_trait_panel_embed(interaction.user.display_name, trait, rolls_left),
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

        item, roll_number, rolls_left = roll_starter_candidate(user_id)
        if item is None:
            self.mode = "starter"
            self._set_starter_buttons()
            await interaction.response.edit_message(
                embed=build_embed(
                    "🎁 Starter Tab Complete",
                    "You have no starter rolls left. Press Back To Hub, then Open Loadout to finalize 1 weapon and 1 armor.",
                    discord.Color.orange(),
                ),
                view=self,
            )
            return

        self.mode = "starter"
        self._set_starter_buttons()
        await interaction.response.edit_message(
            embed=build_create_starter_panel_embed(interaction.user.display_name, item, roll_number, rolls_left),
            view=self,
        )

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

        rolled_items, starter_finalize = get_loadout_items(player)
        if not rolled_items:
            await interaction.response.send_message(
                embed=build_embed("Loadout ✨", "You do not have any items to equip yet.", discord.Color.orange()),
                ephemeral=True,
            )
            return

        starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

        self.mode = "loadout"
        self.current_loadout_items = rolled_items
        self.current_starter_finalize = starter_finalize
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self._set_loadout_buttons()

        await interaction.response.edit_message(
            embed=build_create_loadout_panel_embed(
                interaction.user.display_name,
                rolled_items,
                starter_finalize,
                starter_weapon_name,
                starter_armor_name,
            ),
            view=self,
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

        self.mode = "hub"
        self.current_loadout_items = []
        self.current_starter_finalize = False
        self.selected_weapon_roll = None
        self.selected_armor_roll = None
        self._set_hub_buttons()

        help_text = (
            f"{WEAPON_EMOJI} Weapon: {weapon_item.get('name')} [{weapon_item.get('rank')}]\n"
            f"{ARMOR_EMOJI} Armor: {armor_item.get('name')} [{armor_item.get('rank')}]\n\n"
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
        await interaction.response.edit_message(embed=refreshed, view=self)


class TraitRollView(discord.ui.View):
    def __init__(self, author_id, trait):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.trait = trait

    @discord.ui.button(label="Lock Trait", style=discord.ButtonStyle.success)
    async def lock_trait(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This button is not for your roll.", ephemeral=True)
            return

        update_player_trait(str(self.author_id), self.trait["id"], self.trait["name"])
        PENDING_TRAIT_ROLLS.pop(str(self.author_id), None)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Trait locked in.",
            embed=build_trait_roll_embed(self.trait, get_trait_rolls_left(str(self.author_id)), "Locked in successfully."),
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
                "You have no trait rolls left. Use Lock Trait to keep your current trait.",
                ephemeral=True,
            )
            return

        if not spend_trait_roll(user_id):
            await interaction.response.send_message(
                "You have no trait rolls left. Use Lock Trait to keep your current trait.",
                ephemeral=True,
            )
            return

        new_trait = roll_random_trait()
        if new_trait is None:
            await interaction.response.send_message("No trait was found for the roll.", ephemeral=True)
            return

        self.trait = new_trait
        PENDING_TRAIT_ROLLS[user_id] = new_trait

        rolls_left = get_trait_rolls_left(user_id)

        await interaction.response.edit_message(
            content=None,
            embed=build_trait_roll_embed(new_trait, rolls_left, "Use Lock Trait to keep this roll, or Roll Again."),
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
                label=f"#{index} {item['name']} [{item['rank']}]",
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

        for child in self.children:
            child.disabled = True

        loadout_message = (
            "Starter loadout confirmed via buttons.\n"
            if self.is_starter_finalize
            else "Loadout updated.\n"
        )

        await interaction.response.edit_message(
            content=loadout_message
            + f"Weapon: {weapon_item.get('name')} [{weapon_item.get('rank')}]\n"
            + f"Armor: {armor_item.get('name')} [{armor_item.get('rank')}]",
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
        title="📖 Cultivara Command Grimoire",
        description=build_anime_header("Command Guide"),
        color=THEME_CRIMSON,
    )
    embed.add_field(name="🌸 Core", value="!ping\n!help\n!profile\n!reset", inline=True)
    embed.add_field(name="🧿 Traits", value="!rolltrait\nTrait icons follow each roll", inline=True)
    embed.add_field(name="⚒️ Starter Gear", value=f"!rollstarter\n!loadout\n!inv\n!inventory\n!choosestarter <weapon_roll> <armor_roll>\n{WEAPON_EMOJI} weapon / {ARMOR_EMOJI} armor swap later", inline=True)
    embed.add_field(name="🌠 Progression", value="!advance", inline=True)
    embed.set_footer(text="Tip: Use the creation hub buttons to avoid retyping commands.")
    await ctx.send(embed=embed)


@bot.command(name="create")
async def create_character(ctx):
    user_id = str(ctx.author.id)

    if player_exists(user_id):
        await ctx.send(embed=build_embed("Character Exists ✨", "You already have a character. Use !profile to view it.", discord.Color.orange()))
        return

    created = create_player(user_id, ctx.author.display_name)
    if not created:
        await ctx.send(embed=build_embed("Create Failed ✨", "Could not create your character. Please try again.", discord.Color.red()))
        return

    await ctx.send(
        embed=build_embed(
            "Character Created ✨",
            "You are ready to begin cultivation. Open the setup panel below and roll everything from one place.",
            discord.Color.green(),
        )
    )

    await ctx.send(
        embed=build_create_journey_embed(user_id, ctx.author.display_name),
        view=CreateJourneyView(ctx.author.id),
    )


@bot.command(name="rolltrait")
async def roll_trait(ctx):
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    if get_trait_rolls_left(user_id) <= 0:
        await ctx.send(embed=build_embed("No Trait Rolls", "You have no trait rolls left.", discord.Color.orange()))
        return

    if not spend_trait_roll(user_id):
        await ctx.send(embed=build_embed("No Trait Rolls", "You have no trait rolls left.", discord.Color.orange()))
        return

    trait = roll_random_trait()
    if trait is None:
        await ctx.send(embed=build_embed("Trait Roll Failed", "No trait was found for that rarity.", discord.Color.red()))
        return

    PENDING_TRAIT_ROLLS[user_id] = trait
    rolls_left = get_trait_rolls_left(user_id)

    await ctx.send(
        embed=build_trait_roll_embed(trait, rolls_left, "Use Lock Trait to keep this roll, or Roll Again."),
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


@bot.command(name="rollstarter")
async def roll_starter(ctx):
    user_id = str(ctx.author.id)

    if not player_exists(user_id):
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    item, roll_number, rolls_left = roll_starter_candidate(user_id)
    if item is None:
        await ctx.send(
            embed=build_embed(
                "Starter Rolls Complete ✨",
                "You have no starter rolls left. Use !loadout to finalize 1 weapon and 1 armor.",
                discord.Color.orange(),
            )
        )
        return

    await ctx.send(
        embed=build_starter_roll_embed(
            item,
            roll_number,
            rolls_left,
            "All 10 rolls complete. Use !loadout to finalize 1 weapon + 1 armor."
            if rolls_left <= 0
            else "Press Roll Again to continue.",
        ),
        view=StarterRollView(ctx.author.id),
    )


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
        lines.append(f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}] - {stats_text}")

    starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

    embed = discord.Embed(
        title="🧰 Starter Loadout Candidates" if starter_finalize else "🧰 Loadout",
        description=build_anime_header("Spirit Equipment Selection"),
        color=THEME_DARK,
    )
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="🗃️ Items", value=items_text, inline=False)
    embed.add_field(name=f"{WEAPON_EMOJI} Current Weapon", value=starter_weapon_name, inline=True)
    embed.add_field(name=f"{ARMOR_EMOJI} Current Armor", value=starter_armor_name, inline=True)
    embed.set_footer(text="Keep exactly 1 weapon + 1 armor. Use dropdowns below or !choosestarter <weapon_roll> <armor_roll>.")
    await ctx.send(embed=embed, view=StarterSelectView(ctx.author.id, rolled_items, starter_finalize))


@bot.command(name="inv", aliases=["inventory"])
async def inventory_view(ctx):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    inventory_items = player.get("inventory_items", [])
    
    # Get gear inventory from game systems
    game_data = get_player_game_data(str(ctx.author.id))
    gear_inventory = game_data.get("gear_inventory", []) if game_data else []
    
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
        lines.append(f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}] - {stats_text}")

    embed = discord.Embed(title="� Spiritual Armory", description=build_anime_header("Acquired Treasures"), color=THEME_DARK)
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="📿 Artifacts", value=items_text, inline=False)
    embed.set_footer(text=f"Use !loadout to equip {WEAPON_EMOJI} weapon and {ARMOR_EMOJI} armor for battle")
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

    await ctx.send(
        embed=build_embed(
            "Loadout Confirmed ✨",
            f"{WEAPON_EMOJI} Weapon: {weapon_item.get('name')} [{weapon_item.get('rank')}]\n"
            f"{ARMOR_EMOJI} Armor: {armor_item.get('name')} [{armor_item.get('rank')}]",
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
    get_cooldown_remaining,
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
    
    trait_bonuses = {}
    if player["trait_name"]:
        trait_entry = find_trait_by_name(player["trait_name"])
        if trait_entry:
            rarity = trait_entry.get("rarity", "Common")
            trait_bonuses = get_trait_bonuses(rarity)

    total_stats = calculate_total_stats(base_stats, equipped_weapon, equipped_armor, trait_bonuses)
    rank_display, rank_letter = calculate_rank_from_stats(total_stats)

    realm_display = get_realm_display(player["realm"], player["realm_stage"])
    trait_display = player["trait_name"] or "None"
    if player["trait_name"]:
        trait_entry = find_trait_by_name(player["trait_name"])
        if trait_entry:
            trait_display = f"{get_trait_emoji(trait_entry)} {trait_entry['name']} ({trait_entry['rarity']})"

    # Build profile embed with user avatar
    embed = discord.Embed(
        title=f"🏯 Cultivator Profile",
        description=build_anime_header("Your Cultivation Status"),
        color=THEME_DARK,
    )
    
    # Add user avatar in top right
    embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    
    # Status Legend Section
    embed.add_field(
        name="📊 Status Legend",
        value=f"Discord: {ctx.author.mention}\n🌟 Name: **{player['character_name']}**",
        inline=False
    )
    
    # Realm & Cultivation Section
    xp = db_get_xp(user_id)
    next_realm_xp = get_xp_for_next_realm(player["realm_stage"])
    embed.add_field(name="🌌 Realm", value=realm_display, inline=True)
    embed.add_field(name="🧿 Cultivation", value=f"{xp:,}/{next_realm_xp:,} XP\n{int((xp/next_realm_xp)*100)}% Progress", inline=True)
    
    # Stats in grid format
    embed.add_field(
        name="⚔️ Stats - " + rank_display,
        value=(
            f"⚔️ **DMG**: {total_stats['damage']} "
            f"❤️ **HP**: {total_stats['hp']}\n"
            f"🛡️ **DEF**: {total_stats['defense']} "
            f"⚡ **SPD**: {total_stats['speed']}\n"
            f"🍀 **LCK**: {total_stats['luck']} "
            f"🗡️ **ARM**: {total_stats['armor']}"
        ),
        inline=False
    )
    
    # Breakthrough & Status
    embed.add_field(name="💫 Breakthrough", value="Ready", inline=True)
    embed.add_field(name="❤️ Health", value="Perfect", inline=True)
    embed.add_field(name="🚫 Status", value="None", inline=True)
    
    # Equipment Section
    weapon_name = "None"
    weapon_stats = ""
    armor_name = "None"
    armor_stats = ""
    
    if equipped_weapon:
        weapon_name = f"{equipped_weapon.get('rank')} {equipped_weapon.get('name')}"
        weapon_stats = " - " + ", ".join(f"{k}: +{v}" for k, v in equipped_weapon.get("stats", {}).items())
    if equipped_armor:
        armor_name = f"{equipped_armor.get('rank')} {equipped_armor.get('name')}"
        armor_stats = " - " + ", ".join(f"{k}: +{v}" for k, v in equipped_armor.get("stats", {}).items())
    
    embed.add_field(
        name="🛠️ Equipment",
        value=f"{WEAPON_EMOJI} **Weapon**: {weapon_name}{weapon_stats}\n{ARMOR_EMOJI} **Armor**: {armor_name}{armor_stats}",
        inline=False
    )
    
    # Trait Section
    embed.add_field(name="✨ Trait", value=trait_display, inline=False)
    
    # Footer with action hints
    embed.set_footer(text="Use !inv to view inventory | !loadout to equip items | !cd for cooldowns")
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
    
    await ctx.send(
        embed=build_embed(
            "⛩️ Meditation Complete",
            f"**+{xp_earned} Spiritual Power** | **+{currency_earned}** Spirit Coins\n\nResources Absorbed:\n{loot_text}{level_up_msg}",
            THEME_GOLD,
        )
    )


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
    
    await ctx.send(
        embed=build_embed(
            "⛩️ Cultivation Trial Complete",
            f"**+{xp_earned} Spiritual Power** | **+{currency_earned}** Spirit Coins\n\nCombat Spoils:\n{loot_text}{level_up_msg}",
            THEME_GOLD,
        )
    )


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
    player_stats = calculate_total_stats(
        game_data["base_stats"],
        game_data["equipped_weapon"],
        game_data["equipped_armor"],
    )

    # Conduct battle
    won, xp_earned, battle_log, loot, currency_earned = battle_system(player_stats, "normal")

    # If won, add rewards
    if won:
        if loot:
            add_gear_to_inventory(user_id, [loot])
        
        add_wallet_currency(user_id, currency_earned)

        player = get_player(user_id)
        xp = get_xp(user_id)
        new_xp, new_realm, leveled_up = add_xp_game(xp, player["realm_stage"], xp_earned)
        set_xp(user_id, new_xp)

        if leveled_up and new_realm != player["realm_stage"]:
            update_player_realm(user_id, player["realm"], new_realm)

        level_up_msg = f"\n✨ **Realm Up!** Now at stage {new_realm}!" if leveled_up else ""
        loot_msg = f"\n� **Divine Treasures:** {loot['rank']} {loot['type'].title()}" if loot else ""

        await ctx.send(
            embed=build_embed(
                "⛩️ Opponent Defeated",
                f"{battle_log}\n\n**+{xp_earned} Spiritual Power** | **+{currency_earned}** Spirit Coins{loot_msg}{level_up_msg}",
                THEME_GOLD,
            )
        )
    else:
        await ctx.send(
            embed=build_embed(
                "🌪️ Defeated",
                battle_log,
                THEME_CRIMSON,
            )
        )

    # Set cooldown (90 seconds)
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
    player_stats = calculate_total_stats(
        game_data["base_stats"],
        game_data["equipped_weapon"],
        game_data["equipped_armor"],
    )

    # Conduct raid
    won, xp_earned, battle_log, loot, currency_earned = battle_system(player_stats, "raid")

    # If won, add rewards
    if won:
        if loot:
            add_gear_to_inventory(user_id, [loot])
        
        add_wallet_currency(user_id, currency_earned)

        player = get_player(user_id)
        xp = get_xp(user_id)
        new_xp, new_realm, leveled_up = add_xp_game(xp, player["realm_stage"], xp_earned)
        set_xp(user_id, new_xp)

        if leveled_up and new_realm != player["realm_stage"]:
            update_player_realm(user_id, player["realm"], new_realm)

        level_up_msg = f"\n✨ **Realm Up!** Now at stage {new_realm}!" if leveled_up else ""
        loot_msg = f"\n� **Legendary Treasures:** {loot['rank']} {loot['type'].title()}" if loot else ""

        await ctx.send(
            embed=build_embed(
                "⚡ Calamity Subdued",
                f"{battle_log}\n\n**+{xp_earned} Spiritual Power** | **+{currency_earned}** Spirit Coins{loot_msg}{level_up_msg}",
                THEME_GOLD,
            )
        )
    else:
        await ctx.send(
            embed=build_embed(
                "☠️ Overwhelmed by Calamity",
                battle_log,
                THEME_CRIMSON,
            )
        )

    # Set cooldown (180 seconds)
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
                cooldown_info.append(f"**{cmd.title()}**: ✅ Ready")
        else:
            cooldown_info.append(f"**{cmd.title()}**: ✅ Ready")
    
    embed = discord.Embed(
        title="⏳ Action Cooldowns",
        description=build_anime_header("Cultivation Timer"),
        color=THEME_DARK,
    )
    embed.add_field(
        name="Current Status",
        value="\n".join(cooldown_info),
        inline=False,
    )
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
    }
    return tiers.get(rarity, 0)


def format_trait_bonuses_detailed(trait):
    """Format complete trait information for display."""
    bonuses = trait.get("bonuses", {})
    bonus_text = ""
    
    for key, value in bonuses.items():
        if isinstance(value, bool):
            if value:
                label = key.replace("_", " ").title()
                bonus_text += f"• {label}\n"
        elif key.endswith("_multiplier") and isinstance(value, (int, float)):
            label = key.replace("_multiplier", "").replace("_", " ").title()
            bonus_text += f"• {label} Multiplier: **{value:.2f}x**\n"
        elif isinstance(value, (int, float)):
            label = key.replace("_percent", "").replace("_", " ").title()
            if key.endswith("_percent"):
                bonus_text += f"• {label} +**{value}%**\n"
            else:
                bonus_text += f"• {label} +**{value}**\n"
    
    return bonus_text if bonus_text else "No bonuses"


@bot.command(name="trait")
async def show_trait(ctx):
    """Show detailed information about your current trait."""
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

    trait_name = player.get("trait_name")
    if not trait_name:
        await ctx.send(
            embed=build_embed(
                "No Trait Selected",
                "You haven't selected a trait yet. Use !rolltrait to get started.",
                discord.Color.orange(),
            )
        )
        return

    # Find trait in pool
    trait = None
    for t in get_trait_pool():
        if t.get("name") == trait_name:
            trait = t
            break

    if not trait:
        await ctx.send(
            embed=build_embed(
                "Trait Not Found",
                f"Could not find trait '{trait_name}'.",
                discord.Color.red(),
            )
        )
        return

    # Format trait information
    rarity = trait.get("rarity", "Unknown")
    emoji = trait.get("emoji", "✨")
    description = trait.get("description", "No description available.")
    power_rating = get_trait_power_rating(rarity)
    rarity_tier = get_trait_rarity_tier(rarity)
    bonus_text = format_trait_bonuses_detailed(trait)

    # Build embed
    embed = discord.Embed(
        title=f"{emoji} {trait_name} - {rarity} Trait",
        description=description,
        color=discord.Color.gold() if rarity_tier >= 6 else discord.Color.blue(),
    )

    embed.add_field(
        name="════════════════════════════",
        value=f"**Rarity Level:** {rarity_tier}/8\n**Power Rating:** {power_rating}",
        inline=False,
    )

    embed.add_field(name="📊 Base Bonuses", value=bonus_text.strip(), inline=False)

    # Trait value assessment
    if rarity in ("Godworthy", "Celestial"):
        assessment = "🔥 **EXCEPTIONAL** - This is an elite-tier trait with immense power!"
    elif rarity in ("Legendary", "Amazing"):
        assessment = "⚡ **EXCELLENT** - A powerful trait with strong advantages!"
    elif rarity in ("Great",):
        assessment = "✨ **VERY GOOD** - A solid trait with notable benefits!"
    elif rarity in ("Normal",):
        assessment = "👍 **DECENT** - A respectable trait for your journey."
    elif rarity in ("Uncommon",):
        assessment = "😐 **MODEST** - Basic benefits to aid your cultivation."
    else:
        assessment = "🤷 **BASIC** - A humble trait, but every journey starts somewhere!"

    embed.add_field(name="════════════════════════════", value=assessment, inline=False)
    embed.set_footer(text=f"Trait ID: {trait.get('id', 'unknown')}")

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

    embed = discord.Embed(
        title="📈 Cultivation Progress",
        description=build_anime_header("Ascendance Path"),
        color=THEME_GOLD,
    )
    embed.add_field(name="🌌 Current Realm", value=realm_display, inline=True)
    embed.add_field(name="🎯 Realm Stage", value=str(player["realm_stage"]), inline=True)
    embed.add_field(name="⭐ XP Progress", value=f"**{xp}** / **{next_realm_xp}**", inline=True)
    embed.add_field(
        name="📊 Progress Bar",
        value=f"{bar}\n**{progress_pct}%** to next realm",
        inline=False,
    )
    embed.set_footer(text="Push beyond your limits | Ascend the heavenly realms")
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

    embed = discord.Embed(
        title="💰 Spirit Treasury",
        description=build_anime_header("Wealth Status"),
        color=THEME_GOLD,
    )
    embed.add_field(name="👜 Wallet", value=f"**{wallet:,}** Spirit Coins", inline=True)
    embed.add_field(name="🏦 Bank", value=f"**{bank:,}** Spirit Coins", inline=True)
    embed.add_field(name="💎 Total", value=f"**{total:,}** Spirit Coins", inline=True)
    embed.set_footer(text="Use !deposit to save coins | !withdraw to retrieve coins")
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

