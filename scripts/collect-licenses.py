"""Collect panel dependency licenses; retain the existing native worker license corpus."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
packages = {}
for manifest, target in [(ROOT / 'extension/Cargo.toml','wasm32-unknown-unknown')]:
    metadata = json.loads(subprocess.check_output(['cargo','metadata','--locked','--offline','--format-version','1','--manifest-path',str(manifest),'--filter-platform',target], text=True, encoding='utf-8'))
    nodes={node['id']:node for node in metadata['resolve']['nodes']}
    included=set(); pending=[metadata['resolve']['root']]
    while pending:
        current=pending.pop()
        if current not in included:
            included.add(current); pending.extend(nodes[current]['dependencies'])
    for package in metadata['packages']:
        if package['id'] in included: packages[package['id']] = package
parts = ['Pinned Rust dependency licenses. Includes private PhotoCraft SDK/API source licenses.\n']
for package in sorted(packages.values(), key=lambda p:(p['name'],p['version'])):
    folder = Path(package['manifest_path']).parent
    if folder in [ROOT, ROOT/'extension']:
        continue
    files = sorted(p for p in folder.rglob('*') if p.is_file() and not any(x in p.relative_to(folder).parts for x in ['target','dist','.git','vendor']) and p.name.lower().startswith(('license','licence','copying','copyright')))
    if not files:
        raise RuntimeError(f'Missing license text for {package["name"]}')
    parts.append(f'\n{"="*72}\n{package["name"]} {package["version"]}\nLicense: {package.get("license")}\nSource: {package.get("repository")}\n')
    for path in files:
        parts.append(f'\n--- {path.relative_to(folder).as_posix()} ---\n{path.read_text(encoding="utf-8",errors="replace")}\n')
(ROOT / 'licenses').mkdir(exist_ok=True)
(ROOT / 'licenses/rust-panel-dependencies.txt').write_text('\n'.join(parts), encoding='utf-8')
print(f'Collected license texts for {len(packages)} pinned Rust packages.')
