import copy
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch

from compose_smoke import Harness, PAIRS, SCHEMA, SERVICES, assert_output, isolate


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.date = datetime.date.today().isoformat()
        self.rows = [[*pair, self.date] for pair in PAIRS]
        self.columns = [dict(name=n, type=t) for n, t in SCHEMA]

    def test_exact_output_and_reuse(self):
        self.assertEqual(self.date, assert_output(self.rows, self.columns))
        self.assertEqual(self.date, assert_output(self.rows, self.columns, self.date))

    def test_wrong_missing_and_duplicate_rows_fail(self):
        for rows in (self.rows[:2], self.rows + [self.rows[0]], [["9999", "wrong", self.date]] * 3, [['truncated']] * 3):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                assert_output(rows, self.columns)

    def test_wrong_schema_or_dates_fail(self):
        for columns in (self.columns[:-1], [dict(name='mcc', type='bigint')] + self.columns[1:]):
            with self.assertRaises(RuntimeError):
                assert_output(self.rows, columns)
        with self.assertRaises(RuntimeError):
            assert_output(self.rows, self.columns, '2000-01-01')
        self.rows[0][2] = None
        with self.assertRaises(RuntimeError):
            assert_output(self.rows, self.columns)


class IsolationTests(unittest.TestCase):
    def test_removes_host_access_and_external_state(self):
        base = {'services': {n: {'image': 'base', 'ports': ['1:1'], 'profiles': ['all'], 'container_name': n,
                'networks': {'example': {}}, 'volumes': []} for n in SERVICES}}
        base['services']['minio']['volumes'] = [dict(type='bind', source='/developer/data', target='/data')]
        base['services']['coordinator']['volumes'] = [dict(type='volume', source='external', target='/data/trino')]
        base['services']['datapipe']['volumes'] = [dict(type='bind', source='/examples', target='/opt/app/conf')]
        base['services']['unrelated'] = {'image': 'unused'}
        original = copy.deepcopy(base)
        result = isolate(base, 'candidate:123')
        self.assertEqual(original, base)
        self.assertEqual(set(SERVICES), set(result['services']))
        for service in result['services'].values():
            for forbidden in ('ports', 'container_name', 'profiles'):
                self.assertNotIn(forbidden, service)
        self.assertEqual('candidate:123', result['services']['datapipe']['image'])
        self.assertTrue(result['services']['datapipe']['volumes'][0]['read_only'])
        self.assertEqual({'minio-state': {}, 'coordinator-state': {}}, result['volumes'])
        self.assertEqual({'example': {}}, result['networks'])


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.h = Harness('.', self.directory.name, 'candidate:123', timeout=1)

    @patch('compose_smoke.subprocess.Popen')
    def test_nonzero_exit_is_logged_and_fails(self, run):
        run.return_value.communicate.return_value = ('task failed', '')
        run.return_value.returncode = 7
        with self.assertRaises(RuntimeError):
            self.h.run(['make', '4'])
        self.assertEqual(7, self.h.report['commands'][0]['exit_code'])
        self.assertEqual('task failed', (Path(self.directory.name) / 'command-001.log').read_text())
        self.assertEqual(1, run.return_value.communicate.call_args.kwargs['timeout'])
        self.assertTrue(run.call_args.kwargs['start_new_session'])

    @patch('compose_smoke.os.killpg')
    @patch('compose_smoke.subprocess.Popen')
    def test_timeout_is_logged_and_fails(self, run, kill):
        run.return_value.pid = 12345
        run.return_value.communicate.side_effect = [subprocess.TimeoutExpired(['docker'], 1), subprocess.TimeoutExpired(['docker'], 5), ('waiting', '')]
        with self.assertRaises(RuntimeError):
            self.h.run(['docker'])
        self.assertTrue(self.h.report['commands'][0]['timeout'])
        self.assertEqual(2, kill.call_count)

    def test_real_timeout_terminates_grandchild(self):
        marker = Path(self.directory.name) / 'grandchild-survived'
        child = 'import time,pathlib; time.sleep(1); pathlib.Path(%r).write_text("alive")' % str(marker)
        parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",%r]); time.sleep(10)' % child
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.h.run([sys.executable, '-c', parent], timeout=0.1)
        time.sleep(1.2)
        self.assertFalse(marker.exists(), 'Grandchild outlived the command timeout')

    @patch('compose_smoke.os.killpg')
    @patch('compose_smoke.subprocess.Popen')
    def test_cancellation_terminates_child_group(self, run, kill):
        run.return_value.returncode = None
        run.return_value.pid = 12345
        run.return_value.communicate.side_effect = [KeyboardInterrupt(), ('', '')]
        with self.assertRaises(KeyboardInterrupt):
            self.h.run(['docker'])
        kill.assert_called_once()

    def test_query_error_and_pagination(self):
        with patch.object(self.h, 'run', return_value=json.dumps({'error': {'message': 'broken'}})):
            with self.assertRaises(RuntimeError):
                self.h.sql('SELECT 1')
        with patch.object(self.h, 'run', side_effect=[json.dumps({'nextUri': 'http://next', 'data': [[1]]}), json.dumps({'data': [[2]]})]):
            self.assertEqual([[1], [2]], self.h.sql('SELECT 1')[0])

    def test_task_failure_stops_cycles(self):
        def run(args, **kwargs):
            if args[0] == 'make':
                raise RuntimeError('failed task')
            return ''
        with patch.object(self.h, 'run', side_effect=run), patch.object(self.h, 'sql', return_value=([], [])):
            with self.assertRaisesRegex(RuntimeError, 'failed task'):
                self.h.execute()
        self.assertEqual(1, len(self.h.report['cycles']))
        self.assertFalse(self.h.report['cycles'][0]['passed'])

    def test_readiness_failure_never_executes_task(self):
        with patch.object(self.h, 'run', side_effect=RuntimeError('not ready')) as run:
            with self.assertRaisesRegex(RuntimeError, 'not ready'):
                self.h.execute()
        self.assertFalse(any(c.args[0][0] == 'make' for c in run.call_args_list))

    def test_failure_report_and_cleanup_propagate_nonzero(self):
        self.h.output = Path(self.directory.name) / 'report'
        def fail():
            self.h.started = True
            raise RuntimeError('output mismatch')
        with patch.object(self.h, 'prepare'), patch.object(self.h, 'execute', side_effect=fail), patch.object(self.h, 'run', return_value='') as run:
            self.assertEqual(1, self.h.main())
        report = json.loads((self.h.output / 'report.json').read_text())
        self.assertFalse(report['passed'])
        self.assertEqual('output mismatch', report['error'])
        self.assertIn('--volumes', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
