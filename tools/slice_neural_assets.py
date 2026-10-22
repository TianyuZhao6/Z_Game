"""Losslessly separate the transparent, reference-derived production atlases.

The supplied concept sheets are flattened. Image generation reconstructs their
cutouts first; this step only slices the resulting pixels, retaining alpha.
"""
import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STRUCTURES = ('basalt-low', 'basalt-spire', 'masonry-dark', 'basalt-rooted',
              'masonry-fragile', 'masonry-chipped', 'masonry-stump', 'rubble')
VESSELS = ('node-small', 'node-medium', 'node-large', 'node-damaged',
           'junction-y', 'junction-four', 'capillary', 'terminal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--structures', type=Path, required=True)
    parser.add_argument('--vessels', type=Path, required=True)
    args = parser.parse_args()
    destination = ROOT/'assets'/'sprites'/'environment'/'neural-parts-v2'
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest.update(derivation='AI-reconstructed cutouts from supplied references; lossless grid slicing, not literal extraction from flattened concepts.',
                    parts=[])
    for source, names in ((args.structures, STRUCTURES), (args.vessels, VESSELS)):
        atlas = Image.open(source)
        if atlas.mode != 'RGBA' or atlas.getchannel('A').getextrema()[0] != 0:
            raise ValueError('A genuinely transparent RGBA atlas is required')
        w, h = atlas.width//4, atlas.height//2
        for index, name in enumerate(names):
            x, y = index%4*w, index//4*h
            image = atlas.crop((x, y, x+w, y+h))
            image.save(destination/f'{name}.png')
            manifest['parts'].append({'file': f'{name}.png', 'atlas': source.name,
                                      'source_rect': [x,y,w,h]})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
