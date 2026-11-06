import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from scripts import run
from scripts.tools.wp_client import WPError, WPClient, WPCredentials, NoRedirect

HTML='<h1>Keep title</h1>\r\n<p>中文 &amp; text</p><a href="#x">TOC</a><h2 id="x">X</h2><table style="border:1px solid black"><tr><td>A</td></tr></table>\n'

class UploadTests(unittest.TestCase):
    def setUp(self):
        # All fixtures remain under the authorized governance task directory.
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3])
        self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.doc=self.root/'article.html'; self.doc.write_bytes(HTML.encode())
        self.img=self.root/'feature.png'; self.img.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.wp=Mock(); self.wp.creds.site_base='https://example.test'
        self.wp.upload_media.return_value={'id':7}; self.wp.create_post.return_value={'id':42}
        self.wp._request.side_effect=lambda method,path,**kw: ({'status':'draft','title':{'raw':'Explicit'},'content':{'raw':HTML},'featured_media':7} if path=='posts/42' else {'id':1})
        self.data={'site_url':'https://example.test','username':'test','app_password':'test-only'}
    def invoke(self, extra=None, prepare=True):
        args=['--project-dir',str(self.root),'--expected-site','https://example.test','--doc',str(self.doc),'--title','Explicit','--featured-image',str(self.img)]
        if extra: args+=extra
        with contextlib.ExitStack() as stack:
            self.prep=stack.enter_context(patch.object(run,'prepare',return_value=(self.root,self.root/'unused',self.data))) if prepare else None
            stack.enter_context(patch.object(run,'WPClient',return_value=self.wp))
            out=io.StringIO(); stack.enter_context(contextlib.redirect_stdout(out)); stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            rc=run.main(args)
        return rc,json.loads(out.getvalue())
    def test_verbatim_html_title_draft_and_feature(self):
        rc,r=self.invoke(); self.assertEqual(rc,0); self.assertEqual(r['status'],'uploaded')
        self.assertEqual(self.wp.create_post.call_args.args[0],dict(title='Explicit',content=HTML,status='draft',featured_media=7))
        self.wp.upload_media.assert_called_once_with(self.img)
    def test_docx_and_markdown_rejected_before_credentials(self):
        for ext in ['docx','md','txt']:
            self.doc=self.root/('brief.'+ext);self.doc.write_text('brief')
            rc,r=self.invoke();self.assertEqual(r['status'],'invalid_input');self.prep.assert_not_called()
        self.wp._request.assert_not_called()
    def test_removed_interfaces_rejected(self):
        for flag in ['--prepared-stdin','--brand','--media-dir','--editor']:
            with self.assertRaises(SystemExit):self.invoke([flag,'x'])
        self.wp.upload_media.assert_not_called()
    def test_no_image_rejected_before_credentials(self):
        self.img.unlink();rc,r=self.invoke();self.assertNotEqual(rc,0);self.prep.assert_not_called()
    def test_bad_image_rejected(self):
        self.img.write_bytes(b'not an image');rc,r=self.invoke();self.assertNotEqual(rc,0);self.prep.assert_not_called()
    def test_wrapper_plain_text_empty_and_bad_utf8_rejected(self):
        for content in [b'<html><body><p>x</p></body></html>',b'<!DOCTYPE html><p>x</p>',b'   ',b'# markdown',b'\xff']:
            self.doc.write_bytes(content);rc,r=self.invoke();self.assertNotEqual(rc,0);self.prep.assert_not_called()
    def test_htm_accepted(self):
        self.doc=self.root/'body.htm';self.doc.write_bytes(HTML.encode());self.assertEqual(self.invoke()[0],0)
    def test_path_escape_rejected(self):
        self.doc=self.root/'escape.html';self.doc.symlink_to(Path(__file__))
        rc,r=self.invoke();self.assertNotEqual(rc,0);self.prep.assert_not_called()
    def test_image_failure_prevents_post(self):
        self.wp.upload_media.side_effect=WPError('connection failure');rc,r=self.invoke();self.assertNotEqual(rc,0);self.wp.create_post.assert_not_called()
    def test_post_failure_preserves_media_and_no_retry(self):
        self.wp.create_post.side_effect=WPError('connection failure');rc,r=self.invoke();self.assertEqual(r['media_id'],7);self.assertEqual(r['stage'],'create_post');self.wp.create_post.assert_called_once()
    def test_verification_mismatch_reports_incomplete(self):
        self.wp._request.side_effect=lambda *a,**k: {'status':'publish','title':{'raw':'Explicit'},'content':{'raw':'changed'},'featured_media':0}
        rc,r=self.invoke();self.assertEqual(r['status'],'verification_incomplete');self.assertEqual(r['post_id'],42);self.assertFalse(r['verification']['content'])
    def test_verification_failure_preserves_post_id(self):
        self.wp._request.side_effect=[{'id':1},WPError('permission failure')]
        rc,r=self.invoke();self.assertEqual(r['post_id'],42);self.assertEqual(r['status'],'incomplete')
    def test_site_mismatch_prevents_network(self):
        self.data['site_url']='https://other.test';rc,r=self.invoke();self.wp._request.assert_not_called()
    def test_missing_credentials_template_owner_only(self):
        rc,r=self.invoke(prepare=False);self.assertEqual(rc,2)
        p=Path(r['path']);self.assertEqual(p.stat().st_mode & 0o777,0o600);self.wp._request.assert_not_called()
    def test_transport_forces_draft(self):
        wp=WPClient(WPCredentials('https://example.test','test','test-only'))
        with patch.object(wp,'_request',return_value={'id':1}) as req:
            wp.create_post({'status':'publish'});self.assertEqual(req.call_args.kwargs['json_body']['status'],'draft')
    def test_redirect_refused(self):
        with self.assertRaises(WPError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.test')

if __name__=='__main__': unittest.main()
