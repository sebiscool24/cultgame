import os
import sqlite3

DB_FOLDER = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_FOLDER, "cultivation.db")


def _parse_json_list(value):
    import json

    if not value or value == "None":
        return []

    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []

    return parsed if isinstance(parsed, list) else []


def _dump_json_list(items):
    import json

    return json.dumps(items)


def _add_column_if_missing(cursor, column_name, column_definition):
    cursor.execute("PRAGMA table_info(players)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE players ADD COLUMN {column_name} {column_definition}")


def initialize_database():
    os.makedirs(DB_FOLDER, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            character_name TEXT,
            cult_ego INTEGER NOT NULL DEFAULT 1,
            qi INTEGER NOT NULL DEFAULT 0,
            realm TEXT NOT NULL DEFAULT 'Unmutated Gene',
            realm_stage INTEGER NOT NULL DEFAULT 1,
            selected_trait TEXT,
            trait_name TEXT,
            selected_origin TEXT,
            origin_name TEXT,
            selected_bloodline TEXT,
            bloodline_name TEXT,
            inventory TEXT NOT NULL DEFAULT '[]',
            abilities TEXT NOT NULL DEFAULT 'None',
            clan TEXT NOT NULL DEFAULT 'None',
            trait_rolls_left INTEGER NOT NULL DEFAULT 10,
            starter_rolls_left INTEGER NOT NULL DEFAULT 10,
            starter_weapon TEXT,
            starter_armor TEXT,
            starter_items TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Keep old databases compatible as fields are added over time.
    _add_column_if_missing(cursor, "character_name", "TEXT")
    _add_column_if_missing(cursor, "cult_ego", "INTEGER NOT NULL DEFAULT 1")
    _add_column_if_missing(cursor, "qi", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "realm", "TEXT NOT NULL DEFAULT 'Unmutated Gene'")
    _add_column_if_missing(cursor, "realm_stage", "INTEGER NOT NULL DEFAULT 1")
    _add_column_if_missing(cursor, "selected_trait", "TEXT")
    _add_column_if_missing(cursor, "trait_name", "TEXT")
    _add_column_if_missing(cursor, "selected_origin", "TEXT")
    _add_column_if_missing(cursor, "origin_name", "TEXT")
    _add_column_if_missing(cursor, "selected_bloodline", "TEXT")
    _add_column_if_missing(cursor, "bloodline_name", "TEXT")
    _add_column_if_missing(cursor, "inventory", "TEXT NOT NULL DEFAULT '[]'")
    _add_column_if_missing(cursor, "abilities", "TEXT NOT NULL DEFAULT 'None'")
    _add_column_if_missing(cursor, "clan", "TEXT NOT NULL DEFAULT 'None'")
    _add_column_if_missing(cursor, "trait_rolls_left", "INTEGER NOT NULL DEFAULT 10")
    _add_column_if_missing(cursor, "starter_rolls_left", "INTEGER NOT NULL DEFAULT 10")
    _add_column_if_missing(cursor, "starter_weapon", "TEXT")
    _add_column_if_missing(cursor, "starter_armor", "TEXT")
    _add_column_if_missing(cursor, "starter_items", "TEXT NOT NULL DEFAULT '[]'")
    
    # Game systems columns
    _add_column_if_missing(cursor, "xp", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "equipped_weapon", "TEXT")
    _add_column_if_missing(cursor, "equipped_armor", "TEXT")
    _add_column_if_missing(cursor, "cooldowns", "TEXT NOT NULL DEFAULT '{}'")
    _add_column_if_missing(cursor, "gear_inventory", "TEXT NOT NULL DEFAULT '[]'")
    _add_column_if_missing(cursor, "base_stats", "TEXT NOT NULL DEFAULT '{\"damage\": 5, \"defense\": 3, \"luck\": 2, \"speed\": 4, \"armor\": 2, \"hp\": 50}'")
    _add_column_if_missing(cursor, "wallet", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "bank_balance", "INTEGER NOT NULL DEFAULT 0")

    connection.commit()
    connection.close()

    print(f"Database ready: {DB_PATH}")


def create_player(user_id, username):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO players (
                user_id, username, character_name, cult_ego, qi, realm, realm_stage,
                selected_trait, trait_name, inventory, abilities, clan, trait_rolls_left,
                starter_rolls_left, starter_weapon, starter_armor, starter_items
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_id),
                username,
                username,
                1,
                0,
                "Unmutated Gene",
                1,
                None,
                None,
                "None",
                "None",
                "None",
                10,
                10,
                None,
                None,
                "[]",
            ),
        )
        connection.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        connection.close()


def get_player(user_id):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT user_id, username, character_name, cult_ego, qi, realm, realm_stage,
               selected_trait, trait_name, inventory, abilities, clan, trait_rolls_left,
             starter_rolls_left, starter_weapon, starter_armor, starter_items,
             selected_origin, origin_name, selected_bloodline, bloodline_name
        FROM players WHERE user_id = ?
        """,
        (str(user_id),),
    )
    row = cursor.fetchone()
    connection.close()

    if row is None:
        return None

    return {
        "user_id": row[0],
        "username": row[1],
        "character_name": row[2] or row[1],
        "cult_ego": row[3],
        "qi": row[4],
        "realm": row[5],
        "realm_stage": row[6],
        "selected_trait": row[7],
        "trait_name": row[8],
        "inventory": row[9],
        "inventory_items": _parse_json_list(row[9]),
        "abilities": row[10],
        "clan": row[11],
        "trait_rolls_left": row[12],
        "starter_rolls_left": row[13],
        "starter_weapon": row[14],
        "starter_armor": row[15],
        "starter_items": row[16],
        "starter_items_list": _parse_json_list(row[16]),
        "selected_origin": row[17] or row[7],
        "origin_name": row[18] or row[8],
        "selected_bloodline": row[19],
        "bloodline_name": row[20],
    }


def player_exists(user_id):
    return get_player(user_id) is not None


def delete_player(user_id):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("DELETE FROM players WHERE user_id = ?", (str(user_id),))
    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return deleted


def update_player_trait(user_id, trait_id, trait_name):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE players SET selected_trait = ?, trait_name = ? WHERE user_id = ?",
        (trait_id, trait_name, str(user_id)),
    )
    connection.commit()
    connection.close()


def update_player_origin(user_id, origin_id, origin_name):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE players
        SET selected_origin = ?, origin_name = ?, selected_trait = ?, trait_name = ?
        WHERE user_id = ?
        """,
        (origin_id, origin_name, origin_id, origin_name, str(user_id)),
    )
    connection.commit()
    connection.close()


def update_player_bloodline(user_id, bloodline_id, bloodline_name):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE players SET selected_bloodline = ?, bloodline_name = ? WHERE user_id = ?",
        (bloodline_id, bloodline_name, str(user_id)),
    )
    connection.commit()
    connection.close()


def spend_trait_roll(user_id):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT trait_rolls_left FROM players WHERE user_id = ?",
        (str(user_id),),
    )
    row = cursor.fetchone()
    if row is None:
        connection.close()
        return False

    if row[0] <= 0:
        connection.close()
        return False

    cursor.execute(
        "UPDATE players SET trait_rolls_left = trait_rolls_left - 1 WHERE user_id = ?",
        (str(user_id),),
    )
    connection.commit()
    connection.close()
    return True


def get_trait_rolls_left(user_id):
    player = get_player(user_id)
    if player is None:
        return 0
    return player.get("trait_rolls_left", 0)


def get_starter_rolls_left(user_id):
    player = get_player(user_id)
    if player is None:
        return 0
    return player.get("starter_rolls_left", 0)


def use_starter_roll(user_id):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("SELECT starter_rolls_left FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    if row is None or row[0] <= 0:
        connection.close()
        return False

    cursor.execute(
        "UPDATE players SET starter_rolls_left = starter_rolls_left - 1 WHERE user_id = ?",
        (str(user_id),),
    )
    connection.commit()
    connection.close()
    return True


def add_starter_item(user_id, item_summary):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("SELECT starter_items FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    if row is None:
        connection.close()
        return False

    parsed = _parse_json_list(row[0])
    parsed.append(item_summary)
    cursor.execute(
        "UPDATE players SET starter_items = ? WHERE user_id = ?",
        (_dump_json_list(parsed), str(user_id)),
    )
    connection.commit()
    connection.close()
    return True


def get_inventory_items(user_id):
    player = get_player(user_id)
    if player is None:
        return []
    return player.get("inventory_items", [])


def set_inventory_items(user_id, items):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE players SET inventory = ? WHERE user_id = ?",
        (_dump_json_list(items), str(user_id)),
    )
    connection.commit()
    connection.close()


def add_items_to_inventory(user_id, items):
    current_items = get_inventory_items(user_id)
    current_items.extend(items)
    set_inventory_items(user_id, current_items)


def move_selected_starter_items_to_inventory(user_id, selected_item_ids):
    player = get_player(user_id)
    if player is None:
        return False

    starter_items = player.get("starter_items_list", [])
    selected_items = []

    for selected_item_id in selected_item_ids:
        for item in starter_items:
            if item.get("id") == selected_item_id:
                selected_items.append(item)
                break

    if selected_items:
        add_items_to_inventory(user_id, selected_items)

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.execute("UPDATE players SET starter_items = ? WHERE user_id = ?", ("[]", str(user_id)))
    connection.commit()
    connection.close()
    return True


def get_item_by_id(user_id, item_id):
    player = get_player(user_id)
    if player is None:
        return None

    all_items = player.get("inventory_items", []) + player.get("starter_items_list", [])
    for item in all_items:
        if item.get("id") == item_id:
            return item
    return None


def choose_starter_items(user_id, weapon_id, armor_id):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE players SET starter_weapon = ?, starter_armor = ? WHERE user_id = ?",
        (weapon_id, armor_id, str(user_id)),
    )
    connection.commit()
    connection.close()


def update_player_realm(user_id, realm_name, realm_stage):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE players SET realm = ?, realm_stage = ? WHERE user_id = ?",
        (realm_name, realm_stage, str(user_id)),
    )
    connection.commit()
    connection.close()


def spend_qi(user_id, amount):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("SELECT qi FROM players WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    if row is None:
        connection.close()
        return False

    if row[0] < amount:
        connection.close()
        return False

    cursor.execute("UPDATE players SET qi = qi - ? WHERE user_id = ?", (amount, str(user_id)))
    connection.commit()
    connection.close()
    return True
