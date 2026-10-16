"""Keep the independent panel's model choices aligned with its pinned catalog."""
import argparse
import json
from pathlib import Path


def sync(root, check=False):
    manifest_path = root / 'authoring.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    catalog = json.loads((root / 'runtime/model-catalog.json').read_text(encoding='utf-8'))
    choices = []
    for model in catalog['models']:
        label = model['label'] + ': ' + model['description'].rstrip('.')
        if not 1 <= len(label) <= 128 or any(ord(char) < 32 for char in label):
            raise ValueError('Model explanation exceeds panel label bounds: ' + model['id'])
        choices.append(label)
    if not 2 < len(choices) <= 32 or len(choices) != len(set(choices)):
        raise ValueError('Model choices must be unique and bounded')
    field = next(field for field in manifest['descriptor']['panel']['fields'] if field['id'] == 'model')
    expected = dict(field, options=choices, default=choices[0])
    if check:
        if field != expected:
            raise ValueError('Panel choices changed. Run scripts/sync-panel-models.py, then rebuild.')
        print(f'Panel and catalog agree: {len(choices)} models')
        return
    field.update(expected)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Updated {len(choices)} model choices')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    sync(Path(__file__).resolve().parent.parent, args.check)
