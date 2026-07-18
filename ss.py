import os
import random
import json

import discord
from discord.ext import commands

from data.realms import get_breakthrough_chance, get_next_realm, get_progression_requirement, get_realm_bonus, get_realm_display, get_realm_index
from data.starter_items import STARTER_ITEM_RANK_CHANCES, get_item_pool, get_rank_chances
from data.traits import RARITY_WEIGHTS, get_trait_pool
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

CORE_STATS = ("dmg", "qi_cultivation", "luck", "hp")

RANK_POWER = {
    "S+": 26,
    "S": 24,
    "S-": 22,
    "A+": 20,
    "A": 18,
    "A-": 16,
    "B+": 13,
    "B": 11,
    "B-": 9,
    "C+": 7,
    "C": 6,
    "C-": 5,
    "D+": 4,
    "D": 3,
    "D-": 2,
    "E": 1,
    "F": 0,
}

RARITY_BASE_COMBAT_BONUS = {
    "Common": {"dmg_percent": 2, "luck_percent": 1, "qi_cultivation_percent": 1},
    "Uncommon": {"dmg_percent": 4, "luck_percent": 2, "qi_cultivation_percent": 2},
    "Normal": {"dmg_percent": 6, "luck_percent": 3, "qi_cultivation_percent": 3},
    "Great": {"dmg_percent": 8, "luck_percent": 4, "qi_cultivation_percent": 4, "hp_percent": 3},
    "Amazing": {"dmg_percent": 11, "luck_percent": 5, "qi_cultivation_percent": 6, "hp_percent": 6},
    "Legendary": {"dmg_percent": 14, "luck_percent": 6, "qi_cultivation_percent": 8, "hp_percent": 8, "dmg_multiplier": 1.08},
    "Celestial": {"dmg_percent": 20, "luck_percent": 10, "qi_cultivation_percent": 13, "hp_percent": 12, "lifesteal_percent": 7, "dmg_multiplier": 1.18},
    "Godworthy": {"dmg_percent": 28, "luck_percent": 14, "qi_cultivation_percent": 17, "hp_percent": 16, "lifesteal_percent": 12, "dmg_multiplier": 1.28},
}

TRAIT_UNIQUE_EFFECTS = {
    # Celestial - Super powerful unique effects
    "celestial_01": {"effect_label": "Starbound Conversion", "qi_to_dmg_percent": 15, "description": "Every 100 Qi converts to +15% damage"},
    "celestial_02": {"effect_label": "Guardian Constellation", "damage_taken_reduction_percent": 12, "shield_regen_hp_percent": 8, "description": "Reduce damage by 12% and regenerate shield"},
    "celestial_03": {"effect_label": "Judgement Arc", "execute_threshold_percent": 10, "instant_kill_chance_percent": 3, "description": "Execute enemies below 10% HP with 3% instant-kill chance"},
    "celestial_04": {"effect_label": "Moonstep Shift", "first_strike_dodge_percent": 22, "next_turn_crit_percent": 15, "description": "First turn: 22% dodge, 15% bonus crit"},
    "celestial_05": {"effect_label": "Solar Overload", "burst_dmg_multiplier": 2.0, "cooldown_turns": 4, "description": "Every 4 turns, deal 2x damage"},
    "celestial_06": {"effect_label": "Void Carapace", "shield_percent_hp": 18, "shield_damage_reflect_percent": 25, "description": "18% HP shield that reflects 25% damage"},
    "celestial_07": {"effect_label": "Eclipse Tempo", "combo_ramp_percent": 15, "max_combo_turns": 10, "description": "Ramp +15% damage per turn, max 10 turns"},
    "celestial_08": {"effect_label": "Heaven Temper", "post_breakthrough_hp_percent": 20, "post_breakthrough_all_stats_percent": 8, "description": "After breakthrough: +20% HP, +8% all stats"},
    "celestial_09": {"effect_label": "Dawn Execution", "opening_hit_crit_percent": 25, "opening_hit_crit_dmg_percent": 50, "description": "First hit: 25% crit with +50% crit damage"},
    "celestial_10": {"effect_label": "Mirrored Guard", "counter_dmg_percent": 18, "counter_heal_percent": 10, "description": "Counter 18% damage, heal 10% of counter damage"},
    "celestial_11": {"effect_label": "Ember Debt", "lifesteal_to_qi_percent": 50, "description": "Convert 50% of lifesteal into Qi gain"},
    "celestial_12": {"effect_label": "Endless Horizon", "hp_regen_percent": 7, "regen_scales_with_cultivation": True, "description": "Regen 7% HP per turn, scales with Cultivation"},
    "celestial_13": {"effect_label": "Halo Fracture", "armor_break_percent": 15, "enemy_defense_reduction_percent": 20, "description": "Break armor and reduce enemy defense by 20%"},
    "celestial_14": {"effect_label": "Night Sovereignty", "luck_to_dmg_percent": 28, "luck_to_crit_percent": 12, "description": "Convert 28% Luck to damage, 12% to crit"},
    "celestial_15": {"effect_label": "Gatebreaker", "breakthrough_chance_bonus_percent": 12, "breakthrough_reward_bonus_percent": 25, "description": "+12% breakthrough chance, +25% rewards"},

    # Legendary - Cool but balanced
    "legendary_01": {"effect_label": "Mirror Reflection", "dodge_reflects_dmg_percent": 15, "description": "When you dodge, reflect 15% damage back"},
    "legendary_02": {"effect_label": "Ascension Path", "xp_gain_bonus_percent": 10, "breakthrough_speed_percent": 8, "description": "+10% XP, +8% breakthrough speed"},
    "legendary_03": {"effect_label": "Dragon's Wrath", "crit_damage_percent": 35, "description": "Critical hits deal 35% bonus damage"},
    "legendary_04": {"effect_label": "World Anchor", "stability_bonus": True, "chance_negate_debuff_percent": 12, "description": "12% chance to negate enemy debuffs"},
    "legendary_05": {"effect_label": "Storm's Edge", "attack_speed_percent": 12, "description": "Attack 12% faster"},
    "legendary_06": {"effect_label": "Celestial Path", "cultivation_speed_bonus_percent": 10, "description": "+10% cultivation speed"},
    "legendary_07": {"effect_label": "Eternal Flame", "lifesteal_percent": 10, "description": "Recover 10% of damage as health"},
    "legendary_08": {"effect_label": "Crit Master", "critical_chance_percent": 12, "description": "+12% chance for critical hits"},
    "legendary_09": {"effect_label": "Depth Charge", "next_hit_bonus_dmg_percent": 20, "description": "Next hit after combo deals +20% damage"},
    "legendary_10": {"effect_label": "Defender's Resolve", "damage_reduction_percent": 8, "description": "Reduce all damage by 8%"},

    # Amazing - Nice effects but modest
    "amazing_01": {"effect_label": "Eclipse Mind", "dodge_chance_bonus_percent": 8, "description": "+8% dodge chance"},
    "amazing_02": {"effect_label": "Hunger", "qi_gain_bonus_percent": 7, "description": "+7% Qi gain"},
    "amazing_03": {"effect_label": "Fortress", "defense_bonus_percent": 8, "description": "+8% defense"},
    "amazing_04": {"effect_label": "Thunder Rush", "attack_bonus_percent": 8, "description": "+8% attack damage"},
    "amazing_05": {"effect_label": "Veil Walker", "evasion_bonus_percent": 8, "description": "+8% evasion"},
    "amazing_06": {"effect_label": "Growth Surge", "cultivation_bonus_percent": 8, "description": "+8% cultivation growth"},
    "amazing_07": {"effect_label": "Golden Touch", "luck_bonus_percent": 8, "description": "+8% luck"},
    "amazing_08": {"effect_label": "Life Force", "hp_bonus_percent": 8, "description": "+8% maximum HP"},

    # Godworthy - Absolutely broken
    "godworthy_01": {"effect_label": "Mythic Mutation", "trait_evolution_tier": 1, "dmg_multiplier": 1.35, "all_stats_percent": 12, "description": "Trait can evolve. +35% damage multiplier, +12% all stats"},
    "godworthy_02": {"effect_label": "Epoch Pulse", "lifesteal_percent": 18, "hp_regen_percent": 10, "regen_on_kill_percent": 50, "description": "18% lifesteal, 10% regen, restore 50% HP on kill"},
    "godworthy_03": {"effect_label": "Abyss Tribute", "kill_refund_qi_percent": 25, "dmg_multiplier": 1.32, "instant_kill_threshold_percent": 5, "description": "Refund 25% Qi on kill, +32% damage, 5% instant-kill threshold"},
    "godworthy_04": {"effect_label": "Worldroot Domain", "aura_hp_percent": 15, "damage_taken_reduction_percent": 14, "aura_allies_defense_percent": 10, "description": "+15% aura HP, -14% damage taken, aura gives allies +10% defense"},
    "godworthy_05": {"effect_label": "Astral Authority", "all_stats_percent": 13, "dmg_multiplier": 1.34, "description": "+13% ALL stats, +34% damage multiplier"},
    "godworthy_06": {"effect_label": "Primordial Echo", "combo_ramp_percent": 22, "qi_to_dmg_percent": 18, "cooldown_refund_percent": 15, "description": "Combo ramps to +22%, convert 18% Qi to damage, 15% cooldown refund"},
    "godworthy_07": {"effect_label": "Bloodline Sovereign", "lifesteal_percent": 20, "crit_dmg_percent": 40, "bleed_on_crit_percent": 25, "description": "20% lifesteal, +40% crit damage, bleed on 25% of crits"},
    "godworthy_08": {"effect_label": "Mandate of Heaven", "breakthrough_chance_bonus_percent": 15, "dmg_multiplier": 1.33, "enemies_crit_resistance_reduction": 20, "description": "+15% breakthrough chance, +33% damage, reduce enemy crit resist by 20%"},
    "godworthy_09": {"effect_label": "Rune of Origin", "skill_echo_percent": 25, "qi_cultivation_percent": 25, "skill_cooldown_reduction_percent": 20, "description": "Skills echo 25%, +25% cultivation, -20% cooldowns"},
    "godworthy_10": {"effect_label": "Origin Rewrite", "all_stats_percent": 16, "lifesteal_percent": 20, "dmg_multiplier": 1.4, "double_damage_percent": 10, "description": "+16% ALL stats, 20% lifesteal, 40% damage, 10% double-damage procs"},
}


def gear_emoji(item_type):
    return WEAPON_EMOJI if item_type == "weapon" else ARMOR_EMOJI if item_type == "armor" else "✨"


def get_trait_emoji(trait):
    return trait.get("emoji", "✨")


def get_item_emoji(item):
    return item.get("emoji", gear_emoji(item.get("type")))


def build_embed(title, description, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color)


def format_trait_bonuses(bonuses):
    parts = []
    for key, value in bonuses.items():
        label = key.replace("_", " ").title()
        if isinstance(value, bool):
            if value:
                parts.append(label)
            continue
        if key.endswith("_multiplier") and isinstance(value, (int, float)):
            parts.append(f"{label} x{value:.2f}")
            continue
        if isinstance(value, (int, float)):
            if key.endswith("_percent"):
                parts.append(f"{label} +{value}%")
            else:
                parts.append(f"{label} +{value}")
            continue
        parts.append(f"{label}: {value}")
    return ", ".join(parts) if parts else "None"


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


def format_trait_info(trait):
    """Format complete trait information for display."""
    rarity = trait.get("rarity", "Unknown")
    emoji = trait.get("emoji", "✨")
    
    # Base bonuses
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
    
    # Unique effects
    trait_id = trait.get("id", "")
    unique_text = ""
    if trait_id in TRAIT_UNIQUE_EFFECTS:
        effect = TRAIT_UNIQUE_EFFECTS[trait_id]
        effect_label = effect.get("effect_label", "Special Effect")
        unique_text = f"\n**✨ Unique Effect: {effect_label}**\n"
        
        for key, value in effect.items():
            if key == "effect_label":
                continue
            if isinstance(value, bool):
                if value:
                    label = key.replace("_", " ").title()
                    unique_text += f"• {label}\n"
            elif key.endswith("_multiplier") and isinstance(value, (int, float)):
                label = key.replace("_multiplier", "").replace("_", " ").title()
                unique_text += f"• {label} Multiplier: **{value:.2f}x**\n"
            elif isinstance(value, (int, float)):
                label = key.replace("_percent", "").replace("_", " ").title()
                if key.endswith("_percent"):
                    unique_text += f"• {label} +**{value}%**\n"
                else:
                    unique_text += f"• {label} +**{value}**\n"
    
    return bonus_text, unique_text


def _empty_core_stats():
    return {stat: 0 for stat in CORE_STATS}


def _merge_additive_stats(target, source):
    for key in CORE_STATS:
        target[key] = target.get(key, 0) + int(source.get(key, 0))
    return target


def _get_rank_power(rank):
    return RANK_POWER.get(rank, RANK_POWER["F"])


def compute_item_stats(item):
    item_type = item.get("type", "weapon")
    rank_power = _get_rank_power(item.get("rank", "F"))
    raw = item.get("stats", {}) or {}

    if item_type == "weapon":
        core = {
            "dmg": 5 + rank_power,
            "qi_cultivation": 2 + int(round(rank_power * 0.65)),
            "luck": 1 + int(round(rank_power * 0.22)),
            "hp": 6 + int(round(rank_power * 0.9)),
        }
    else:
        core = {
            "dmg": 1 + int(round(rank_power * 0.45)),
            "qi_cultivation": 2 + int(round(rank_power * 0.8)),
            "luck": 1 + int(round(rank_power * 0.2)),
            "hp": 18 + rank_power * 2,
        }

    # Legacy item keys still contribute so old data remains meaningful.
    core["dmg"] += int(raw.get("attack", 0))
    core["dmg"] += int(raw.get("attack_percent", 0) / 2)
    core["dmg"] += int(raw.get("critical_chance", 0) / 2)
    core["dmg"] += int(raw.get("critical_chance_percent", 0) / 2)

    core["qi_cultivation"] += int(raw.get("qi_gain", 0))
    core["qi_cultivation"] += int(raw.get("qi_gain_percent", 0) / 2)
    core["qi_cultivation"] += int(raw.get("cultivation_speed_percent", 0) / 2)

    core["luck"] += int(raw.get("dodge_chance_percent", 0) / 2)
    core["luck"] += int(raw.get("critical_chance", 0) / 3)
    core["luck"] += int(raw.get("critical_chance_percent", 0) / 2)

    core["hp"] += int(raw.get("hp", 0))
    core["hp"] += int(raw.get("defense", 0) * 2)
    core["hp"] += int(raw.get("defense_percent", 0))

    for key in CORE_STATS:
        core[key] = max(0, int(core.get(key, 0)))

    return core


def format_core_stats(stats):
    return f"DMG: +{stats['dmg']}, Qi Cult: +{stats['qi_cultivation']}, Luck: +{stats['luck']}, HP: +{stats['hp']}"


def enrich_trait_for_combat(trait):
    if not trait:
        return None

    trait_copy = dict(trait)
    bonuses = dict(trait_copy.get("bonuses", {}))

    for key, value in RARITY_BASE_COMBAT_BONUS.get(trait_copy.get("rarity"), {}).items():
        if isinstance(value, (int, float)):
            bonuses[key] = bonuses.get(key, 0) + value
        else:
            bonuses[key] = value

    for key, value in TRAIT_UNIQUE_EFFECTS.get(trait_copy.get("id"), {}).items():
        if isinstance(value, (int, float)) and isinstance(bonuses.get(key), (int, float)):
            bonuses[key] = bonuses[key] + value
        else:
            bonuses[key] = value

    trait_copy["bonuses"] = bonuses
    return trait_copy


def _build_character_base_stats(player):
    realm_idx = get_realm_index(player.get("realm", "Mortal Path"))
    stage = int(player.get("realm_stage", 1) or 1)
    cult_ego = int(player.get("cult_ego", 1) or 1)

    return {
        "dmg": 8 + cult_ego * 2 + realm_idx * 4 + (stage - 1) * 2,
        "qi_cultivation": 10 + cult_ego + realm_idx * 6 + stage * 2,
        "luck": 3 + int(cult_ego / 3) + realm_idx + int((stage - 1) / 2),
        "hp": 120 + cult_ego * 9 + realm_idx * 24 + (stage - 1) * 12,
    }


def _find_equipped_item(player, item_id):
    if not item_id:
        return None

    for item in player.get("inventory_items", []) + player.get("starter_items_list", []):
        if item.get("id") == item_id:
            return item
    return None


def _apply_trait_to_stats(stats, trait):
    if not trait:
        return stats, {"trait_effects": "None"}

    bonuses = trait.get("bonuses", {})
    final_stats = dict(stats)

    dmg_percent = bonuses.get("dmg_percent", 0) + bonuses.get("attack_percent", 0)
    qi_percent = bonuses.get("qi_cultivation_percent", 0) + bonuses.get("qi_gain_percent", 0) + bonuses.get("cultivation_speed_percent", 0)
    luck_percent = bonuses.get("luck_percent", 0) + bonuses.get("critical_chance_percent", 0) + bonuses.get("dodge_chance_percent", 0)
    hp_percent = bonuses.get("hp_percent", 0) + bonuses.get("defense_percent", 0)

    all_stats_percent = bonuses.get("all_stats_percent", 0)
    dmg_percent += all_stats_percent
    qi_percent += all_stats_percent
    luck_percent += all_stats_percent
    hp_percent += all_stats_percent

    final_stats["dmg"] = int(round(final_stats["dmg"] * (1 + dmg_percent / 100)))
    final_stats["qi_cultivation"] = int(round(final_stats["qi_cultivation"] * (1 + qi_percent / 100)))
    final_stats["luck"] = int(round(final_stats["luck"] * (1 + luck_percent / 100)))
    final_stats["hp"] = int(round(final_stats["hp"] * (1 + hp_percent / 100)))

    dmg_multiplier = bonuses.get("dmg_multiplier", 1.0)
    if isinstance(dmg_multiplier, (int, float)):
        final_stats["dmg"] = int(round(final_stats["dmg"] * dmg_multiplier))

    qi_to_dmg_percent = bonuses.get("qi_to_dmg_percent", 0)
    if qi_to_dmg_percent:
        final_stats["dmg"] += int(round(final_stats["qi_cultivation"] * (qi_to_dmg_percent / 100)))

    luck_to_dmg_percent = bonuses.get("luck_to_dmg_percent", 0)
    if luck_to_dmg_percent:
        final_stats["dmg"] += int(round(final_stats["luck"] * (luck_to_dmg_percent / 100)))

    extras = []
    if bonuses.get("effect_label"):
        extras.append(str(bonuses.get("effect_label")))
    if bonuses.get("lifesteal_percent"):
        extras.append(f"Lifesteal {bonuses['lifesteal_percent']}%")
    if bonuses.get("damage_taken_reduction_percent"):
        extras.append(f"Damage Reduction {bonuses['damage_taken_reduction_percent']}%")
    if bonuses.get("breakthrough_chance_bonus_percent"):
        extras.append(f"Breakthrough Bonus {bonuses['breakthrough_chance_bonus_percent']}%")

    return final_stats, {"trait_effects": ", ".join(extras) if extras else "Passive stat boosts"}


def compute_player_stat_sheet(player):
    base_stats = _build_character_base_stats(player)

    gear_stats = _empty_core_stats()
    weapon_item = _find_equipped_item(player, player.get("starter_weapon"))
    armor_item = _find_equipped_item(player, player.get("starter_armor"))

    if weapon_item:
        _merge_additive_stats(gear_stats, compute_item_stats(weapon_item))
    if armor_item:
        _merge_additive_stats(gear_stats, compute_item_stats(armor_item))

    pre_trait_total = _empty_core_stats()
    _merge_additive_stats(pre_trait_total, base_stats)
    _merge_additive_stats(pre_trait_total, gear_stats)

    trait_entry = find_trait_by_name(player.get("trait_name"))
    final_total, extras = _apply_trait_to_stats(pre_trait_total, trait_entry)

    power_score = final_total["dmg"] * 2 + final_total["hp"] + final_total["qi_cultivation"] * 2 + final_total["luck"] * 3
    if power_score >= 1400:
        power_rank = "S"
    elif power_score >= 1100:
        power_rank = "A"
    elif power_score >= 850:
        power_rank = "B"
    elif power_score >= 620:
        power_rank = "C"
    elif power_score >= 420:
        power_rank = "D"
    else:
        power_rank = "E"

    return {
        "base": base_stats,
        "gear": gear_stats,
        "total": final_total,
        "trait": trait_entry,
        "trait_effects": extras.get("trait_effects", "None"),
        "power_rank": power_rank,
        "power_score": power_score,
    }


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
            return enrich_trait_for_combat(trait)
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
    return enrich_trait_for_combat(random.choice(filtered))


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
        description=(
            "```\n"
            "+------------------------------+\n"
            "|       Cultivation Trait      |\n"
            "+------------------------------+\n"
            "```"
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name=f"{get_trait_emoji(trait)} Trait", value=trait["name"], inline=True)
    embed.add_field(name="Rarity", value=trait["rarity"], inline=True)
    embed.add_field(name="Rolls Left", value=str(rolls_left), inline=True)
    embed.add_field(name="Description", value=trait["description"], inline=False)
    embed.add_field(name="Bonuses", value=format_trait_bonuses(trait["bonuses"]), inline=False)
    embed.set_footer(text=status_line)
    return embed


def build_starter_roll_embed(item, roll_number, rolls_left, status_line):
    stats_text = format_core_stats(compute_item_stats(item))
    embed = discord.Embed(
        title=f"{get_item_emoji(item)} Starter Item Roll",
        description=(
            "```\n"
            "+------------------------------+\n"
            "|      Starter Item Roll       |\n"
            "+------------------------------+\n"
            "```"
        ),
        color=discord.Color.green(),
    )
    embed.add_field(name="Roll", value=f"{roll_number}/10", inline=True)
    embed.add_field(name=f"{get_item_emoji(item)} Item", value=item["name"], inline=True)
    embed.add_field(name="Rank", value=item["rank"], inline=True)
    embed.add_field(name="Type", value=f"{get_item_emoji(item)} {item['type'].title()}", inline=True)
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
        "stats": compute_item_stats(rolled_item),
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
    stats_text = format_core_stats(compute_item_stats(item))
    return (
        f"Roll {roll_number}/10\n"
        f"You obtained: {get_item_emoji(item)} {item['name']}\n"
        f"Rank: {item['rank']}\n"
        f"Type: {get_item_emoji(item)} {item['type'].title()}\n"
        f"Stats: {stats_text}\n"
        f"Starter Rolls Left: {rolls_left}\n"
        "These are candidate items only. After all 10 rolls, keep exactly 1 weapon and 1 armor."
    )


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
                placeholder="Choose your final weapon",
                min_values=1,
                max_values=1,
                options=weapon_options,
            )
            weapon_select.callback = self.select_weapon_callback
            self.add_item(weapon_select)

        if armor_options:
            armor_select = discord.ui.Select(
                placeholder="Choose your final armor",
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
    embed = discord.Embed(title="Cultivara Commands", color=discord.Color.blurple())
    embed.add_field(name="Core", value="!ping\n!help\n!profile\n!reset", inline=True)
    embed.add_field(name="Traits", value="!rolltrait\nCute trait icons follow each roll", inline=True)
    embed.add_field(name="Starter Items", value=f"!rollstarter\n!loadout\n!inv\n!inventory\n!choosestarter <weapon_roll> <armor_roll>\n{WEAPON_EMOJI} weapons / {ARMOR_EMOJI} armor swap later", inline=True)
    embed.add_field(name="Progression", value="!advance", inline=True)
    embed.set_footer(text="Tip: Use the buttons to keep rolling without retyping.")
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
            "Your character has been created.\n"
            "You have 10 free trait rolls. Use !rolltrait to begin.\n"
            "You also have 10 starter item rolls. Use !rollstarter, then keep only 1 weapon and 1 armor.\n"
            "Use !loadout to choose your final starter gear.\n"
            "After that, use !inv or !inventory to view your regular inventory.",
            discord.Color.green(),
        )
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


@bot.command(name="profile")
async def profile(ctx):
    player = get_player(str(ctx.author.id))

    if player is None:
        await ctx.send(embed=build_embed("No Character", "You do not have a character yet. Use !create first.", discord.Color.orange()))
        return

    trait_line = player.get("trait_name") or "None"
    trait_entry = find_trait_by_name(player.get("trait_name"))
    stat_sheet = compute_player_stat_sheet(player)
    if trait_entry:
        trait_line = f"{get_trait_emoji(trait_entry)} {trait_line}"
    realm_display = get_realm_display(player['realm'], player['realm_stage'])
    starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

    embed = discord.Embed(title=f"{player['character_name']} Profile", color=discord.Color.purple())
    embed.add_field(name="Cult Ego", value=str(player["cult_ego"]), inline=True)
    embed.add_field(name="Qi", value=str(player["qi"]), inline=True)
    embed.add_field(name="Realm", value=realm_display, inline=False)
    embed.add_field(name="Trait", value=trait_line, inline=True)
    embed.add_field(name="Trait ID", value=player["selected_trait"] or "None", inline=True)
    embed.add_field(name="Starter Weapon", value=starter_weapon_name, inline=False)
    embed.add_field(name="Starter Armor", value=starter_armor_name, inline=False)
    embed.add_field(name="Base Stats", value=format_core_stats(stat_sheet["base"]), inline=False)
    embed.add_field(name="Gear Stats", value=format_core_stats(stat_sheet["gear"]), inline=False)
    embed.add_field(name="Total Stats", value=format_core_stats(stat_sheet["total"]), inline=False)
    embed.add_field(name="Trait Combat Effects", value=stat_sheet["trait_effects"], inline=False)
    embed.add_field(name="Abilities", value=player["abilities"], inline=False)
    inventory_preview = player.get("inventory_items", [])
    if inventory_preview:
        preview_lines = [f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}]" for index, item in enumerate(inventory_preview, 1)]
        inventory_value = "\n".join(preview_lines)
        if len(inventory_value) > 1000:
            inventory_value = inventory_value[:1000] + "\n..."
    else:
        inventory_value = "None"
    embed.add_field(name="Inventory", value=inventory_value, inline=False)
    embed.add_field(name="Clan", value=player["clan"], inline=False)
    embed.set_footer(text=f"Overall Rank: {stat_sheet['power_rank']} | Power Score: {stat_sheet['power_score']}")
    await ctx.send(embed=embed)


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

    trait = find_trait_by_name(trait_name)
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
    bonus_text, unique_text = format_trait_info(trait)
    rarity = trait.get("rarity", "Unknown")
    emoji = trait.get("emoji", "✨")
    description = trait.get("description", "No description available.")
    power_rating = get_trait_power_rating(rarity)
    rarity_tier = get_trait_rarity_tier(rarity)

    # Build embed
    embed = discord.Embed(
        title=f"{emoji} {trait_name} - {rarity} Trait",
        description=description,
        color=discord.Color.gold() if rarity_tier >= 6 else discord.Color.blue(),
    )

    embed.add_field(name="════════════════════════════", value=f"**Rarity Level:** {rarity_tier}/8\n**Power Rating:** {power_rating}", inline=False)

    if bonus_text:
        embed.add_field(name="📊 Base Bonuses", value=bonus_text.strip(), inline=False)

    if unique_text:
        embed.add_field(name=unique_text.split("\n")[0], value="\n".join(unique_text.split("\n")[1:]).strip(), inline=False)

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
        stats_text = format_core_stats(compute_item_stats(item))
        lines.append(f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}] - {stats_text}")

    starter_weapon_name, starter_armor_name = get_selected_starter_names(player)

    embed = discord.Embed(
        title="Starter Loadout Candidates ✨" if starter_finalize else "Loadout ✨",
        color=discord.Color.teal(),
    )
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="Items", value=items_text, inline=False)
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
    if not inventory_items:
        await ctx.send(
            embed=build_embed(
                "Inventory ✨",
                "Your inventory is empty right now. Finish your starter loadout to move only your selected weapon and armor here.",
                discord.Color.orange(),
            )
        )
        return

    lines = []
    for index, item in enumerate(inventory_items, 1):
        stats_text = format_core_stats(compute_item_stats(item))
        equipped_tag = ""
        if item.get("id") == player.get("starter_weapon"):
            equipped_tag = " [Equipped Weapon]"
        elif item.get("id") == player.get("starter_armor"):
            equipped_tag = " [Equipped Armor]"
        lines.append(f"{index}. {get_item_emoji(item)} {item['name']} [{item['rank']}] - {stats_text}{equipped_tag}")

    embed = discord.Embed(title="Inventory ✨", color=discord.Color.blue())
    items_text = "\n".join(lines)
    if len(items_text) > 1000:
        items_text = items_text[:1000] + "\n..."
    embed.add_field(name="Items", value=items_text, inline=False)
    embed.set_footer(text=f"Use !loadout to change {WEAPON_EMOJI} weapon and {ARMOR_EMOJI} armor. New gear can be swapped in later.")
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
        await ctx.send("You do not have a character yet. Use !create first.")
        return

    realm_name = player['realm']
    stage = player['realm_stage']
    requirement = get_progression_requirement(realm_name, stage)
    chance = get_breakthrough_chance(realm_name, stage)
    bonus = get_realm_bonus(realm_name)

    if player['qi'] < requirement:
        await ctx.send(
            f"You need {requirement} Qi to advance.\n"
            f"Current Qi: {player['qi']}\n"
            f"Breakthrough chance: {chance}%"
        )
        return

    if not spend_qi(str(ctx.author.id), requirement):
        await ctx.send("You do not have enough Qi to attempt this breakthrough.")
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
        await ctx.send(
            f"Breakthrough successful!\n"
            f"Realm: {get_realm_display(realm_name, next_stage)}\n"
            f"Bonus: {bonus}"
        )
    else:
        await ctx.send(
            f"The breakthrough failed.\n"
            f"You spent {requirement} Qi.\n"
            f"Breakthrough chance: {chance}%"
        )


def main():
    initialize_database()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
