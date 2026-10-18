"""Read-only host metadata for WF01; no configuration values or process arguments."""
import argparse
import ast
import importlib.metadata
import json
from pathlib import Path
import subprocess


def inventory(root):
    root = Path(root).resolve()
    services = {}
    for name in ('superhuman-web.service', 'superhuman-worker.service'):
        try:
            result = subprocess.run(['systemctl', 'show', name,
                '--property=User,WorkingDirectory,FragmentPath,ActiveState,SubState'],
                capture_output=True, text=True, timeout=5, check=True)
            services[name] = dict(line.split('=', 1) for line in result.stdout.splitlines()
                                  if '=' in line)
        except (OSError, subprocess.SubprocessError):
            services[name] = {'inspection': 'unavailable'}
    declared_versions = {}
    for relative in ('superhuman/hosted/boundary.py', 'superhuman/repairs/__init__.py'):
        path = root / relative
        if path.is_file():
            tree = ast.parse(path.read_bytes())
            versions = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if (isinstance(key, ast.Constant) and key.value == 'version'
                                and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                            versions.add(value.value)
                if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str) and any(
                            isinstance(target, ast.Name) and target.id in ('VERSION', '__version__')
                            for target in node.targets)):
                    versions.add(node.value.value)
            declared_versions[relative] = sorted(versions)
    config = root / 'data/hosted/config.json'
    configuration_schema = 'not found'
    if config.is_file():
        value = json.loads(config.read_text(encoding='utf-8'))
        configuration_schema = {key: type(item).__name__ for key, item in value.items()}
    return {'services': services, 'declared_source_versions': declared_versions,
            'configuration_schema': configuration_schema,
            'installed_distributions': dict(sorted(
                (item.metadata['Name'], item.version) for item in importlib.metadata.distributions())),
            'scope': 'host metadata; source version is not a process attestation',
            'configuration_values': 'not reported', 'provider_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.root), indent=2, sort_keys=True))
