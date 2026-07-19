REALMS = [
    {"name": "Unmutated Gene", "bonus": "Baseline human body; begin collecting gene essence", "qi_requirement": 80, "breakthrough_chance": 95},
    {"name": "Primitive Mutant", "bonus": "Small body and instinct increase", "qi_requirement": 160, "breakthrough_chance": 85},
    {"name": "Mutant Genome", "bonus": "Improved essence absorption", "qi_requirement": 280, "breakthrough_chance": 78},
    {"name": "Sacred-Blood Genome", "bonus": "Unlocks stronger mutation bonuses", "qi_requirement": 440, "breakthrough_chance": 70},
    {"name": "First Sanctuary Evolver", "bonus": "Higher gene core growth", "qi_requirement": 640, "breakthrough_chance": 60},
    {"name": "Second Sanctuary Evolver", "bonus": "Improved evolution stability", "qi_requirement": 880, "breakthrough_chance": 50},
    {"name": "Super Gene Noble", "bonus": "Unlock future geno-art interactions", "qi_requirement": 1160, "breakthrough_chance": 40},
    {"name": "King-Class Genome", "bonus": "Strong sanctuary status bonuses", "qi_requirement": 1480, "breakthrough_chance": 30},
    {"name": "Emperor-Class Genome", "bonus": "Endgame-level evolution pressure", "qi_requirement": 1840, "breakthrough_chance": 20},
    {"name": "Deified Gene Core", "bonus": "Extremely difficult final evolution", "qi_requirement": 2240, "breakthrough_chance": 10},
]

LEGACY_REALM_ALIASES = {
    "Mortal Path": "Unmutated Gene",
    "Awakened Body": "Primitive Mutant",
    "Spirit Vessel": "Mutant Genome",
    "Core Forging": "Sacred-Blood Genome",
    "Astral Domain": "First Sanctuary Evolver",
    "Heavenly Soul": "Second Sanctuary Evolver",
    "Dao Walker": "Super Gene Noble",
    "Celestial Monarch": "King-Class Genome",
    "Immortal Sovereign": "Emperor-Class Genome",
    "Godworthy Existence": "Deified Gene Core",
}


def get_realm_index(realm_name):
    realm_name = LEGACY_REALM_ALIASES.get(realm_name, realm_name)
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
    realm_name = LEGACY_REALM_ALIASES.get(realm_name, realm_name)
    return f"{realm_name} Gene Lock {stage}/9"
