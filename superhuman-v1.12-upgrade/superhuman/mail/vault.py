"""Credential encryption. Key lives outside app/ and its deployment bundles."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken


def key_path():
    path=Path(os.environ.get('SUPERHUMAN_MAIL_KEY_FILE', str(Path.home() / '.config/superhuman/mail.key'))).expanduser()
    if path.resolve().is_relative_to((Path.cwd()/'data').resolve()):
        raise ValueError('Store the mail encryption key outside app/data so deployment bundles cannot include it')
    return path


def cipher(create=False):
    path = key_path()
    if not path.exists():
        if not create:
            raise ValueError('Mail encryption key missing. Restore your private key backup; do not replace it.')
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(Fernet.generate_key())
    if path.is_symlink() or not path.is_file() or (os.name != 'nt' and path.stat().st_mode & 0o077):
        raise ValueError('Mail key must be a regular private file with permissions 600')
    return Fernet(path.read_bytes().strip())


def seal(value):
    return cipher().encrypt(json.dumps(value).encode()).decode()


def open_secret(value):
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, UnicodeError, json.JSONDecodeError):
        raise ValueError('Mail credential cannot be decrypted with this key') from None
