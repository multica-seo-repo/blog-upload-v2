"""Upload only: cleaned HTML, explicit title and selected featured image to a WordPress draft."""
import argparse
import json
from urllib.parse import urlsplit
from .credentials import prepare, TEMPLATE
from .tools.wp_client import WPCredentials, WPClient, WPError, _normalize_site_root
from .upload_blog import validate_inputs, upload_html, InputError

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for flag in ('project-dir','expected-site','doc','title','featured-image'):
        parser.add_argument('--'+flag, required=True)
    args = parser.parse_args(argv)
    result = {'status':'failed','stage':'validate','warnings':[]}
    try:
        root, html, image = validate_inputs(args.project_dir,args.doc,args.title,args.featured_image)
        site = urlsplit(args.expected_site)
        if site.scheme!='https' or not site.hostname or site.username or site.password or site.query or site.fragment:
            raise InputError('Provide the verified plain HTTPS site URL.')
        result['stage'] = 'credentials'
        root, path, data = prepare(root)
        if data is None:
            result.update(status='needs_credentials',path=str(path),message='Fill this file locally, then run again.')
            print(json.dumps(result)); return 2
        if _normalize_site_root(args.expected_site)!=_normalize_site_root(data['site_url']):
            raise InputError('Credential site does not match the intended site.')
        creds = WPCredentials(**{k:data[k] for k in TEMPLATE})
        wp = WPClient(creds)
        result['stage'] = 'authenticate'
        wp._request('GET','users/me', action='authenticate')
        upload_html(html,args.title,image,wp,result)
    except InputError as exc:
        result.update(status='invalid_input' if result['stage']=='validate' else 'incomplete',message=str(exc))
    except WPError as exc:
        result.update(status='incomplete' if result.get('media_id') or result.get('post_id') else 'failed',message=str(exc))
    except (ValueError,OSError,KeyError,TypeError,AttributeError):
        result.update(status='incomplete' if result.get('media_id') or result.get('post_id') else 'invalid_input',message='Input, credential or response validation failed. No credentials are printed.')
    if result['status'] not in {'uploaded','needs_credentials'} and result['stage'] in {'upload_media','create_post','verify'}:
        result['warnings'].append('Inspect remote state before retrying; no automatic retry or cleanup was performed.')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='uploaded' else 1

if __name__=='__main__':
    raise SystemExit(main())
