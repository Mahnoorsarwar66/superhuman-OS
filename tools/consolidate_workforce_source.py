"""Promote a verified source capture locally, preserving every replaced source file."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from .workforce_baseline import sha256, source_inventory
except ImportError:
    from workforce_baseline import sha256, source_inventory


def consolidate(root, captured, expected_local, backup):
    root, captured, backup = Path(root).resolve(), Path(captured).resolve(), Path(backup).resolve()
    if not backup.is_relative_to(root / '.workforce'):
        raise ValueError('Backup must be inside this checkout/.workforce')
    if backup.exists():
        raise ValueError('Choose a new backup directory')
    if source_inventory(root) != expected_local['source_files']:
        raise ValueError('Local source changed since inventory; reconcile before consolidation')
    provenance = json.loads((captured / 'source-provenance.json').read_text(encoding='utf-8'))
    files = source_inventory(captured)
    if not files or files != provenance['source_files']:
        raise ValueError('Captured source no longer matches its provenance')
    if set(expected_local['source_files']) - set(files):
        raise ValueError('Local-only source requires explicit reconciliation')
    if any(record.get('syntax') == 'fail' for record in files.values()):
        raise ValueError('Captured source has syntax errors')
    backup.mkdir(parents=True, exist_ok=False)
    if (root / 'source-provenance.json').is_file():
        shutil.copy2(root / 'source-provenance.json', backup / 'source-provenance.json')
    for name in expected_local['source_files']:
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, dest)
    changed = []
    try:
        for name, record in files.items():
            dest = root / name
            if not dest.resolve().is_relative_to(root):
                raise ValueError('Source destination escapes checkout: ' + name)
            if dest.exists() and sha256(dest.read_bytes()) == record['sha256']:
                continue
            # Recheck each target immediately before replacing it.
            before = expected_local['source_files'].get(name)
            if (dest.exists() and (before is None or sha256(dest.read_bytes()) != before['sha256'])):
                raise ValueError('Local source changed during consolidation: ' + name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name('.' + dest.name + '.workforce.tmp')
            if temporary.exists():
                raise ValueError('Temporary source path already exists: ' + name)
            temporary.write_bytes((captured / name).read_bytes())
            temporary.replace(dest)
            changed.append(name)
        if source_inventory(root) != files:
            raise ValueError('Consolidated source did not verify')
    except Exception:
        for name in reversed(changed):
            saved = backup / name
            if saved.exists():
                shutil.copy2(saved, root / name)
            else:
                (root / name).unlink()
        raise
    receipt = {'before': expected_local['source_fingerprint'],
               'before_files': expected_local['source_files'],
               'server_source_fingerprint': provenance['server_source_fingerprint'],
               'changed_files': changed, 'source_files': files,
               'scope': 'local source consolidation; no database migrations or deployment'}
    provenance_raw = (json.dumps(provenance, indent=2) + '\n').encode('utf-8')
    receipt['installed_provenance_sha256'] = sha256(provenance_raw)
    (backup / 'consolidation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    (root / 'source-provenance.json').write_bytes(provenance_raw)
    return receipt


def restore(root, backup):
    root, backup = Path(root).resolve(), Path(backup).resolve()
    if not backup.is_relative_to(root / '.workforce'):
        raise ValueError('Backup must be inside this checkout/.workforce')
    receipt = json.loads((backup / 'consolidation.json').read_text(encoding='utf-8'))
    if source_inventory(root) != receipt['source_files']:
        raise ValueError('Consolidated source changed; restore refused to preserve edits')
    if source_inventory(backup) != receipt['before_files']:
        raise ValueError('Backup source changed; restore refused')
    if not set(receipt['changed_files']) <= set(receipt['source_files']):
        raise ValueError('Invalid restore file list')
    provenance = root / 'source-provenance.json'
    if sha256(provenance.read_bytes()) != receipt['installed_provenance_sha256']:
        raise ValueError('Source provenance changed; restore refused')
    for name in receipt['changed_files']:
        if not (root / name).resolve().is_relative_to(root):
            raise ValueError('Restore destination escapes checkout')
    for name in reversed(receipt['changed_files']):
        saved = backup / name
        if saved.is_file():
            shutil.copy2(saved, root / name)
        else:
            (root / name).unlink()
    if (backup / 'source-provenance.json').is_file():
        shutil.copy2(backup / 'source-provenance.json', provenance)
    else:
        provenance.unlink()
    if source_inventory(root) != receipt['before_files']:
        raise ValueError('Restored source did not verify')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--captured', type=Path)
    parser.add_argument('--expected-local', type=Path)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--restore', action='store_true', help='Restore unchanged consolidated source only')
    args = parser.parse_args()
    if args.restore:
        if args.captured or args.expected_local:
            parser.error('Restore takes only --root and --backup')
        restore(args.root, args.backup)
        print('Prior local source restored; data and configuration unchanged')
        return
    if not args.captured or not args.expected_local:
        parser.error('Consolidation requires --captured and --expected-local')
    expected = json.loads(args.expected_local.read_text(encoding='utf-8-sig'))
    receipt = consolidate(args.root, args.captured, expected, args.backup)
    print(f'Consolidated {len(receipt["source_files"])} source files; '
          f'{len(receipt["changed_files"])} changed or added. Backup: {args.backup}')


if __name__ == '__main__':
    main()
