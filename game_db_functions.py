"""
Game system database functions - these are helper functions for managing
player data related to the game systems (XP, gear, combat, etc.)
"""
import json
import sqlite3
import os

DB_FOLDER = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_FOLDER, "cultivation.db")


def _parse_json(value):
    """Parse JSON string, return empty dict if invalid."""
    if not value or value == "None":
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _parse_json_list(value):
    """Parse JSON list, return empty list if invalid."""
    if not value or value == "None":
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _dump_json(obj):
    """Dump object to JSON string."""
    return json.dumps(obj)


def get_player_game_data(user_id):
    """Get complete game system data for a player."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        """
        SELECT xp, equipped_weapon, equipped_armor, cooldowns, gear_inventory, base_stats
        FROM players WHERE user_id = ?
        """,
        (str(user_id),)
    )
    row = cursor.fetchone()
    connection.close()
    
    if row is None:
        return None
    
    return {
        "xp": row[0],
        "equipped_weapon": _parse_json(row[1]),
        "equipped_armor": _parse_json(row[2]),
        "cooldowns": _parse_json(row[3]),
        "gear_inventory": _parse_json_list(row[4]),
        "base_stats": _parse_json(row[5]),
    }


def add_xp(user_id, xp_amount):
    """Add XP to player."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET xp = xp + ? WHERE user_id = ?",
        (int(xp_amount), str(user_id))
    )
    connection.commit()
    connection.close()


def set_xp(user_id, xp_amount):
    """Set exact XP for player."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET xp = ? WHERE user_id = ?",
        (int(xp_amount), str(user_id))
    )
    connection.commit()
    connection.close()


def get_xp(user_id):
    """Get player's current XP."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute("SELECT xp FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    connection.close()
    
    return row[0] if row else 0


def set_equipped_gear(user_id, weapon=None, armor=None):
    """Set equipped weapon and armor."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET equipped_weapon = ?, equipped_armor = ? WHERE user_id = ?",
        (_dump_json(weapon) if weapon else None, 
         _dump_json(armor) if armor else None, 
         str(user_id))
    )
    connection.commit()
    connection.close()


def get_equipped_gear(user_id):
    """Get player's equipped weapon and armor."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT equipped_weapon, equipped_armor FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    connection.close()
    
    if row is None:
        return None, None
    
    return _parse_json(row[0]), _parse_json(row[1])


def add_gear_to_inventory(user_id, gear_items):
    """Add gear items to player's gear inventory."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT gear_inventory FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    
    current_inventory = _parse_json_list(row[0]) if row else []
    current_inventory.extend(gear_items if isinstance(gear_items, list) else [gear_items])
    
    cursor.execute(
        "UPDATE players SET gear_inventory = ? WHERE user_id = ?",
        (_dump_json(current_inventory), str(user_id))
    )
    connection.commit()
    connection.close()


def get_gear_inventory(user_id):
    """Get player's gear inventory."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT gear_inventory FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    connection.close()
    
    return _parse_json_list(row[0]) if row else []


def remove_gear_from_inventory(user_id, gear_id):
    """Remove a gear item from inventory by ID."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT gear_inventory FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    
    if row:
        inventory = _parse_json_list(row[0])
        inventory = [item for item in inventory if item.get("id") != gear_id]
        
        cursor.execute(
            "UPDATE players SET gear_inventory = ? WHERE user_id = ?",
            (_dump_json(inventory), str(user_id))
        )
        connection.commit()
    
    connection.close()


def get_gear_by_id(user_id, gear_id):
    """Get a specific gear item by ID from player's inventory."""
    inventory = get_gear_inventory(user_id)
    for item in inventory:
        if item.get("id") == gear_id:
            return item
    return None


def update_cooldowns(user_id, cooldowns_dict):
    """Update player's cooldowns."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET cooldowns = ? WHERE user_id = ?",
        (_dump_json(cooldowns_dict), str(user_id))
    )
    connection.commit()
    connection.close()


def get_cooldowns(user_id):
    """Get player's cooldowns."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT cooldowns FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    connection.close()
    
    return _parse_json(row[0]) if row else {}


def set_base_stats(user_id, stats_dict):
    """Set player's base stats."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET base_stats = ? WHERE user_id = ?",
        (_dump_json(stats_dict), str(user_id))
    )
    connection.commit()
    connection.close()


def get_base_stats(user_id):
    """Get player's base stats."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "SELECT base_stats FROM players WHERE user_id = ?",
        (str(user_id),)
    )
    row = cursor.fetchone()
    connection.close()
    
    if row:
        stats = _parse_json(row[0])
        # Ensure default stats if empty
        if stats:
            return stats
    
    # Default base stats
    return {
        "damage": 5,
        "defense": 3,
        "luck": 2,
        "speed": 4,
        "armor": 2,
        "hp": 50,
    }


def add_wallet_currency(user_id, amount):
    """Add currency to player's wallet."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET wallet = wallet + ? WHERE user_id = ?",
        (int(amount), str(user_id))
    )
    connection.commit()
    connection.close()


def get_wallet(user_id):
    """Get player's wallet balance."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute("SELECT wallet FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    connection.close()
    
    return row[0] if row else 0


def get_bank_balance(user_id):
    """Get player's bank balance."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute("SELECT bank_balance FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    connection.close()
    
    return row[0] if row else 0


def deposit_to_bank(user_id, amount):
    """Move currency from wallet to bank."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET wallet = wallet - ?, bank_balance = bank_balance + ? WHERE user_id = ? AND wallet >= ?",
        (int(amount), int(amount), str(user_id), int(amount))
    )
    connection.commit()
    success = cursor.rowcount > 0
    connection.close()
    
    return success


def withdraw_from_bank(user_id, amount):
    """Move currency from bank to wallet."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    
    cursor.execute(
        "UPDATE players SET bank_balance = bank_balance - ?, wallet = wallet + ? WHERE user_id = ? AND bank_balance >= ?",
        (int(amount), int(amount), str(user_id), int(amount))
    )
    connection.commit()
    success = cursor.rowcount > 0
    connection.close()
    
    return success
