from pathlib import Path

from PIL import Image


SOURCE = Path("assets/traits/trait_icons_sheet.png")
OUTPUT_DIR = Path("assets/traits/icons")


def remove_edge_background(image):
    image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    stack = []
    visited = set()

    def is_background(x, y):
        r, g, b, a = pixels[x, y]
        return a > 0 and max(r, g, b) < 35

    for x in range(width):
        if is_background(x, 0):
            stack.append((x, 0))
        if is_background(x, height - 1):
            stack.append((x, height - 1))
    for y in range(height):
        if is_background(0, y):
            stack.append((0, y))
        if is_background(width - 1, y):
            stack.append((width - 1, y))

    while stack:
        x, y = stack.pop()
        if (x, y) in visited or not is_background(x, y):
            continue
        visited.add((x, y))
        pixels[x, y] = (0, 0, 0, 0)
        if x > 0:
            stack.append((x - 1, y))
        if x < width - 1:
            stack.append((x + 1, y))
        if y > 0:
            stack.append((x, y - 1))
        if y < height - 1:
            stack.append((x, y + 1))

    return image


def crop_trait_icons():
    sheet = Image.open(SOURCE).convert("RGBA")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    column_centers = [200, 306, 412, 518, 624, 730, 836, 942, 1050, 1156]
    row_centers = [74, 180, 313, 418, 555, 668, 808, 926, 1065, 1180]
    cell_size = 104
    output_size = 96

    for existing_icon in OUTPUT_DIR.glob("*.png"):
        existing_icon.unlink()

    for tier_index in range(1, 6):
        for row_index in range(2):
            row_center = row_centers[(tier_index - 1) * 2 + row_index]
            for col_index, column_center in enumerate(column_centers):
                icon_index = row_index * 10 + col_index + 1
                x = column_center - cell_size // 2
                y = row_center - cell_size // 2
                crop = sheet.crop((x, y, x + cell_size, y + cell_size))
                crop = remove_edge_background(crop)
                bbox = crop.getbbox()
                if bbox:
                    crop = crop.crop(bbox)

                canvas = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
                max_dim = max(crop.width, crop.height)
                scale = 84 / max_dim if max_dim else 1
                resized = crop.resize(
                    (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                    Image.LANCZOS,
                )
                canvas.alpha_composite(
                    resized,
                    ((output_size - resized.width) // 2, (output_size - resized.height) // 2),
                )
                canvas.save(OUTPUT_DIR / f"tier_{tier_index}_{icon_index:02}.png")


if __name__ == "__main__":
    crop_trait_icons()
    print(f"Generated {len(list(OUTPUT_DIR.glob('*.png')))} trait icons")