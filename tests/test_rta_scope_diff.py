import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests'/'fixtures'
spec=importlib.util.spec_from_file_location('rta_scope_diff',ROOT/'scripts/rta_scope_diff.py')
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ScopeTests(unittest.TestCase):
    def fake(self,path,changed=False,unexpected=False,header_change=False,reverse_order=False):
        with zipfile.ZipFile(path,'w') as z:
            members=[('mimetype','application/epub+zip'),
                     ('OEBPS/package.opf','after' if changed else 'before'),
                     ('OEBPS/chapter-001.xhtml','body')]
            if unexpected:members.append(('OEBPS/surprise.txt','oops'))
            if reverse_order:members.reverse()
            for name,data in members:
                if name=='OEBPS/chapter-001.xhtml' and header_change:
                    info=zipfile.ZipInfo(name,date_time=(2024,1,1,0,0,0))
                    z.writestr(info,data)
                else:
                    z.writestr(name,data)
    def test_scope_pass_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/'a.epub';b=p/'b.epub';policy=FIXTURES/'synthetic_scope_policy.json'
            self.fake(a);self.fake(b,changed=True)
            passed=mod.scope_diff(a,b,policy)
            self.assertEqual(passed['status'],'SCOPE_PASS')
            self.assertEqual(passed['changed'],['OEBPS/package.opf'])
            self.fake(b,changed=True,unexpected=True)
            fail=mod.scope_diff(a,b,policy)
            self.assertEqual(fail['status'],'SCOPE_FAIL')
            self.assertEqual(fail['unexpected']['added'], ['OEBPS/surprise.txt'])
    def test_header_changes_reported_and_optionally_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/'a.epub';b=p/'b.epub';policy=p/'policy.json'
            self.fake(a);self.fake(b,header_change=True)
            data=json.loads((FIXTURES/'synthetic_scope_policy.json').read_text('utf-8'))
            policy.write_text(json.dumps(data),'utf-8')
            report=mod.scope_diff(a,b,policy)
            self.assertEqual(report['status'],'SCOPE_PASS')
            self.assertEqual(report['header_metadata_changed'],['OEBPS/chapter-001.xhtml'])
            data['strict_metadata']=True
            policy.write_text(json.dumps(data),'utf-8')
            self.assertEqual(mod.scope_diff(a,b,policy)['status'],'SCOPE_FAIL')

    def test_member_order_changes_are_reported_and_optionally_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);a=p/'a.epub';b=p/'b.epub';policy=p/'policy.json'
            self.fake(a);self.fake(b,reverse_order=True)
            data=json.loads((FIXTURES/'synthetic_scope_policy.json').read_text('utf-8'))
            policy.write_text(json.dumps(data),'utf-8')
            report=mod.scope_diff(a,b,policy)
            self.assertEqual(report['status'],'SCOPE_PASS')
            self.assertFalse(report['member_order_equal'])
            data['strict_order']=True
            policy.write_text(json.dumps(data),'utf-8')
            self.assertEqual(mod.scope_diff(a,b,policy)['status'],'SCOPE_FAIL')

if __name__=='__main__':unittest.main()
