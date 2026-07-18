REALMS = [
    {"name": "Mortal Path", "bonus": "No bonuses", "qi_requirement": 80, "breakthrough_chance": 95},
    {"name": "Awakened Body", "bonus": "Small physical stat increase", "qi_requirement": 160, "breakthrough_chance": 85},
    {"name": "Spirit Vessel", "bonus": "Increased Qi gain", "qi_requirement": 280, "breakthrough_chance": 78},
    {"name": "Core Forging", "bonus": "Unlocks stronger progression bonuses", "qi_requirement": 440, "breakthrough_chance": 70},
    {"name": "Astral Domain", "bonus": "Higher Cult Ego growth", "qi_requirement": 640, "breakthrough_chance": 60},
    {"name": "Heavenly Soul", "bonus": "Improved breakthrough chances", "qi_requirement": 880, "breakthrough_chance": 50},
    {"name": "Dao Walker", "bonus": "Unlock future ability interactions", "qi_requirement": 1160, "breakthrough_chance": 40},
    {"name": "Celestial Monarch", "bonus": "Strong status bonuses", "qi_requirement": 1480, "breakthrough_chance": 30},
    {"name": "Immortal Sovereign", "bonus": "Endgame-level progression", "qi_requirement": 1840, "breakthrough_chance": 20},
    {"name": "Godworthy Existence", "bonus": "Extremely difficult final realm", "qi_requirement": 2240, "breakthrough_chance": 10},
]


def get_realm_index(realm_name):
    for index, realm in enumerate(REALMS):
        if realm["name"] == realm_name:
            return index
    return 0


def get_next_realm(realm_name):
    current_index = get_realm_index(realm_name)
    if current_index < len(REALMS) - 1:
        return REALMS[current_index + 1]["name"]
    return realm_name


def get_realm_bonus(realm_name):
    realm = REALMS[get_realm_index(realm_name)]
    return realm["bonus"]


def get_breakthrough_chance(realm_name, stage):
    realm_index = get_realm_index(realm_name)
    chance = max(5, REALMS[realm_index]["breakthrough_chance"] - (stage - 1) * 2)
    return chance


def get_progression_requirement(realm_name, stage):
    realm_index = get_realm_index(realm_name)
    return REALMS[realm_index]["qi_requirement"] + (stage - 1) * 120


def get_realm_display(realm_name, stage):
    return f"{realm_name} Stage {stage}/9"
