"""Generate a session key locally; never print or overwrite an existing key."""
import base64
import os
import secrets
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / 'secrets'
folder.mkdir(mode=0o750, exist_ok=True)
folder.chmod(0o750)
key = folder / 'token_key'
if not key.exists():
    with key.open('xb') as output:
        output.write(base64.urlsafe_b64encode(secrets.token_bytes(32)) + b'\n')
    key.chmod(0o640)
    print('Created secrets/token_key; keep this file private and back it up securely.')
else:
    print('Existing secrets/token_key preserved.')
if hasattr(os, 'geteuid') and os.geteuid() == 0:
    os.chown(folder, 0, 10001)
    os.chown(key, 0, 10001)
    key.chmod(0o640)
print('Place your Service Account JSON in secrets/service-account.json; do not commit it.')
