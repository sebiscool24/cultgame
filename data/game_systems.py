"""
Core game systems: stats, combat, gear generation, XP progression
"""
import random
import time
from typing import Dict, List, Tuple, Optional

# ============================================================================
# GAME BALANCE CONFIG - ADJUST THESE FOR BALANCING
# ============================================================================

REALM_XP_THRESHOLDS = {
    1: 0,
    2: 100,
    3: 300,
    4: 600,
    5: 1000,
    6: 1500,
    7: 2100,
    8: 2800,
    9: 3600,
    10: 4500,
}

# Gear rank -> base stat multipliers (factor for random range)
GEAR_RANK_STATS = {
    "S": {"min": 60, "max": 90, "luck": (8, 15), "speed": (12, 20), "armor": (15, 25)},
    "A": {"min": 40, "max": 60, "luck": (6, 12), "speed": (10, 16), "armor": (12, 20)},
    "B": {"min": 20, "max": 40, "luck": (4, 8), "speed": (6, 12), "armor": (8, 15)},
    "C": {"min": 10, "max": 20, "luck": (2, 5), "speed": (3, 8), "armor": (4, 10)},
    "D": {"min": 5, "max": 10, "luck": (1, 3), "speed": (2, 5), "armor": (2, 6)},
    "E": {"min": 2, "max": 5, "luck": (1, 2), "speed": (1, 3), "armor": (1, 3)},
    "F": {"min": 1, "max": 3, "luck": (0, 1), "speed": (0, 2), "armor": (0, 1)},
}

# Loot command rewards - FARMING HAS NO GEAR DROPS
LOOT_REWARDS = {
    "gather": {"xp_range": (10, 25), "currency_range": (5, 15), "drop_gear": False},
    "hunt": {"xp_range": (30, 60), "currency_range": (50, 120), "drop_gear": False},
    "wander": {"xp_range": (50, 100), "currency_range": (25, 75), "drop_gear": False},
}

# Combat rewards
COMBAT_REWARDS = {
    "battle": {"xp_range": (40, 80), "currency_range": (60, 150), "loot_chance": 0.7},
    "raid": {"xp_range": (100, 150), "currency_range": (100, 250), "loot_chance": 0.85},
}

# Trait bonuses by rarity
TRAIT_BONUSES = {
    "Common": {
        "example_bonuses": {"attack_bonus": 5, "defense_bonus": 3},
        "passive": "Modest training bonus",
    },
    "Uncommon": {
        "example_bonuses": {"attack_bonus": 10, "defense_bonus": 6},
        "passive": "Steady cultivation boost",
    },
    "Great": {
        "example_bonuses": {"attack_bonus": 15, "defense_bonus": 10},
        "passive": "Notable growth advantage",
    },
    "Amazing": {
        "example_bonuses": {"attack_bonus": 25, "defense_bonus": 15, "luck_bonus": 5},
        "passive": "Significant power increase",
    },
    "Legendary": {
        "example_bonuses": {"attack_bonus": 40, "defense_bonus": 25, "luck_bonus": 10},
        "passive": "Rare ascension effect",
    },
    "Celestial": {
        "example_bonuses": {"attack_bonus": 60, "defense_bonus": 40, "luck_bonus": 20},
        "passive": "Lifesteal: recover 10% of damage dealt",
    },
    "Godworthy": {
        "example_bonuses": {"attack_bonus": 100, "defense_bonus": 60, "luck_bonus": 30},
        "passive": "Divine Ascension: +2x damage multiplier, immunity to critical hits",
    },
}

# ============================================================================
# DATA STRUCTURES
# ============================================================================


def create_gear_item(rank: str, item_type: str) -> Dict:
    """Generate a random gear item with stats based on rank."""
    rank_config = GEAR_RANK_STATS.get(rank, GEAR_RANK_STATS["F"])
    
    base_damage = random.randint(rank_config["min"], rank_config["max"])
    luck = random.randint(*rank_config["luck"])
    speed = random.randint(*rank_config["speed"])
    armor = random.randint(*rank_config["armor"])
    
    # Defense scales from armor
    defense = armor // 2 + random.randint(0, 5)
    
    item_id = f"{item_type}_{rank}_{random.randint(1000, 9999)}"
    
    return {
        "id": item_id,
        "type": item_type,  # "weapon" or "armor"
        "rank": rank,
        "stats": {
            "damage": base_damage,
            "defense": defense,
            "luck": luck,
            "speed": speed,
            "armor": armor,
        },
        "created_at": int(time.time()),
    }


def calculate_total_stats(
    base_stats: Dict[str, int],
    equipped_weapon: Optional[Dict] = None,
    equipped_armor: Optional[Dict] = None,
    trait_bonuses: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    """Calculate total stats from base + equipped gear + trait bonuses."""
    total = base_stats.copy()
    
    # Add equipped gear stats
    if equipped_weapon and "stats" in equipped_weapon:
        for stat, value in equipped_weapon["stats"].items():
            total[stat] = total.get(stat, 0) + value
    
    if equipped_armor and "stats" in equipped_armor:
        for stat, value in equipped_armor["stats"].items():
            total[stat] = total.get(stat, 0) + value
    
    # Apply trait bonuses
    if trait_bonuses:
        for stat_key, bonus_value in trait_bonuses.items():
            if stat_key.endswith("_bonus"):
                # e.g., "attack_bonus" -> add to "damage"
                base_stat = stat_key.replace("_bonus", "")
                total[base_stat] = total.get(base_stat, 0) + bonus_value
            elif stat_key.endswith("_percent"):
                # e.g., "attack_percent" -> multiply stat
                base_stat = stat_key.replace("_percent", "")
                if base_stat in total:
                    total[base_stat] = int(total[base_stat] * (1 + bonus_value / 100))
    
    return total


# ============================================================================
# COMBAT SYSTEM
# ============================================================================


def calculate_combat_stats(total_stats: Dict[str, int]) -> Dict[str, any]:
    """Calculate derived combat stats from total stats."""
    return {
        "health": total_stats.get("hp", 50) + total_stats.get("armor", 0) * 2,
        "attack": total_stats.get("damage", 0),
        "defense": total_stats.get("defense", 0),
        "crit_chance": min(
            50, 10 + total_stats.get("luck", 0) // 5
        ),  # 10% base + luck bonus, max 50%
        "dodge_chance": min(30, 5 + total_stats.get("speed", 0) // 10),  # 5% base + speed
        "speed": total_stats.get("speed", 0),
    }


def simulate_combat_round(
    player_stats: Dict[str, any],
    enemy_stats: Dict[str, any],
) -> Tuple[int, int, List[str]]:
    """
    Simulate one combat round.
    Returns: (player_damage, enemy_damage, combat_log)
    """
    log = []
    player_damage = 0
    enemy_damage = 0

    # Player attacks
    if random.random() * 100 > enemy_stats["dodge_chance"]:
        player_damage = player_stats["attack"]
        if random.random() * 100 < player_stats["crit_chance"]:
            player_damage = int(player_damage * 1.5)
            log.append(f"⚡ Critical Hit! **{player_damage}** damage!")
        else:
            log.append(f"⚔️ Dealt **{player_damage}** damage")
    else:
        log.append("🛡️ Enemy dodged!")

    # Enemy attacks
    if random.random() * 100 > player_stats["dodge_chance"]:
        enemy_damage = enemy_stats["attack"]
        if random.random() * 100 < enemy_stats["crit_chance"]:
            enemy_damage = int(enemy_damage * 1.5)
            log.append(f"💢 Enemy critical! **{enemy_damage}** damage taken!")
        else:
            log.append(f"💫 Enemy dealt **{enemy_damage}** damage")
    else:
        log.append("✨ Dodged enemy attack!")

    return player_damage, enemy_damage, log


def battle(
    player_stats: Dict[str, int],
    difficulty: str = "normal",
) -> Tuple[bool, int, str, Dict, int]:
    """
    Battle system - player vs generated enemy
    Returns: (won: bool, xp_earned: int, battle_log: str, loot: Dict, currency_earned: int)
    """
    # Generate enemy with scaled stats
    difficulty_multiplier = {"normal": 1.0, "hard": 1.3, "raid": 1.6}.get(difficulty, 1.0)
    enemy_stats = calculate_combat_stats(
        {
            "damage": int(player_stats["damage"] * difficulty_multiplier * 0.8),
            "defense": int(player_stats["defense"] * difficulty_multiplier * 0.8),
            "luck": int(player_stats["luck"] * difficulty_multiplier * 0.7),
            "speed": int(player_stats["speed"] * difficulty_multiplier * 0.9),
            "armor": int(player_stats["armor"] * difficulty_multiplier * 0.8),
            "hp": int((50 + player_stats.get("armor", 0) * 2) * difficulty_multiplier),
        }
    )

    player_combat = calculate_combat_stats(player_stats)
    
    # Battle rounds
    player_health = player_combat["health"]
    enemy_health = enemy_stats["health"]
    log_entries = []
    round_count = 0

    while player_health > 0 and enemy_health > 0 and round_count < 20:
        round_count += 1
        log_entries.append(f"\n**Round {round_count}:**")

        player_dmg, enemy_dmg, round_log = simulate_combat_round(
            player_combat, enemy_stats
        )

        for entry in round_log:
            log_entries.append(entry)

        player_health -= enemy_dmg
        enemy_health -= player_dmg
        log_entries.append(f"HP: **{max(0, player_health)}** / Enemy: **{max(0, enemy_health)}**")

    # Determine winner
    won = player_health > 0
    log_str = "\n".join(log_entries)

    if won:
        if difficulty == "normal":
            xp_earned = random.randint(40, 80)
            currency_earned = random.randint(60, 150)
        else:  # raid
            xp_earned = random.randint(100, 150)
            currency_earned = random.randint(100, 250)
        
        # 70% chance for loot on normal, 85% on raid
        loot_chance = 0.7 if difficulty == "normal" else 0.85
        loot = (
            create_gear_item(random.choice(["D", "C", "B"]), "weapon")
            if random.random() < loot_chance
            else None
        )
        return won, xp_earned, log_str, loot, currency_earned
    else:
        return won, 0, log_str, None, 0


# ============================================================================
# XP & LEVELING
# ============================================================================


def get_xp_for_next_realm(current_realm: int) -> int:
    """Get total XP needed to reach next realm."""
    return REALM_XP_THRESHOLDS.get(current_realm + 1, 5000)


def check_realm_up(current_xp: int, current_realm: int) -> Tuple[bool, int]:
    """Check if player should level up, return (should_level_up, new_realm)."""
    next_threshold = REALM_XP_THRESHOLDS.get(current_realm + 1)
    if next_threshold is not None and current_xp >= next_threshold:
        # Find new realm
        for realm, threshold in sorted(REALM_XP_THRESHOLDS.items(), reverse=True):
            if current_xp >= threshold:
                return True, realm
    return False, current_realm


def add_xp(current_xp: int, current_realm: int, xp_gained: int) -> Tuple[int, int, bool]:
    """
    Add XP and check for realm up.
    Returns: (new_xp, new_realm, leveled_up)
    """
    new_xp = current_xp + xp_gained
    leveled_up, new_realm = check_realm_up(new_xp, current_realm)
    return new_xp, new_realm, leveled_up


# ============================================================================
# COOLDOWN SYSTEM
# ============================================================================


def set_cooldown(
    cooldowns: Dict[str, float], command: str, duration_seconds: int
) -> Dict[str, float]:
    """Set cooldown for a command."""
    cooldowns[command] = time.time() + duration_seconds
    return cooldowns


def get_cooldown_remaining(
    cooldowns: Dict[str, float], command: str
) -> Tuple[bool, float]:
    """Check if command is on cooldown. Returns (is_on_cooldown, seconds_remaining)."""
    if command not in cooldowns:
        return False, 0.0

    remaining = cooldowns[command] - time.time()
    if remaining <= 0:
        return False, 0.0

    return True, remaining


# ============================================================================
# LOOT GENERATION
# ============================================================================


def generate_loot(command: str) -> Tuple[List[Dict], int, int]:
    """
    Generate loot from a command.
    Returns: (loot_items: List, xp_earned: int, currency_earned: int)
    """
    if command not in LOOT_REWARDS:
        return [], 0, 0

    rewards = LOOT_REWARDS[command]
    xp_earned = random.randint(*rewards["xp_range"])
    currency_earned = random.randint(*rewards["currency_range"])

    # Farming commands don't drop gear
    if not rewards.get("drop_gear", True):
        return [], xp_earned, currency_earned
    
    # Combat commands might drop gear - this is handled by battle() function
    return [], xp_earned, currency_earned
