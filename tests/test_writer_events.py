"""Synthetic integration tests against Hermes' real file locks/job store."""
import concurrent.futures
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.environ.get('HERMES_SOURCE', str(Path.home() / '.hermes/hermes-agent')))
from cron import jobs

SOURCE = Path(__file__).resolve().parents[1] / 'agency/hermes-plugins/ai-lab-capabilities/writer_events.py'
spec = importlib.util.spec_from_file_location('writer_events_tested', SOURCE)
events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(events)


class WriterEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'HERMES_HOME': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = jobs.use_cron_store(self.home)
        self.store.__enter__()
        self.addCleanup(self.store.__exit__, None, None, None)
        self.job = jobs.create_job(prompt='Synthetic Writer test; never executed', schedule='15 */6 * * *',
                                   name='Synthetic Writer', deliver='local')
        self.id = self.job['id']
        self.db = self.home / 'outbox.sqlite3'

    def receipt(self, seed='a'):
        return {'admission_state': 'admitted', 'compile_eligible': True,
                'sha256': seed * 64, 'raw_path': 'raw/reports/synthetic.md'}

    def pending(self):
        with events.connect(self.db) as db:
            return db.execute('SELECT COUNT(*) FROM wakes WHERE pending=1').fetchone()[0]

    def test_idle_wake(self):
        result = events.request(self.db, self.id, self.receipt())
        self.assertEqual(result['state'], 'scheduled')
        self.assertFalse(result['compile_verified'])
        actual = jobs.get_job(self.id)
        self.assertTrue(actual['manual_run_at'])
        self.assertEqual(actual['schedule'], self.job['schedule'])
        self.assertEqual(self.pending(), 0)

    def test_pause_preserved_and_resume_drains(self):
        jobs.update_job(self.id, {'enabled': False, 'state': 'paused', 'paused_reason': 'operator'})
        self.assertEqual(events.request(self.db, self.id, self.receipt())['state'], 'paused_or_disabled')
        self.assertFalse(jobs.get_job(self.id)['enabled'])
        self.assertEqual(self.pending(), 1)
        jobs.update_job(self.id, {'enabled': True, 'state': 'scheduled', 'paused_at': None, 'paused_reason': None})
        self.assertEqual(events.drain(self.db, self.id)['state'], 'scheduled')

    def test_claimed_run_new_event_survives_completion(self):
        claim = jobs.claim_job_for_fire(self.id, force=True)
        self.assertTrue(claim)
        self.assertEqual(events.request(self.db, self.id, self.receipt())['state'], 'busy')
        self.assertEqual(self.pending(), 1)
        self.assertTrue(jobs.mark_job_run(self.id, True))
        self.assertEqual(events.drain(self.db, self.id)['state'], 'scheduled')
        self.assertTrue(jobs.get_job(self.id).get('manual_run_at'))

    def test_duplicate_does_not_retrigger_completed_request(self):
        events.request(self.db, self.id, self.receipt())
        jobs.mark_job_run(self.id, True)
        self.assertEqual(events.request(self.db, self.id, self.receipt())['state'], 'idle')
        self.assertFalse(jobs.get_job(self.id).get('manual_run_at'))

    def test_new_hash_creates_new_request(self):
        events.request(self.db, self.id, self.receipt())
        jobs.mark_job_run(self.id, True)
        self.assertEqual(events.request(self.db, self.id, self.receipt('b'))['state'], 'scheduled')

    def test_ineligible_cannot_wake(self):
        for changes in ({'compile_eligible': False}, {'admission_state': 'pending'}, {'sha256': 'not-a-hash'}):
            result = events.request(self.db, self.id, dict(self.receipt(), **changes))
            self.assertIn(result['state'], ('ineligible', 'invalid_receipt'))
        self.assertFalse(jobs.get_job(self.id).get('manual_run_at'))

    def test_missing_job_retains_pending(self):
        self.assertEqual(events.request(self.db, 'missing', self.receipt())['state'], 'missing_job')
        self.assertEqual(self.pending(), 1)

    def test_save_failure_retains_pending(self):
        with patch.object(jobs, 'save_jobs', side_effect=OSError('synthetic failure')):
            self.assertEqual(events.request(self.db, self.id, self.receipt())['state'], 'trigger_failed')
        self.assertEqual(self.pending(), 1)
        self.assertEqual(events.drain(self.db, self.id)['state'], 'scheduled')

    def test_concurrent_requests_coalesce(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: events.request(self.db, self.id, self.receipt()), range(24)))
        self.assertNotIn('trigger_failed', [x['state'] for x in results])
        with events.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wakes').fetchone()[0], 1)
        self.assertTrue(jobs.get_job(self.id).get('manual_run_at'))

    def test_operator_manual_context_preserved(self):
        jobs.trigger_job(self.id, extra_prompt='Synthetic operator context')
        before = jobs.get_job(self.id)
        events.request(self.db, self.id, self.receipt())
        after = jobs.get_job(self.id)
        self.assertEqual(after['manual_run_prompt'], before['manual_run_prompt'])
        self.assertEqual(after['manual_run_at'], before['manual_run_at'])

    def test_cross_process_lock_contention_fails_closed(self):
        code = "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.readline()"
        proc = subprocess.Popen([sys.executable, '-c', code, str(jobs._jobs_lock_file())],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'locked')
            self.assertEqual(events.request(self.db, self.id, self.receipt())['state'], 'trigger_failed')
            self.assertEqual(self.pending(), 1)
        finally:
            proc.communicate('\n', timeout=10)
        self.assertEqual(events.drain(self.db, self.id)['state'], 'scheduled')

    def test_native_script_retries_pending_without_agent(self):
        import shutil
        import yaml
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        deployed = self.home / 'plugins/ai-lab-capabilities'
        deployed.mkdir(parents=True)
        shutil.copy2(SOURCE, deployed / 'writer_events.py')
        cfg = {'plugins': {'entries': {'ai-lab-capabilities': {'settings': {'research_deposit': {
            'enabled': True, 'writer_events_enabled': True, 'writer_job_id': self.id,
            'deployment_mode': 'local_single_tenant'}}}}}}
        (self.home / 'config.yaml').write_text(yaml.safe_dump(cfg))
        ctx = PluginContext(PluginManifest(name='ai-lab-capabilities'), PluginManager())
        db = ctx.state.data_dir / 'writer-events.sqlite3'
        events.enqueue(db, self.receipt())
        script = SOURCE.parents[3] / 'scripts/wiki-writer-event-drain.py'
        env = dict(os.environ, AI_LAB_AGENT_OS_MODE='local_single_tenant')
        result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        self.assertEqual(json.loads(result.stdout)['state'], 'scheduled')
        self.assertTrue(jobs.get_job(self.id)['manual_run_at'])

    def test_process_restart_preserves_busy_request(self):
        jobs.claim_job_for_fire(self.id, force=True)
        events.request(self.db, self.id, self.receipt())
        jobs.mark_job_run(self.id, True)
        code = "import importlib.util,sys; s=importlib.util.spec_from_file_location('e',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.drain(sys.argv[2],sys.argv[3])['state'])"
        env = dict(os.environ, PYTHONPATH=str(Path(jobs.__file__).parents[1]))
        result = subprocess.run([sys.executable, '-c', code, str(SOURCE), str(self.db), self.id],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'scheduled')


if __name__ == '__main__':
    unittest.main()
