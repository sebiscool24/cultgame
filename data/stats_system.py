"""
Player stats calculation system - combines base stats, gear, and trait bonuses
"""

# Example trait bonuses by rarity - these are referenced when calculating stats
TRAIT_BONUS_BY_RARITY = {
    "Common": {"damage": 5, "defense": 3, "luck": 1},
    "Uncommon": {"damage": 10, "defense": 6, "luck": 2},
    "Great": {"damage": 15, "defense": 10, "luck": 5},
    "Amazing": {"damage": 25, "defense": 15, "luck": 8},
    "Legendary": {"damage": 40, "defense": 25, "luck": 15},
    "Celestial": {"damage": 60, "defense": 40, "luck": 25, "special": "Lifesteal"},
    "Godworthy": {"damage": 100, "defense": 60, "luck": 40, "special": "Divine Ascension"},
}

TRAIT_DESCRIPTIONS = {
    "Common": "Modest training bonus",
    "Uncommon": "Steady cultivation boost",
    "Great": "Notable growth advantage",
    "Amazing": "Significant power increase",
    "Legendary": "Rare ascension effect",
    "Celestial": "Lifesteal: recover 10% of damage dealt",
    "Godworthy": "Divine Ascension: +2x damage multiplier, immunity to critical hits",
}


def get_trait_bonuses(trait_rarity):
    """Get stat bonuses for a trait based on rarity."""
    return TRAIT_BONUS_BY_RARITY.get(trait_rarity, {})


def get_trait_passive_description(trait_rarity):
    """Get passive effect description for a trait."""
    return TRAIT_DESCRIPTIONS.get(trait_rarity, "Unknown trait")


def calculate_total_stats(base_stats, equipped_weapon=None, equipped_armor=None, trait_bonuses=None):
    """
    Calculate total stats from base + equipment + traits
    
    Args:
        base_stats: dict with base stats {damage, defense, luck, speed, armor, hp}
        equipped_weapon: dict with weapon stats
        equipped_armor: dict with armor stats
        trait_bonuses: dict with trait bonus stats
    
    Returns:
        dict with total stats
    """
    total = {
        "damage": base_stats.get("damage", 0),
        "defense": base_stats.get("defense", 0),
        "luck": base_stats.get("luck", 0),
        "speed": base_stats.get("speed", 0),
        "armor": base_stats.get("armor", 0),
        "hp": base_stats.get("hp", 50),
    }
    
    # Add equipment stats
    if equipped_weapon and isinstance(equipped_weapon, dict):
        weapon_stats = equipped_weapon.get("stats", {})
        total["damage"] += weapon_stats.get("damage", 0)
        total["defense"] += weapon_stats.get("defense", 0)
        total["luck"] += weapon_stats.get("luck", 0)
        total["speed"] += weapon_stats.get("speed", 0)
        total["armor"] += weapon_stats.get("armor", 0)
    
    if equipped_armor and isinstance(equipped_armor, dict):
        armor_stats = equipped_armor.get("stats", {})
        total["damage"] += armor_stats.get("damage", 0)
        total["defense"] += armor_stats.get("defense", 0)
        total["luck"] += armor_stats.get("luck", 0)
        total["speed"] += armor_stats.get("speed", 0)
        total["armor"] += armor_stats.get("armor", 0)
        total["hp"] += armor_stats.get("hp", 0)
    
    stat_aliases = {
        "attack": "damage",
        "damage": "damage",
        "defense": "defense",
        "def": "defense",
        "hp": "hp",
        "health": "hp",
        "luck": "luck",
        "lck": "luck",
        "speed": "speed",
        "armor": "armor",
    }

    combat_bonus_keys = {
        "critical_chance_percent",
        "dodge_chance_percent",
        "damage_reduction_percent",
        "lifesteal_percent",
        "counter_chance_percent",
        "omen_chance_percent",
        "sequence_authority_percent",
        "madness_resistance_percent",
        "fate_anchor_percent",
        "concealment_percent",
        "qi_gain_percent",
        "cultivation_speed_percent",
        "breakthrough_reward_bonus_percent",
        "loot_luck_percent",
    }

    # Add trait bonuses. Percent/flat stat bonuses affect the core sheet;
    # mystery-style keys are preserved for combat/profile systems.
    if trait_bonuses and isinstance(trait_bonuses, dict):
        for key, value in trait_bonuses.items():
            if isinstance(value, bool):
                total[key] = value
                continue
            if not isinstance(value, (int, float)):
                total[key] = value
                continue

            if key in total:
                total[key] += value
            elif key.endswith("_percent"):
                base_key = key.removesuffix("_percent")
                stat_key = stat_aliases.get(base_key)
                if stat_key in total:
                    bonus_amount = int(total[stat_key] * value / 100)
                    if value > 0:
                        bonus_amount = max(1, bonus_amount)
                    elif value < 0:
                        bonus_amount = min(-1, bonus_amount)
                    total[stat_key] += bonus_amount
                elif key in combat_bonus_keys:
                    total[key] = total.get(key, 0) + value
            elif key.endswith("_flat") or key.endswith("_bonus"):
                base_key = key.rsplit("_", 1)[0]
                stat_key = stat_aliases.get(base_key)
                if stat_key in total:
                    total[stat_key] += value
                else:
                    total[key] = total.get(key, 0) + value
            elif key.endswith("_multiplier"):
                base_key = key.removesuffix("_multiplier")
                stat_key = stat_aliases.get(base_key)
                if stat_key in total:
                    total[stat_key] = int(total[stat_key] * value)
                else:
                    total[key] = value
            elif key in combat_bonus_keys:
                total[key] = total.get(key, 0) + value
    
    return total


def format_stats(stats):
    """Format stats for display in Discord embeds."""
    return f"""⚔️ **Damage:** {stats['damage']}
🛡️ **Defense:** {stats['defense']}
🍀 **Luck:** {stats['luck']}
⚡ **Speed:** {stats['speed']}
🔰 **Armor:** {stats['armor']}
❤️ **HP:** {stats['hp']}"""


def calculate_rank_from_stats(total_stats):
    """Calculate overall rank from stats."""
    # Simple calculation: sum important stats
    rank_score = (total_stats['damage'] * 1.5 + 
                  total_stats['defense'] + 
                  total_stats['luck'] * 1.2 +
                  total_stats['speed'] + 
                  total_stats['armor'])
    
    # Map score to rank
    if rank_score >= 500:
        return "⭐⭐⭐ S-Rank", "S"
    elif rank_score >= 400:
        return "⭐⭐⭐ A-Rank", "A"
    elif rank_score >= 300:
        return "⭐⭐ B-Rank", "B"
    elif rank_score >= 200:
        return "⭐ C-Rank", "C"
    elif rank_score >= 100:
        return "D-Rank", "D"
    else:
        return "F-Rank", "F"
