"""Project-local draft uploads; no credential copies or output artifacts."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from .tools.wp_client import WPCredentials, WPClient, WPError
from .tools.client_config import ClientConfig
from . import upload_blog

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

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--expected-site')
    parser.add_argument('--doc')
    parser.add_argument('--brand')
    parser.add_argument('--title')
    parser.add_argument('--media-dir')
    parser.add_argument('--editor', choices=['gutenberg','classic','elementor'], default='gutenberg')
    parser.add_argument('--prepared-stdin', action='store_true')
    args = parser.parse_args(argv)
    try:
        root, path, data = prepare(args.project_dir)
        if data is None:
            print(json.dumps(dict(status='needs_credentials', path=str(path), message='Fill this file locally, then run again.')))
            return 2
        if not args.expected_site:
            raise ValueError('Provide the intended site from verified project/task records.')
        from .tools.wp_client import _normalize_site_root
        if _normalize_site_root(args.expected_site) != _normalize_site_root(data['site_url']):
            raise ValueError('Credential site does not match the intended project/task site.')
        for value in [args.doc, args.media_dir]:
            if value and not Path(value).resolve(strict=True).is_relative_to(root):
                raise ValueError('Input must be within the selected project directory.')
        if not args.doc and not args.prepared_stdin:
            raise ValueError('Select the article to upload.')
        creds = WPCredentials(**{k:data[k] for k in TEMPLATE})
        WPClient(creds)._request('GET', 'users/me', action='authenticate')
        cfg = ClientConfig('project', 'Project', urlsplit(creds.site_url).hostname, creds.site_url, str(path), args.editor)
        if args.prepared_stdin:
            import sys
            payload = json.load(sys.stdin)
            for block in payload.get('body', []):
                if block.get('kind') == 'image' and not Path(block['src']).resolve(strict=True).is_relative_to(root):
                    raise ValueError('Image must be inside the project directory.')
            result = upload_blog.upload_prepared(payload, cfg)
        elif Path(args.doc).suffix.lower() == '.html':
            result = upload_blog.upload_html(Path(args.doc).read_text(), cfg, title=args.title, fallback_title=Path(args.doc).stem, media_dir=args.media_dir)
        else:
            result = upload_blog.upload_blog(args.doc, cfg, brand=args.brand, media_dir=args.media_dir)
        from dataclasses import asdict
        print(json.dumps(dict(status='uploaded', **asdict(result))))
        return 0
    except WPError as exc:
        print(json.dumps(dict(status='failed', message=str(exc))))
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps(dict(status='invalid_input', message='Check the local credential file, intended site, article format and project paths. No credentials are printed.')))
    return 1

if __name__ == '__main__':
    raise SystemExit(main())
