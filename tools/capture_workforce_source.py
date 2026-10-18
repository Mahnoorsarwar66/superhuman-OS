"""Capture inventoried server source into a new local staging directory (WF01)."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


REMOTE_CAPTURE = r'''
import hashlib, io, json, sys, zipfile
from pathlib import Path
root = Path('/home/superhuman/app').resolve()
archive = io.BytesIO()
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
    for path in sorted((root / 'superhuman').rglob('*')):
        if (not path.is_file() or path.is_symlink() or
            not path.resolve().is_relative_to(root) or '__pycache__' in path.parts or
            (path.suffix not in ('.py', '.js', '.css', '.html', '.png', '.svg', '.ico', '.woff2') and
             path.relative_to(root).as_posix() != 'superhuman/organisation/seed.json')):
            continue
        output.writestr(path.relative_to(root).as_posix(), path.read_bytes())
sys.stdout.buffer.write(archive.getvalue())
'''


def verified_members(raw, report):
    """Validate all bytes before creating destination files; no zip extraction API."""
    expected = report['source_files']
    found = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            name = member.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or '\\' in name or
                    not name.startswith('superhuman/') or
                    (path.suffix not in ('.py', '.js', '.css', '.html', '.png', '.svg', '.ico', '.woff2') and
                     name != 'superhuman/organisation/seed.json') or name in found):
                raise ValueError('Unsafe or duplicate archive member')
            if member.file_size > 20 * 1024 * 1024:
                raise ValueError('Source member exceeds capture limit')
            data = archive.read(member)
            if name not in expected or hashlib.sha256(data).hexdigest() != expected[name]['sha256']:
                raise ValueError('Source changed since inventory: ' + name)
            found[name] = data
    if set(found) != set(expected):
        raise ValueError('Capture does not contain the complete inventoried source')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--host', default='root@167.71.196.20')
    args = parser.parse_args()
    if args.destination.exists():
        parser.error('Choose a new staging directory; existing source is never overwritten')
    report = json.loads(args.report.read_text(encoding='utf-8-sig'))
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o',
               'ConnectTimeout=15', '-i', str(args.key), args.host,
               '/home/superhuman/app/.venv/bin/python -']
    result = subprocess.run(command, input=REMOTE_CAPTURE.encode(), capture_output=True,
                            timeout=120, check=True)
    files = verified_members(result.stdout, report)
    args.destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = args.destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (args.destination / 'source-provenance.json').write_text(json.dumps({
        'scope': 'source only; no data, secrets, installation manifests or service changes',
        'server_source_fingerprint': report['source_fingerprint'],
        'source_files': report['source_files'], 'host': args.host,
        'root': '/home/superhuman/app', 'runtime_version': 'not attested by source capture',
    }, indent=2) + '\n', encoding='utf-8')
    print(f'Captured and hash-verified {len(files)} source files into {args.destination}')


if __name__ == '__main__':
    main()
