import builtins
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / 'agency/hermes-plugins/ai-lab-capabilities/writer_status.py'
spec = importlib.util.spec_from_file_location('status_projection', P)
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)
PIPELINE = os.environ.get('RESEARCH_PIPELINE_MODULE')

class WriterImportIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pipeline = self.root / 'article_research_pipeline.py'
        self.pipeline.touch()
        (self.root / 'wiki_contract_apply.py').write_text(
            'import sys\n'
            'sys.path.insert(0, "synthetic-writer-bootstrap")\n'
            'from tools.contract_validator import value\n'
            'from tools.nested import evidence\n')
        (self.root / 'contract_validator.py').write_text(
            'value = "writer"\ndef dir_for_type(value): return "synthetic"\n')
        (self.root / 'nested.py').write_text(
            'from dataclasses import dataclass\n'
            'from tools.contract_validator import value\n'
            '@dataclass\nclass Evidence:\n    value: str = value\n'
            'evidence = Evidence()\n')
        self.host = types.ModuleType('tools')
        self.host.__path__ = ['/synthetic/hermes/tools']
        self.host.marker = object()
        self.host_validator = types.ModuleType('tools.contract_validator')
        self.host_validator.value = 'must-not-be-used'
        self.host_import = builtins.__import__
        self.host_path = list(sys.path)

    def test_cached_host_package_and_nested_imports_stay_untouched(self):
        with patch.dict(sys.modules, {'tools': self.host,
                                     'tools.contract_validator': self.host_validator}):
            writer = projection._writer(self.pipeline)
            self.assertEqual(writer.value, 'writer')
            self.assertEqual(writer.evidence.value, 'writer')
            self.assertEqual(writer._status_dir_for_type('any'), 'synthetic')
            self.assertIs(sys.modules['tools'], self.host)
            self.assertIs(sys.modules['tools.contract_validator'], self.host_validator)
            self.assertEqual(self.host.__path__, ['/synthetic/hermes/tools'])
            self.assertEqual(sys.path, self.host_path)
            self.assertIs(builtins.__import__, self.host_import)
            self.assertFalse(list(self.root.rglob('*.pyc')))

    def test_missing_dependency_cleans_private_modules_and_retries(self):
        (self.root / 'nested.py').unlink()
        before = {name for name in sys.modules if name.startswith('_research_status_writer_')}
        with self.assertRaises(FileNotFoundError):
            projection._writer(self.pipeline)
        self.assertEqual(before, {name for name in sys.modules if name.startswith('_research_status_writer_')})
        self.assertEqual(sys.path, self.host_path)
        (self.root / 'nested.py').write_text('evidence = "recovered"\n')
        self.assertEqual(projection._writer(self.pipeline).evidence, 'recovered')

    def test_parallel_loads_share_only_the_private_writer(self):
        with patch.dict(sys.modules, {'tools': self.host}):
            with ThreadPoolExecutor(max_workers=8) as pool:
                writers = list(pool.map(projection._writer, [self.pipeline] * 24))
            self.assertTrue(all(writer is writers[0] for writer in writers))
            self.assertIs(sys.modules['tools'], self.host)
            self.assertEqual(sys.path, self.host_path)

    @unittest.skipUnless(PIPELINE and os.environ.get('HERMES_SOURCE'), 'requires real Hermes and Writer checkouts')
    def test_real_hermes_tools_preimport(self):
        code = '''
import importlib.util, os, sys
from pathlib import Path
sys.path.insert(0, os.environ['HERMES_SOURCE'])
import tools
assert Path(tools.__file__).resolve() == (Path(os.environ['HERMES_SOURCE']) / 'tools/__init__.py').resolve()
original_path = list(sys.path)
original_tools = {k: v for k, v in sys.modules.items() if k == 'tools' or k.startswith('tools.')}
spec = importlib.util.spec_from_file_location('isolated_status_test', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
writer = module._writer(os.environ['RESEARCH_PIPELINE_MODULE'])
assert callable(writer.parse_contract)
assert writer._status_dir_for_type('methodology')
assert module._writer(os.environ['RESEARCH_PIPELINE_MODULE']) is writer
assert sys.path == original_path
assert original_tools == {k: v for k, v in sys.modules.items() if k == 'tools' or k.startswith('tools.')}
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code, str(P)], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_different_writer_roots_do_not_share_dependencies(self):
        first = projection._writer(self.pipeline)
        other = self.root / 'other'
        other.mkdir()
        for source in self.root.glob('*.py'):
            (other / source.name).write_bytes(source.read_bytes())
        (other / 'contract_validator.py').write_text(
            'value = "other"\ndef dir_for_type(value): return "other"\n')
        second = projection._writer(other / self.pipeline.name)
        self.assertEqual(first.evidence.value, 'writer')
        self.assertEqual(second.evidence.value, 'other')
        self.assertIsNot(first, second)


@unittest.skipUnless(PIPELINE, 'requires configured sole Writer checkout')
class WriterProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.writer = projection._writer(PIPELINE)
        (self.root/'raw/compiled/day/_consumed').mkdir(parents=True)
        (self.root/'raw/.contract-apply.lock').touch()
        (self.root/'raw/reports').mkdir()
        self.raw = 'raw/reports/example.md'
        raw = '---\ntask_id: task\nsource_revision: rev\nowner_tenant: local_owner\ntenant: local_owner\nnoexport: true\n---\nEvidence\n'
        (self.root/self.raw).write_text(raw)
        self.receipt = {'raw_path': self.raw, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}
        self.body = '### Verified increment\n\n- Specific synthetic evidence with bounded scope.\n'
        contract = '---\ntask_id: task\ntarget: Example\ntype: methodology\nsource_files: '+json.dumps([self.raw])+'\nsource_sha256: '+json.dumps({self.raw:self.receipt['sha256']})+'\n---\n'+self.body
        self.contract = self.root/'raw/compiled/day/_consumed/example.contract.md'
        self.contract.write_text(contract)
        meta, body = self.writer.parse_contract(contract)
        self.row = {'file':'example.contract.md','target':'Example','sha256':self.writer.contract_sha256(meta, body),'status':'applied'}
        self.ledger = self.root/'raw/compiled/day/consumed.json'
        self.write_ledger([self.row])
        self.target = self.root/'wiki/方法论/Example.md'
        self.target.parent.mkdir(parents=True)
        self.target.write_text('---\ntenant: local_owner\nowner_tenant: local_owner\nnoexport: true\n---\n'+self.body)

    def write_ledger(self, rows):
        self.ledger.write_text(json.dumps({'records': rows}))

    def result(self):
        return projection.read_compilation(self.root, PIPELINE, self.receipt, 'rev', 'task')

    def test_actual_writer_parser_and_hash(self):
        before = self.ledger.read_bytes()
        self.assertTrue(self.result()['verified'])
        self.assertEqual(before, self.ledger.read_bytes())

    def test_duplicate_requires_body(self):
        self.write_ledger([dict(self.row,status='skipped_duplicate')])
        self.assertTrue(self.result()['verified'])
        self.target.write_text('---\ntenant: local_owner\nnoexport: true\n---\nRemoved')
        self.assertFalse(self.result()['verified'])

    def test_rollback_invalidates(self):
        self.write_ledger([self.row, {'status':'rolled_back'}])
        self.assertFalse(self.result()['verified'])

    def test_failed_latest_invalidates(self):
        self.write_ledger([self.row,dict(self.row,status='failed')])
        self.assertFalse(self.result()['verified'])

    def test_wrong_revision(self):
        self.assertFalse(projection.read_compilation(self.root,PIPELINE,self.receipt,'other','task')['verified'])

    def test_raw_tampered(self):
        (self.root/self.raw).write_text('tampered')
        self.assertFalse(self.result()['verified'])

    def test_missing_ledger(self):
        self.ledger.unlink()
        self.assertFalse(self.result()['verified'])

    def test_wrong_target_tenant(self):
        self.target.write_text(self.target.read_text().replace('local_owner','other'))
        self.assertFalse(self.result()['verified'])

    def test_symlink_target(self):
        outside = self.root/'outside.md'
        outside.write_bytes(self.target.read_bytes())
        self.target.unlink()
        self.target.symlink_to(outside)
        self.assertFalse(self.result()['verified'])

    def test_pending_transaction(self):
        journal=self.root/self.writer.TRANSACTION_DIR/'journal.json'
        journal.parent.mkdir(parents=True)
        journal.write_text('{"state":"active"}')
        self.assertFalse(self.result()['verified'])

    def test_no_contract(self):
        self.contract.unlink()
        self.assertFalse(self.result()['verified'])

    def test_partial_contracts(self):
        second=self.contract.with_name('second.contract.md')
        second.write_text(self.contract.read_text().replace('Specific synthetic','Another synthetic'))
        self.assertFalse(self.result()['verified'])

if __name__ == '__main__':
    unittest.main()
