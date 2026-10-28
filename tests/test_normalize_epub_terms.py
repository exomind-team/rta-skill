from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[1]
SCRIPT=REPO/'scripts'/'normalize_epub_terms.py'
spec=importlib.util.spec_from_file_location('normalize_epub_terms',SCRIPT)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
X=mod.XHTML;O=mod.OPF;C=mod.CONTAINER

def x(local): return f'{{{X}}}{local}'

class NormalizeEpubTermsTests(unittest.TestCase):
 def test_mapping_and_protected_continuations(self):
  rules={"canonical":"Alpha","variants":["Alfa","Alphaa"],"protected_following":{"Alfa":["-","data"]}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'rules.json';p.write_text(json.dumps(rules),encoding='utf-8')
   canonical,variants,protected,pattern=mod.load_rules(p)
   self.assertEqual(canonical,'Alpha')
   source='Alfa grows; Alfa-data stays; Alphaa works.'
   self.assertEqual([m.group(0) for m in mod.eligible_matches(source,pattern,protected)],['Alfa','Alphaa'])
   normalized,counts=mod.normalize_text(source,canonical,pattern,protected)
   self.assertEqual(normalized,'Alpha grows; Alfa-data stays; Alpha works.')
   self.assertEqual(counts,{'Alfa':1,'Alphaa':1})

 def test_epub_preserves_original_side_markers_and_assets(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=Path(d);src=tmp/'input.epub';out=tmp/'output.epub';rules=tmp/'rules.json'
   rules.write_text(json.dumps({"canonical":"Alpha","variants":["Alfa"],"protected_following":{"Alfa":["-data"]}}),encoding='utf-8')
   container=b'''<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
   opf=b'''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><manifest><item id="pre" href="preface.xhtml" media-type="application/xhtml+xml"/><item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="img" href="image.png" media-type="image/png"/></manifest><spine><itemref idref="pre"/><itemref idref="ch"/></spine></package>'''
   pre=b'''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Sample</h1></body></html>'''
   chapter='''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter</h1><p class="proofread" id="rewritten-p1">Alfa &amp; one.<a class="uncertainty-marker" href="#rewritten-p1">[u1]</a></p><details id="original-p1" class="source-comparison" data-added="0" data-deleted="0"><summary><span class="diff-label">原文</span> <span class="diff-add">+0</span> <span class="diff-delete">-0</span></summary><blockquote class="comparison"><p class="diff">Alfa &amp; one.</p></blockquote></details><figure><img src="image.png" alt="test"/></figure></body></html>'''.encode('utf-8')
   with zipfile.ZipFile(src,'w') as z:
    z.writestr('mimetype',b'application/epub+zip',compress_type=zipfile.ZIP_STORED)
    z.writestr('META-INF/container.xml',container)
    z.writestr('OEBPS/content.opf',opf)
    z.writestr('OEBPS/preface.xhtml',pre)
    z.writestr('OEBPS/chapter.xhtml',chapter)
    z.writestr('OEBPS/style.css',b'')
    z.writestr('OEBPS/image.png',b'synthetic-image-bytes')
   result=mod.process_epub(src,out,rules)
   self.assertEqual(result['normalized_occurrences'],1)
   self.assertEqual(result['image_refs_preserved'],1)
   with zipfile.ZipFile(out) as z:
    self.assertIsNone(z.testzip())
    doc=ET.fromstring(z.read('OEBPS/chapter.xhtml'))
    p=next(n for n in doc.iter(x('p')) if n.attrib.get('id')=='rewritten-p1' and 'proofread' in n.attrib.get('class','').split())
    self.assertEqual(mod.comparison_text(p),'Alpha & one.')
    marker=doc.find('.//'+x('a'))
    self.assertIsNotNone(marker)
    details=doc.find('.//'+x('details'))
    parent_map={c:parent for parent in doc.iter() for c in list(parent)}
    siblings=list(parent_map[p])
    self.assertLess(siblings.index(details),siblings.index(p))
    diff=mod.find_diff(details)
    self.assertEqual(mod.reconstruct(diff),('Alfa & one.','Alpha & one.'))
    self.assertGreater(int(details.attrib['data-added']),0)
    self.assertGreater(int(details.attrib['data-deleted']),0)
    css=z.read('OEBPS/style.css').decode('utf-8')
    self.assertIn('details.source-comparison > summary',css)
    self.assertIn('text-align: right',css)
    self.assertIn('list-style-position: inside',css)
    self.assertFalse(any(e.tag==x('script') for e in doc.iter()))

 def test_layout_only_run_moves_existing_disclosure_before_proofread(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=Path(d);src=tmp/'input.epub';out=tmp/'output.epub'
   container=b'''<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
   opf=b'''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><manifest><item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/></manifest><spine><itemref idref="ch"/></spine></package>'''
   proofread='A proofread sentence.'; original='An original sentence.'
   second_proofread='Second proofread sentence.'; second_original='Second original sentence.'
   revised_with_note='Second proofread〔待核 U1〕 sentence.'
   detail1=ET.tostring(mod.make_details(None,original,proofread,'rewritten-p1'),encoding='unicode')
   detail2=ET.tostring(mod.make_details(None,second_original,revised_with_note,'rewritten-p2'),encoding='unicode')
   extra=mod.make_details(None,'An alternative source.','A different edited sentence.','rewritten-p2')
   extra.set('id','comparison-p2')
   extra_text=ET.tostring(extra,encoding='unicode')
   chapter=f'''<html xmlns="{X}"><body><p class="proofread" id="rewritten-p1">{proofread}</p><p class="uncertainty-jumps">U1</p>{detail1}<p class="proofread" id="rewritten-p2">Second proofread<a class="uncertainty-marker" href="#u1">〔待核 U1〕</a> sentence.</p>{detail2}{extra_text}</body></html>'''.encode('utf-8')
   with zipfile.ZipFile(src,'w') as z:
    z.writestr('mimetype',b'application/epub+zip',compress_type=zipfile.ZIP_STORED)
    z.writestr('META-INF/container.xml',container);z.writestr('OEBPS/content.opf',opf)
    z.writestr('OEBPS/chapter.xhtml',chapter);z.writestr('OEBPS/style.css',b'')
   result=mod.process_epub(src,out,layout_only=True)
   self.assertEqual(result['mode'],'layout-only')
   self.assertEqual(result['changed_paragraphs'],0)
   self.assertEqual(result['normalized_occurrences'],0)
   self.assertEqual(result['relocated_comparison_blocks'],2)
   self.assertEqual(result['layout_exception_count'],1)
   self.assertEqual(result['layout_exceptions'][0]['details_id'],'comparison-p2')
   with zipfile.ZipFile(out) as z:
    self.assertIsNone(z.testzip())
    doc=ET.fromstring(z.read('OEBPS/chapter.xhtml'));body=doc.find(x('body'))
    kids=list(body);self.assertEqual([n.tag for n in kids],[x('details'),x('p'),x('p'),x('details'),x('p'),x('details')])
    d1,p1,jump,d2,p2,extra_out=kids
    self.assertEqual(mod.comparison_text(p1),proofread)
    self.assertEqual(mod.reconstruct(mod.find_diff(d1)),(original,proofread))
    self.assertEqual(mod.comparison_text(p2),second_proofread)
    self.assertEqual(mod.displayed_text(p2),revised_with_note)
    self.assertEqual(mod.reconstruct(mod.find_diff(d2)),(second_original,revised_with_note))
    self.assertEqual(jump.attrib.get('class'),'uncertainty-jumps')
    self.assertEqual(extra_out.attrib['id'],'comparison-p2')
    css=z.read('OEBPS/style.css').decode('utf-8')
    self.assertIn('text-align: right',css)

if __name__=='__main__':
 unittest.main()
