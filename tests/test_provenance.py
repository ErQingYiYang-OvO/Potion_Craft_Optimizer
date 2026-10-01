import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from optimizer.provenance import ROOT, capture_run_snapshot


class ProvenanceTests(unittest.TestCase):
    def test_archive_preserves_old_code_and_distinguishes_changed_data(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'result/search') as name:
            root=Path(name);(root/'data').mkdir();(root/'engine').mkdir()
            self.assertTrue(root.resolve().is_relative_to(ROOT))
            (root/'result/search').mkdir(parents=True)
            (root/'result/manifest.json').write_bytes(b'{"records":[]}')
            (root/'result/search/example_candidates.json').write_bytes(b'{"records":{}}')
            data=root/'data/example.json';data.write_text('{"value":1}',encoding='utf-8')
            (root/'engine/example.py').write_bytes(b'value = 1\n')
            first=capture_run_snapshot(root);same=capture_run_snapshot(root)
            self.assertEqual(first['id'],same['id'])
            data.write_text('{"value":2}',encoding='utf-8')
            second=capture_run_snapshot(root)
            self.assertNotEqual(first['id'],second['id'])
            with zipfile.ZipFile(root/first['archive']) as archive:
                self.assertEqual(json.loads(archive.read('data/example.json')),{'value':1})
                self.assertEqual(archive.read('engine/example.py'),b'value = 1\n')
                self.assertEqual(archive.read('result/manifest.json'),b'{"records":[]}')
                self.assertEqual(archive.read('result/search/example_candidates.json'),b'{"records":{}}')


if __name__=='__main__':unittest.main()
