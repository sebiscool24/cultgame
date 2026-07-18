"""
One-time script: cuts sprites from sheets and uploads them as Discord custom emojis.
Weapons1 sheet: 10 cols x 6 rows (swords/daggers/staves), 1600x900
Armor sheet: 9 cols x 6 rows, 1600x900
"""

import asyncio
import io
import os
import discord
from PIL import Image

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN environment variable first.")

# Grid config - measured from sprite sheets (title bar ~80px at top)
SHEET_CONFIGS = {
    "weapons1": {
        "file": "assets/weapons1.webp",
        "cols": 10, "rows": 6,
        "start_x": 145, "start_y": 115,
        "cell_w": 132, "cell_h": 130,
    },
    "armor": {
        "file": "assets/armor.webp",
        "cols": 9, "rows": 6,
        "start_x": 168, "start_y": 115,
        "cell_w": 148, "cell_h": 130,
    },
}

# Pick one sprite per weapon rank (sheet "weapons1", row, col) - 0-indexed
WEAPON_RANK_SPRITES = {
    "F":  ("weapons1", 0, 0),   # simple gray dagger
    "E":  ("weapons1", 0, 1),   # gold dagger
    "D-": ("weapons1", 0, 2),   # plain short sword
    "D":  ("weapons1", 0, 3),   # dark short sword
    "D+": ("weapons1", 0, 4),   # white sword
    "C-": ("weapons1", 0, 5),   # brown sword
    "C":  ("weapons1", 1, 0),   # curved sword
    "C+": ("weapons1", 1, 1),   # larger curved blade
    "B-": ("weapons1", 1, 3),   # thin elegant sword
    "B":  ("weapons1", 2, 0),   # large blade
    "B+": ("weapons1", 2, 3),   # red glowing sword
    "A-": ("weapons1", 2, 4),   # crystal blue sword
}

# Pick one sprite per armor rank (sheet "armor", row, col) - 0-indexed
ARMOR_RANK_SPRITES = {
    "F":  ("armor", 0, 0),   # plain gray vest
    "E":  ("armor", 0, 1),   # dark shirt
    "D-": ("armor", 0, 2),   # gray shirt
    "D":  ("armor", 0, 3),   # green shirt
    "D+": ("armor", 0, 4),   # purple shirt
    "C-": ("armor", 1, 0),   # fur shoulder
    "C":  ("armor", 1, 5),   # tan vest
    "C+": ("armor", 1, 6),   # plated vest
    "B-": ("armor", 2, 1),   # green robe
    "B":  ("armor", 2, 2),   # blue robe
    "B+": ("armor", 2, 5),   # blue plate
    "A-": ("armor", 4, 6),   # armored chest
}


def cut_sprite(sheet_name, row, col):
    cfg = SHEET_CONFIGS[sheet_name]
    img = Image.open(cfg["file"]).convert("RGBA")
    x = cfg["start_x"] + col * cfg["cell_w"]
    y = cfg["start_y"] + row * cfg["cell_h"]
    sprite = img.crop((x, y, x + cfg["cell_w"], y + cfg["cell_h"]))
    sprite = sprite.resize((64, 64), Image.LANCZOS)
    buf = io.BytesIO()
    sprite.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        guild = client.guilds[0]
        print(f"Uploading to: {guild.name} ({guild.id})")

        uploaded = {}
        all_sprites = {**{f"w_{k.replace('-','m').replace('+','p')}": v for k, v in WEAPON_RANK_SPRITES.items()},
                       **{f"a_{k.replace('-','m').replace('+','p')}": v for k, v in ARMOR_RANK_SPRITES.items()}}

        for emoji_name, (sheet, row, col) in all_sprites.items():
            try:
                image_data = cut_sprite(sheet, row, col)
                emoji = await guild.create_custom_emoji(name=emoji_name, image=image_data)
                uploaded[emoji_name] = str(emoji)
                print(f"  Uploaded: {emoji_name} -> {emoji}")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  FAILED {emoji_name}: {e}")

        print("\n--- DONE ---")
        print("Weapon emoji map:")
        for rank, (sheet, row, col) in WEAPON_RANK_SPRITES.items():
            name = f"w_{rank.replace('-','m').replace('+','p')}"
            if name in uploaded:
                print(f'    "{rank}": "{uploaded[name]}",')

        print("\nArmor emoji map:")
        for rank, (sheet, row, col) in ARMOR_RANK_SPRITES.items():
            name = f"a_{rank.replace('-','m').replace('+','p')}"
            if name in uploaded:
                print(f'    "{rank}": "{uploaded[name]}",')

        await client.close()

    await client.start(TOKEN)


asyncio.run(main())
