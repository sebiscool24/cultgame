"""
Re-upload script: cuts equipment icons, removes sheet backgrounds, auto-centers each sprite, re-uploads.
"""

import asyncio
import io
import os
import discord
from PIL import Image
import numpy as np

SHEET_CONFIGS = {
    "equipment": {
        "file": "assets/equipment_icons_sheet.png",
        "base_size": 1024,
        "x_centers": [137, 205],
        "weapon_y": [75, 151, 226, 302, 377, 453],
        "armor_y": [586, 662, 738, 814, 890, 966],
        "cell": 70,
        "content_scale": 1.0,
    },
}

WEAPON_RANK_SPRITES = {
    "F":  ("equipment", "weapon", 0, 0),
    "E":  ("equipment", "weapon", 0, 1),
    "D-": ("equipment", "weapon", 1, 0),
    "D":  ("equipment", "weapon", 1, 1),
    "D+": ("equipment", "weapon", 2, 0),
    "C-": ("equipment", "weapon", 2, 1),
    "C":  ("equipment", "weapon", 3, 0),
    "C+": ("equipment", "weapon", 3, 1),
    "B-": ("equipment", "weapon", 4, 0),
    "B":  ("equipment", "weapon", 4, 1),
    "B+": ("equipment", "weapon", 5, 0),
    "A-": ("equipment", "weapon", 5, 1),
}

ARMOR_RANK_SPRITES = {
    "F":  ("equipment", "armor", 0, 0),
    "E":  ("equipment", "armor", 0, 1),
    "D-": ("equipment", "armor", 1, 0),
    "D":  ("equipment", "armor", 1, 1),
    "D+": ("equipment", "armor", 2, 0),
    "C-": ("equipment", "armor", 2, 1),
    "C":  ("equipment", "armor", 3, 0),
    "C+": ("equipment", "armor", 3, 1),
    "B-": ("equipment", "armor", 4, 0),
    "B":  ("equipment", "armor", 4, 1),
    "B+": ("equipment", "armor", 5, 0),
    "A-": ("equipment", "armor", 5, 1),
}


def remove_background(img):
    """Remove edge-connected dark sheet background and replace with transparency."""
    img = img.convert("RGBA")
    data = np.array(img)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    brightness = (r.astype(int) + g.astype(int) + b.astype(int)) / 3
    bg_mask = (brightness < 50) & (a > 0)

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
    alpha = data[:,:,3]
    alpha[(brightness < 30) & (alpha > 0)] = 0
    data[:,:,3] = alpha
    return Image.fromarray(data)


def remove_corner_fragments(img):
    """Remove small neighbor fragments while keeping detached sprite details."""
    img = img.convert("RGBA")
    data = np.array(img)
    alpha = data[:,:,3]
    mask = alpha > 0
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components = []

    for start_y in range(height):
        for start_x in range(width):
            if seen[start_y, start_x] or not mask[start_y, start_x]:
                continue
            stack = [(start_y, start_x)]
            seen[start_y, start_x] = True
            pixels = []
            while stack:
                y, x = stack.pop()
                pixels.append((y, x))
                for next_y in range(max(0, y - 1), min(height, y + 2)):
                    for next_x in range(max(0, x - 1), min(width, x + 2)):
                        if not seen[next_y, next_x] and mask[next_y, next_x]:
                            seen[next_y, next_x] = True
                            stack.append((next_y, next_x))
            components.append(pixels)

    if not components:
        return img

    min_area = max(10, int(height * width * 0.0015))
    keep = np.zeros_like(mask, dtype=bool)
    for component in components:
        area = len(component)
        min_y = min(pixel[0] for pixel in component)
        max_y = max(pixel[0] for pixel in component)
        min_x = min(pixel[1] for pixel in component)
        max_x = max(pixel[1] for pixel in component)
        touches_corner = (
            (min_y <= 1 and min_x <= 1) or
            (min_y <= 1 and max_x >= width - 2) or
            (max_y >= height - 2 and min_x <= 1) or
            (max_y >= height - 2 and max_x >= width - 2)
        )
        if area >= min_area and not touches_corner:
            for y, x in component:
                keep[y, x] = True

    data[~keep] = [0, 0, 0, 0]
    return Image.fromarray(data)


def cut_sprite(sheet_name, item_type, row, col):
    cfg = SHEET_CONFIGS[sheet_name]
    img = Image.open(cfg["file"]).convert("RGBA")

    scale = img.width / cfg["base_size"]
    center_x = round(cfg["x_centers"][col] * scale)
    center_y = round(cfg[f"{item_type}_y"][row] * scale)
    half = round((cfg["cell"] * scale) / 2)
    sprite = img.crop((center_x - half, center_y - half, center_x + half, center_y + half))

    sprite = remove_background(sprite)
    sprite = remove_corner_fragments(sprite)

    bbox = sprite.getbbox()
    if bbox:
        sprite = sprite.crop(bbox)

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

        for emoji_name, (sheet, item_type, row, col) in all_sprites.items():
            try:
                image_data = cut_sprite(sheet, item_type, row, col)
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
