import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / 'agency/hermes-plugins/ai-lab-capabilities/writer_status.py'
spec = importlib.util.spec_from_file_location('status_projection', P)
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)
PIPELINE = os.environ.get('RESEARCH_PIPELINE_MODULE')

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
