"""Project-local draft uploads; no credential copies or output artifacts."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from .tools.wp_client import WPCredentials, WPClient, WPError

TEMPLATE = dict(site_url='https://your-client-site.com', username='your-wordpress-username', app_password='YOUR-GENERATED-APPLICATION-PASSWORD')

def credential_path(project):
    root = Path(project).resolve(strict=True)
    path = root / 'blog-upload-workspace/data/secrets/_pending.json'
    if not path.resolve().is_relative_to(root):
        raise ValueError('Credential location escapes the project directory.')
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents):
        raise ValueError('Credential location must not use symbolic links.')
    return root, path

def prepare(project):
    root, path = credential_path(project)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return prepare(project)
        with os.fdopen(fd, 'w') as f:
            json.dump(TEMPLATE, f, indent=2)
        return root, path, None
    try:
        with path.open() as f:
            data = json.load(f)
    except (ValueError, OSError):
        raise ValueError('Cannot read valid credential JSON. Correct the local file.') from None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), str) or not data[k].strip() or data[k] == v for k,v in TEMPLATE.items()):
        return root, path, None
    url = urlsplit(data['site_url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('site_url must be a plain HTTPS site URL.')
    if path.stat().st_mode & 0o077:
        path.chmod(0o600)
    return root, path, data

