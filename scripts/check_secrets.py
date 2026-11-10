"""Check publishable files without printing matching secret values.

Uses tracked Git files when available. In an unpacked source archive, scans source
files while excluding local runtime directories. This is a targeted safeguard,
not a claim to detect every possible credential format.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', 'secrets', 'credentials', 'data', 'backups', 'exports', 'thumbs'}
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'Google OAuth secret': re.compile(r'GOCSPX-[A-Za-z0-9_-]{15,}'),
    'Google API key': re.compile(r'AIza[0-9A-Za-z_-]{30,}'),
    'AWS access key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    'service-account private key JSON': re.compile(r'"private_key"\s*:\s*"'),
}


def files():
    result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if result.returncode == 0 and Path(result.stdout.strip()).resolve() == ROOT:
        paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
        return [ROOT / p for p in paths if p]
    return [p for p in ROOT.rglob('*') if p.is_file() and not any(part in SKIP for part in p.relative_to(ROOT).parts)
            and (not p.name.startswith('.env') or p.name == '.env.example') and p.suffix not in {'.onnx', '.pyc'}]


def main():
    findings = []
    checked = 0
    for path in files():
        relative = path.relative_to(ROOT)
        if (any(part in SKIP - {'.git'} for part in relative.parts)
                or (path.name.startswith('.env') and path.name != '.env.example')
                or path.name in {'oauth.json', 'token_key', 'service-account.json'}
                or path.suffix in {'.pem', '.key', '.p12', '.pfx', '.sqlite3', '.db', '.zip', '.tar'}):
            findings.append(f'{relative}: credential/runtime file must not be published')
            continue
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            findings.append(f'{relative}: unexpected binary file; review before publishing')
            continue
        checked += 1
        for name, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f'{relative}: possible {name}')
    if findings:
        print('\n'.join(findings))
        raise SystemExit(1)
    print(f'Credential-pattern scan passed for {checked} source files. No secret values printed.')


if __name__ == '__main__':
    main()
