"""Upload an unchanged HTML fragment and one selected featured image."""
from html.parser import HTMLParser
from pathlib import Path

class InputError(ValueError):
    pass

class FragmentCheck(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'html', 'head', 'body'}:
            raise InputError('Document wrappers require upstream HTML preparation.')
        self.tags += 1
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
    def handle_endtag(self, tag):
        if tag in {'html', 'head', 'body'}:
            raise InputError('Document wrappers require upstream HTML preparation.')
    def handle_decl(self, decl):
        raise InputError('Full documents require upstream HTML preparation.')

def validate_html(html):
    if not isinstance(html, str) or not html.strip() or '\x00' in html:
        raise InputError('Provide a non-empty UTF-8 HTML article fragment.')
    checker = FragmentCheck(); checker.feed(html); checker.close()
    if not checker.tags:
        raise InputError('Provide HTML markup, not plain text or Markdown.')

def validate_inputs(project, doc, title, image):
    root = Path(project).resolve(strict=True)
    if not root.is_dir(): raise InputError('Project must be a directory.')
    paths = [Path(v).resolve(strict=True) for v in (doc, image)]
    if any(not v.is_relative_to(root) or not v.is_file() for v in paths):
        raise InputError('Input files must be inside the verified project.')
    article, featured = paths
    if article.suffix.lower() not in {'.html', '.htm'}:
        raise InputError('Only cleaned HTML is accepted. Request HTML Brief Cleaner output.')
    if not title.strip(): raise InputError('An explicit post title is required.')
    html = article.read_bytes().decode('utf-8')
    validate_html(html)
    data = featured.read_bytes()
    suffix = featured.suffix.lower()
    valid = ((suffix=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or
             (suffix in {'.jpg','.jpeg'} and data.startswith(b'\xff\xd8\xff')) or
             (suffix=='.gif' and data[:6] in {b'GIF87a',b'GIF89a'}) or
             (suffix=='.webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP'))
    if not valid: raise InputError('Select a PNG, JPEG, GIF or WebP featured-image file.')
    if any(c in featured.name for c in '\r\n"'):
        raise InputError('Unsupported image filename.')
    return root, html, featured

def upload_html(html, title, featured_image, wp, result):
    # Validate public entry point too; no conversion fallback is shipped.
    validate_html(html)
    if not title.strip(): raise InputError('An explicit post title is required.')
    result['stage'] = 'upload_media'
    media = wp.upload_media(featured_image)
    media_id = media.get('id')
    if not isinstance(media_id, int) or isinstance(media_id, bool) or media_id <= 0:
        raise InputError('Media response has no valid ID; inspect remote state before retrying.')
    result['media_id'] = media_id
    payload = dict(title=title, content=html, status='draft', featured_media=media_id)
    result['stage'] = 'create_post'
    post = wp.create_post(payload)
    post_id = post.get('id')
    if not isinstance(post_id, int) or isinstance(post_id, bool) or post_id <= 0:
        raise InputError('Post response has no valid ID; inspect remote state before retrying.')
    result.update(post_id=post_id, edit_url=f'{wp.creds.site_base}/wp-admin/post.php?post={post_id}&action=edit')
    result['stage'] = 'verify'
    saved = wp._request('GET', f'posts/{post_id}', query={'context':'edit'}, action='verify draft')
    checks = {
        'status': saved.get('status') == 'draft',
        'title': isinstance(saved.get('title'),dict) and saved['title'].get('raw') == title,
        'content': isinstance(saved.get('content'),dict) and saved['content'].get('raw') == html,
        'featured_media': saved.get('featured_media') == media_id,
    }
    result['verification'] = checks
    result['warnings'] = [f'{k} differs or cannot be verified.' for k,v in checks.items() if not v]
    result['status'] = 'uploaded' if all(checks.values()) else 'verification_incomplete'
    return result
