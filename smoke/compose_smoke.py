#!/usr/bin/env python3
"""Disposable, three-cycle integration check of the existing Makefile target 4."""
import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import shlex
import signal
import shutil
import subprocess
import sys
import time
import uuid

SERVICES = ('postgres', 'pg-data', 'minio', 'minio-client', 'iceberg-rest', 'coordinator', 'datapipe')
PAIRS = [('4111', 'Transportation:Ride Sharing'), ('5812', 'Food and Drinks:Restaurants'), ('5813', 'Food and Drinks:Fast Food')]
SCHEMA = [('mcc', 'varchar'), ('category', 'varchar'), ('process_date', 'date')]


def isolate(config, image):
    """Whitelist services and replace every writable data mount with owned state."""
    result = {'services': {}, 'volumes': {}, 'networks': {}}
    for name in SERVICES:
        service = copy.deepcopy(config['services'][name])
        for key in ('container_name', 'profiles', 'ports', 'restart'):
            service.pop(key, None)
        for mount in service.get('volumes', []):
            if mount['type'] == 'volume' or mount['target'] in ('/data', '/var/lib/postgresql/data'):
                volume = name + '-state'
                result['volumes'][volume] = {}
                mount.clear()
                mount.update(type='volume', source=volume, target={'postgres': '/var/lib/postgresql/data', 'minio': '/data', 'coordinator': '/data/trino'}[name])
            else:
                mount['read_only'] = True
        for network in service.get('networks', {}):
            result['networks'][network] = {}
        if name == 'datapipe':
            service['image'] = image
            service.setdefault('environment', {})['TASK_PATH'] = '${TASK_PATH}'
        result['services'][name] = service
    return result


def assert_output(rows, columns, baseline=None):
    actual_schema = [(c['name'], c['type']) for c in columns]
    if actual_schema != SCHEMA:
        raise RuntimeError('Unexpected schema: ' + repr(actual_schema))
    if (len(rows) != 3 or any(len(r) != 3 or not all(isinstance(value, str) for value in r) for r in rows)
            or sorted((r[0], r[1]) for r in rows) != PAIRS):
        raise RuntimeError('Unexpected persisted rows: ' + repr(rows))
    dates = {r[2] for r in rows}
    if len(dates) != 1:
        raise RuntimeError('Expected one process date: ' + repr(dates))
    date = next(iter(dates))
    datetime.date.fromisoformat(date)
    if baseline and date != baseline:
        raise RuntimeError('Upsert changed the original process_date')
    if not baseline and date not in {datetime.datetime.now(datetime.timezone.utc).date().isoformat(), datetime.date.today().isoformat()}:
        raise RuntimeError('Initial process_date is not today: ' + date)
    return date


class Harness:
    def __init__(self, root, output, image, timeout=600, compose='docker compose', cleanup=False):
        self.root, self.output, self.image, self.timeout = Path(root), Path(output), image, timeout
        self.project = 'datapipe-smoke-' + uuid.uuid4().hex[:12]
        self.task_container = self.project + '-task'
        self.compose_base = shlex.split(compose)
        self.compose = self.compose_base + ['-p', self.project, '-f', str(self.output / 'compose.json')]
        self.report = {'project': self.project, 'candidate_image': image, 'cycles': [], 'commands': [], 'passed': False}
        self.started = False
        self.cleanup = cleanup
        self.report['cleanup_requested'] = cleanup
        self.report['cleanup_command'] = shlex.join(self.compose + ['down', '--volumes', '--remove-orphans'])

    def run(self, args, timeout=None):
        entry = {'argv': args}
        self.report['commands'].append(entry)
        log = self.output / ('command-%03d.log' % len(self.report['commands']))
        entry['log'] = log.name
        process = subprocess.Popen(args, cwd=self.root, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout or self.timeout)
            log.write_text(stdout + (stderr or ''))
            entry['exit_code'] = process.returncode
            if process.returncode:
                raise RuntimeError('Command failed (%d): %s; see %s' % (process.returncode, shlex.join(args), log))
            return stdout
        except subprocess.TimeoutExpired as exc:
            # make -> compose -> Docker client all share this owned process group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate(timeout=5)
            log.write_text((stdout or '') + (stderr or '') + '\nTIMEOUT\n')
            entry['timeout'] = True
            raise RuntimeError('Command timed out: ' + shlex.join(args)) from exc
        except BaseException:
            if process.returncode is not None:
                raise
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=5)
            raise

    def sql(self, statement):
        curl = ['exec', '-T', 'coordinator', 'curl', '--fail-with-body', '--silent', '--show-error', '--max-time', '20', '-H', 'X-Trino-User: smoke']
        response = json.loads(self.run(self.compose + curl + ['--data-binary', statement, 'http://localhost:8080/v1/statement'], timeout=30))
        rows, columns = [], []
        deadline = time.monotonic() + min(self.timeout, 180)
        while True:
            if response.get('error'):
                raise RuntimeError('Trino query failed: ' + json.dumps(response['error']))
            rows.extend(response.get('data', []))
            columns = response.get('columns', columns)
            if not response.get('nextUri'):
                return rows, columns
            if time.monotonic() >= deadline:
                raise RuntimeError('Trino query timed out')
            response = json.loads(self.run(self.compose + curl + [response['nextUri']], timeout=30))

    def prepare(self):
        self.report['demo_revision'] = self.run(['git', 'rev-parse', 'HEAD']).strip()
        self.report['demo_diff'] = self.run(['git', 'diff', '--', 'Makefile', 'docker-compose.yaml', 'examples'])
        self.report['candidate_inspect'] = json.loads(self.run(['docker', 'image', 'inspect', self.image], timeout=30))
        base = json.loads(self.run(self.compose_base + ['-f', 'docker-compose.yaml', '--profile', '*', 'config', '--format', 'json'], timeout=30))
        config = isolate(base, self.image)
        # Compose can reference absent optional init folders; never let Docker create them in the checkout.
        for service in config['services'].values():
            for mount in service.get('volumes', []):
                if mount['type'] == 'bind' and not Path(mount['source']).exists():
                    empty = self.output / ('empty-' + uuid.uuid4().hex[:8])
                    empty.mkdir()
                    mount['source'] = str(empty)
        # Copy credentials/config into the report area, never chmod developer files.
        certs = self.output / 'postgres-certs'
        shutil.copytree(self.root / 'containers/postgres/certs', certs)
        # Postgres accepts root-owned keys mode 0640; copy/chown inside its container.
        postgres = config['services']['postgres']
        for mount in postgres['volumes']:
            if mount['target'] == '/opt/postgres/certs':
                mount['source'] = str(certs)
                mount['target'] = '/smoke-certs'
        postgres['entrypoint'] = ['/bin/bash', '-ec', 'mkdir -p /opt/postgres/certs; cp /smoke-certs/* /opt/postgres/certs/; chown -R postgres:postgres /opt/postgres/certs; chmod 600 /opt/postgres/certs/server.key; exec docker-entrypoint.sh "$@"', '--']
        trino = self.output / 'trino'
        shutil.copytree(self.root / 'containers/trino/coordinator', trino)
        path = trino / 'config.properties'
        path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith(('http-server.authentication.', 'http-server.https.'))) + '\n')
        catalog = trino / 'catalog'
        for properties in catalog.glob('*.properties'):
            if properties.name != 'iceberg.properties':
                properties.unlink()
        (catalog / 'iceberg.properties').write_text('connector.name=iceberg\niceberg.catalog.type=rest\niceberg.rest-catalog.uri=http://iceberg-rest:8181\nfs.native-s3.enabled=true\ns3.endpoint=http://minio:9000\ns3.region=us-east-1\ns3.path-style-access=true\ns3.aws-access-key=minioadmin\ns3.aws-secret-key=minioadmin\n')
        for mount in config['services']['coordinator']['volumes']:
            if mount['target'] == '/etc/trino':
                mount['source'] = str(trino)
        (self.output / 'compose.json').write_text(json.dumps(config, indent=2))
        self.run(self.compose + ['config', '--quiet'], timeout=30)
        self.report['resolved_images'] = self.run(self.compose + ['config', '--images'], timeout=30).splitlines()

    def execute(self):
        # Start once, then verify repeated task outcomes against the same environment.
        self.started = True
        self.run(self.compose + ['up', '-d', '--wait', '--wait-timeout', '240', 'iceberg-rest', 'coordinator'], timeout=300)
        deadline = time.monotonic() + min(self.timeout, 180)
        while True:
            try:
                self.sql('SELECT 1')
                self.sql("CREATE SCHEMA IF NOT EXISTS iceberg.finance WITH (location='s3://warehouse/finance')")
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(2)
        baseline = None
        for cycle in range(1, 4):
            record = {'cycle': cycle, 'state': 'clean' if cycle == 1 else 'reuse', 'passed': False}
            self.report['cycles'].append(record)
            self.run(['make', '4', 'COMPOSE=' + shlex.join(self.compose), 'TASK_SERVICE=datapipe', 'TASK_RUN_ARGS=--no-deps --name ' + self.task_container])
            rows, columns = self.sql('SELECT mcc, category, process_date FROM iceberg.finance.category ORDER BY mcc')
            baseline = assert_output(rows, columns, baseline)
            record.update(rows=rows, columns=columns, passed=True)
        self.report['dependency_images'] = json.loads(self.run(['docker', 'image', 'inspect'] + self.report['resolved_images'], timeout=30))

    def main(self):
        self.output.mkdir(parents=True, exist_ok=False)
        try:
            self.prepare()
            self.execute()
            self.report['passed'] = True
        except Exception as exc:
            self.report['error'] = str(exc)
        finally:
            if self.started:
                try:
                    self.run(self.compose + ['logs', '--no-color'], timeout=30)
                except Exception as exc:
                    self.report['log_error'] = str(exc)
            if self.started and self.cleanup:
                # A killed Docker client can leave its one-off container running.
                try:
                    containers = self.run(['docker', 'container', 'ls', '-a', '--filter', 'name=^/' + self.task_container + '$', '--format', '{{.Names}}'], timeout=30).splitlines()
                    if self.task_container in containers:
                        self.run(['docker', 'container', 'rm', '--force', self.task_container], timeout=30)
                except Exception as exc:
                    self.report.setdefault('cleanup_errors', []).append(str(exc))
                    self.report['passed'] = False
                for command in (['logs', '--no-color'], ['down', '--volumes', '--remove-orphans', '--timeout', '20']):
                    try:
                        self.run(self.compose + command, timeout=90)
                    except Exception as exc:
                        self.report.setdefault('cleanup_errors', []).append(str(exc))
                        self.report['passed'] = False
            (self.output / 'report.json').write_text(json.dumps(self.report, indent=2))
        return 0 if self.report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Locally built candidate image; recorded with its image ID')
    parser.add_argument('--output', default=str(Path.cwd() / ('smoke-results-' + uuid.uuid4().hex[:8])))
    parser.add_argument('--timeout', type=int, default=600, help='Maximum task duration in seconds')
    parser.add_argument('--cleanup', action='store_true', help='Explicitly remove this smoke project and its volumes after verification; default leaves services running')
    parser.add_argument('--compose', default=os.environ.get('COMPOSE', 'docker compose'))
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    def cancelled(signum, frame):
        raise RuntimeError('Smoke check cancelled by signal %d' % signum)
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    harness = Harness(Path(__file__).resolve().parent.parent, Path(args.output).resolve(), args.image, args.timeout, args.compose, args.cleanup)
    if harness.output.exists():
        parser.error('--output already exists; choose a new evidence directory')
    result = harness.main()
    print('Report: ' + str(harness.output / 'report.json'))
    if result:
        print(harness.report.get('error', 'Cleanup failed'), file=sys.stderr)
    return result


if __name__ == '__main__':
    sys.exit(main())
