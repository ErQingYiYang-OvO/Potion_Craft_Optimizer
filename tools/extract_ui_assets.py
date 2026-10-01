"""Extract game's Simplified Chinese labels and original UI sprites, read-only."""
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools/.vendor'))
import UnityPy
from PIL import Image, ImageChops


def main():
    game = Path(sys.argv[1])
    env = UnityPy.load(*map(str, (game / 'StreamingAssets/aa/StandaloneWindows64').glob('*assets_all*.bundle')))
    objects = list(env.objects)
    by_id = {obj.path_id: obj for obj in objects}
    table = next(obj.read().m_Script for obj in objects
                 if obj.type.name == 'TextAsset' and obj.peek_name() == 'LocalizationData')
    if isinstance(table, bytes):
        table = table.decode('utf-8')
    rows = csv.DictReader(io.StringIO(table), delimiter='\t')
    translations = {row['key']: row['zh'] for row in rows if row.get('key')}
    manifest = {'gameVersion': '2.0.2', 'locale': 'zh',
                'source': 'Installed game LocalizationData, Ingredient.inventoryIconObject, PotionEffect.icon',
                'ingredients': {}, 'effects': {}}
    settings = json.loads((ROOT / 'data/brewing_settings.json').read_text(encoding='utf-8'))
    contour_ref = settings['RecipeMapManagerSettings']['iconContourDefaultColor']
    contour = by_id[contour_ref['m_PathID']].read_typetree()['color']
    for group, filename, field, prefix in [
        ('ingredients', 'ingredients_full.json', 'ingredient', 'ingredient_'),
        ('effects', 'potion_effects_full.json', 'data', 'effect_'),
    ]:
        output = ROOT / 'playground/assets' / group
        output.mkdir(parents=True, exist_ok=True)
        for entry in json.loads((ROOT / 'data' / filename).read_text(encoding='utf-8')):
            data = entry[field]
            name = data['m_Name']
            if name == 'Default':
                continue
            zh = translations.get(prefix + name)
            if not zh:
                raise ValueError(f'Missing Chinese name: {name}')
            pointer = data['inventoryIconObject' if group == 'ingredients' else 'icon']
            sprite = by_id[pointer['m_PathID']]
            if group == 'ingredients':
                image = sprite.read().image
            else:
                # Icon.GetSprite / SpriteMaker: tint each layer, center-align,
                # then alpha-compose textures, contour, and scratches.
                icon = sprite.read_typetree()
                layers = list(zip(icon['textures'], icon['defaultIconColors'])) + [
                    (icon['contourTexture'], contour),
                    (icon['scratchesTexture'], dict(r=1, g=1, b=1, a=1))]
                image = None
                for ref, color in layers:
                    layer = by_id[ref['m_PathID']].read().image.convert('RGBA')
                    tint = Image.new('RGBA', layer.size, tuple(round(color[k]*255) for k in 'rgba'))
                    layer = ImageChops.multiply(layer, tint)
                    if image is None:
                        image = layer
                    else:
                        aligned = Image.new('RGBA', image.size)
                        aligned.paste(layer, ((image.width-layer.width)//2, (image.height-layer.height)//2))
                        image = Image.alpha_composite(image, aligned)
            image.thumbnail((160, 160))
            image.save(output / f'{name}.png')
            manifest[group][name] = {'name': zh, 'icon': f'assets/{group}/{name}.png',
                                     'spriteId': sprite.path_id}
    (ROOT / 'data/ui_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print({group: len(manifest[group]) for group in ('ingredients', 'effects')})
    print({name: data['name'] for name, data in manifest['ingredients'].items()})


if __name__ == '__main__':
    main()
