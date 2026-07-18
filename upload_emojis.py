"""
Re-upload script: removes blue background, auto-centers each sprite, re-uploads.
"""

import asyncio
import io
import os
import discord
from PIL import Image
import numpy as np

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
        "start_x": 249, "start_y": 127,
        "cell_w": 107, "cell_h": 107,
        "step_x": 125, "step_y": 127,
        "content_scale": 1.10,
    },
}

WEAPON_RANK_SPRITES = {
    "F":  ("weapons1", 0, 0),
    "E":  ("weapons1", 0, 1),
    "D-": ("weapons1", 0, 2),
    "D":  ("weapons1", 0, 3),
    "D+": ("weapons1", 0, 4),
    "C-": ("weapons1", 0, 5),
    "C":  ("weapons1", 1, 0),
    "C+": ("weapons1", 1, 1),
    "B-": ("weapons1", 1, 3),
    "B":  ("weapons1", 2, 0),
    "B+": ("weapons1", 2, 3),
    "A-": ("weapons1", 2, 4),
}

ARMOR_RANK_SPRITES = {
    "F":  ("armor", 0, 0),
    "E":  ("armor", 0, 1),
    "D-": ("armor", 0, 2),
    "D":  ("armor", 0, 3),
    "D+": ("armor", 0, 4),
    "C-": ("armor", 1, 0),
    "C":  ("armor", 1, 5),
    "C+": ("armor", 1, 6),
    "B-": ("armor", 2, 1),
    "B":  ("armor", 2, 2),
    "B+": ("armor", 2, 5),
    "A-": ("armor", 4, 6),
}


def remove_background(img):
    """Remove the blue background and replace with transparency."""
    img = img.convert("RGBA")
    data = np.array(img)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    # Blue background is roughly R<160, G>160, B>200
    bg_mask = (r < 170) & (g > 160) & (b > 180) & (b > r + 30)

    height, width = bg_mask.shape
    edge_bg = np.zeros_like(bg_mask, dtype=bool)
    stack = []

    for x in range(width):
        if bg_mask[0, x]:
            stack.append((0, x))
        if bg_mask[height - 1, x]:
            stack.append((height - 1, x))
    for y in range(height):
        if bg_mask[y, 0]:
            stack.append((y, 0))
        if bg_mask[y, width - 1]:
            stack.append((y, width - 1))

    while stack:
        y, x = stack.pop()
        if edge_bg[y, x] or not bg_mask[y, x]:
            continue
        edge_bg[y, x] = True
        if y > 0:
            stack.append((y - 1, x))
        if y < height - 1:
            stack.append((y + 1, x))
        if x > 0:
            stack.append((y, x - 1))
        if x < width - 1:
            stack.append((y, x + 1))

    data[edge_bg] = [0, 0, 0, 0]
    return Image.fromarray(data)


def cut_sprite(sheet_name, row, col):
    cfg = SHEET_CONFIGS[sheet_name]
    img = Image.open(cfg["file"]).convert("RGBA")

    x = cfg["start_x"] + col * cfg.get("step_x", cfg["cell_w"])
    y = cfg["start_y"] + row * cfg.get("step_y", cfg["cell_h"])
    sprite = img.crop((x, y, x + cfg["cell_w"], y + cfg["cell_h"]))

    # Remove blue background
    sprite = remove_background(sprite)

    # Auto-crop to content bounding box, then pad to square
    bbox = sprite.getbbox()
    if bbox:
        sprite = sprite.crop(bbox)

    # Pad to square with transparent border, then fill more of the emoji frame.
    output_size = 64
    content_scale = cfg.get("content_scale", 1.0)
    target_size = min(output_size, int(output_size * content_scale))
    max_dim = max(sprite.width, sprite.height)
    scale = target_size / max_dim if max_dim else 1
    resized = sprite.resize(
        (max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))),
        Image.LANCZOS,
    )

    padded = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
    offset_x = (output_size - resized.width) // 2
    offset_y = (output_size - resized.height) // 2
    padded.paste(resized, (offset_x, offset_y))

    buf = io.BytesIO()
    padded.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN environment variable first.")
    upload_only = os.getenv("EMOJI_UPLOAD_ONLY", "all").lower()

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        guild = client.guilds[0]
        print(f"Uploading to: {guild.name}")

        # Delete old emojis first
        old_names = set()
        if upload_only in {"all", "weapons", "weapon"}:
            for rank in WEAPON_RANK_SPRITES:
                old_names.add(f"w_{rank.replace('-','m').replace('+','p')}")
        if upload_only in {"all", "armor"}:
            for rank in ARMOR_RANK_SPRITES:
                old_names.add(f"a_{rank.replace('-','m').replace('+','p')}")

        weapon_sprites = {}
        armor_sprites = {}
        if upload_only in {"all", "weapons", "weapon"}:
            weapon_sprites = {f"w_{k.replace('-','m').replace('+','p')}": v for k, v in WEAPON_RANK_SPRITES.items()}
        if upload_only in {"all", "armor"}:
            armor_sprites = {f"a_{k.replace('-','m').replace('+','p')}": v for k, v in ARMOR_RANK_SPRITES.items()}

        if not old_names:
            raise RuntimeError("EMOJI_UPLOAD_ONLY must be all, armor, weapon, or weapons.")

        for emoji in guild.emojis:
            if emoji.name in old_names:
                await emoji.delete()
                print(f"  Deleted old: {emoji.name}")
                await asyncio.sleep(0.3)

        # Upload new clean sprites
        uploaded = {}
        all_sprites = {
            **weapon_sprites,
            **armor_sprites,
        }

        for emoji_name, (sheet, row, col) in all_sprites.items():
            try:
                image_data = cut_sprite(sheet, row, col)
                emoji = await guild.create_custom_emoji(name=emoji_name, image=image_data)
                uploaded[emoji_name] = str(emoji)
                print(f"  Uploaded: {emoji_name} -> {emoji}")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  FAILED {emoji_name}: {e}")

        print("\nDone! All icons re-uploaded with transparent backgrounds.")
        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
