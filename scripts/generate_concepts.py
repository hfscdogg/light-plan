"""One-time DALL-E 3 image generation for concept visuals.

Generates 15 photorealistic room renders (5 rooms x 3 tiers) and saves
them to backend/app/static/concepts/. Run once, commit the images,
never run again.

Usage:
    OPENAI_API_KEY=sk-xxx python scripts/generate_concepts.py
"""

import os
import sys
import time
from pathlib import Path

from openai import OpenAI

OUTPUT_DIR = Path(__file__).parent.parent / "backend" / "app" / "static" / "concepts"

ROOMS = {
    "kitchen": "a residential kitchen with an island, white cabinets, walnut countertops and stainless appliances",
    "master_bedroom": "a spacious master bedroom with a king bed, neutral bedding, nightstands and a sitting area",
    "living": "a modern living room with a sectional sofa, coffee table, built-in shelving and large windows",
    "master_bathroom": "a master bathroom with a double vanity, freestanding tub, walk-in shower and natural stone tile",
    "dining": "a dining room with a rectangular table for six, upholstered chairs and a sideboard",
}

TIERS = {
    "good": {
        "label": "Builder Grade",
        "lighting_desc": (
            "basic builder-grade lighting: standard 4-inch recessed cans in a simple grid pattern, "
            "a single basic ceiling fixture, no accent or decorative lighting, flat even illumination "
            "with no layering or visual depth, standard warm white 2700K throughout"
        ),
    },
    "better": {
        "label": "Designer Mid-Range",
        "lighting_desc": (
            "designer mid-range lighting with visible layering: sleek 2-inch recessed downlights "
            "in an optimized grid, decorative pendants or a statement chandelier as a focal point, "
            "wall sconces adding accent glow, warm under-cabinet LED strips in the kitchen, "
            "dimmable warm light between 2700-3000K creating depth and warmth"
        ),
    },
    "best": {
        "label": "Premium Smart Lighting",
        "lighting_desc": (
            "premium full-spectrum smart lighting with dramatic layering: minimal-profile Ketra "
            "recessed downlights with tunable color temperature, architectural wall wash fixtures "
            "creating dramatic accent effects, decorative designer pendants with warm metallic "
            "finishes, task lighting in work areas, landscape lighting visible through windows "
            "at dusk, rich dimensional light quality with color temperature shifting from warm "
            "amber at low levels to crisp white at full, magazine-quality atmosphere"
        ),
    },
}

STYLE_SUFFIX = (
    "Photorealistic interior photograph, twilight/evening setting with lights on and dusk visible "
    "through windows. Warm residential atmosphere. Clean minimal composition emphasizing the "
    "lighting design. Neutral palette: white walls, warm wood tones, charcoal and brass accents. "
    "Camera at 3/4 angle, eye level, wide-angle lens. No people. High-end architectural "
    "photography style. 16:9 aspect ratio."
)


def generate_image(client: OpenAI, prompt: str, output_path: Path) -> bool:
    """Generate a single image and save it."""
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="hd",
            n=1,
        )
        image_url = response.data[0].url

        # Download the image
        import urllib.request
        urllib.request.urlretrieve(image_url, str(output_path))
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY environment variable")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total = len(ROOMS) * len(TIERS)
    generated = 0
    failed = 0

    print(f"Generating {total} concept images...")
    print(f"Output: {OUTPUT_DIR}\n")

    for room_key, room_desc in ROOMS.items():
        for tier_key, tier_info in TIERS.items():
            filename = f"{room_key}_{tier_key}.jpg"
            output_path = OUTPUT_DIR / filename

            if output_path.exists():
                print(f"  SKIP {filename} (already exists)")
                generated += 1
                continue

            prompt = (
                f"Interior of {room_desc}. The room features {tier_info['lighting_desc']}. "
                f"{STYLE_SUFFIX}"
            )

            print(f"  Generating {filename}...")
            if generate_image(client, prompt, output_path):
                generated += 1
                print(f"  SAVED {filename} ({generated}/{total})")
            else:
                failed += 1

            # Rate limit: DALL-E 3 allows ~5 images/min
            time.sleep(13)

    print(f"\nDone: {generated} generated, {failed} failed")
    print(f"Images saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
