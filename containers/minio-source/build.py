#!/usr/bin/env python3
"""Build pinned official MinIO sources for the local Compose examples."""
import argparse
import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

SOURCES = {
    'minio': ('RELEASE.2025-09-07T16-13-09Z', '07c3a429bfed433e49018cb0f78a52145d4bedeb', '8819e3e7817e46b7b3798f8f200ead208562e571563c2e040352378031abe9f2'),
    'mc': ('RELEASE.2025-08-13T08-35-41Z', '7394ce0dd2a80935aded936b09fa12cbb3cb8096', '95cd293c7119f16921a6dc515a1fb74a2227f19fd994b9c8b770a154e802ac44'),
}


def host_architecture():
    machine = platform.machine().lower()
    try:
        return {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64', 'amd64': 'amd64'}[machine]
    except KeyError as error:
        raise RuntimeError('Unsupported host architecture: ' + machine + '; specify --arch') from error


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_archive(path, url, expected):
    if not path.exists():
        temporary = path.with_suffix('.download')
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if checksum(path) != expected:
        raise RuntimeError('Source checksum mismatch: ' + str(path))


def unpack(archive, build):
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            # Upstream archives contain files/directories; reject links and escapes.
            if not (member.isfile() or member.isdir()) or not (build / member.name).resolve().is_relative_to(build.resolve()):
                raise RuntimeError('Unsafe source archive member: ' + member.name)
        source.extractall(build, filter='data')


def run(command, **kwargs):
    print('+ ' + ' '.join(command), flush=True)
    subprocess.run(command, check=True, timeout=1800, **kwargs)


def build_one(name, root, architecture, images=False):
    release, commit, digest = SOURCES[name]
    directory = root / 'build'
    directory.mkdir(exist_ok=True)
    url = 'https://codeload.github.com/minio/%s/tar.gz/%s' % (name, commit)
    archive = directory / (name + '.tar.gz')
    source_archive(archive, url, digest)
    compiler = subprocess.check_output(['go', 'version'], text=True).strip()
    provenance = directory / (name + '-provenance.json')
    cached = None
    try:
        candidate = json.loads(provenance.read_text())
        if (candidate.get('commit') == commit and candidate.get('source_sha256') == digest
                and candidate.get('goarch') == architecture and candidate.get('go_version') == compiler
                and candidate.get('binary_sha256') == checksum(directory / name)
                and (directory / (name + '-LICENSE')).is_file()):
            cached = candidate
    except (OSError, ValueError):
        pass
    if cached:
        print('Reusing verified local binary: ' + name, flush=True)
        if images:
            run(['docker', 'build', '--platform', 'linux/' + architecture, '--pull=false', '-f', str(root / (name + '.Dockerfile')),
                 '-t', 'datapipe-%s:%s' % (name, release), str(root)])
        return cached
    unpack(archive, directory)
    source = directory / (name + '-' + commit)
    env = dict(os.environ, GOOS='linux', GOARCH=architecture, CGO_ENABLED='0')
    flags = '-s -w ' + ' '.join('-X github.com/minio/%s/cmd.%s=%s' % (name, key, value) for key, value in {
        'Version': datetime.datetime.strptime(release, 'RELEASE.%Y-%m-%dT%H-%M-%SZ').strftime('%Y-%m-%dT%H:%M:%SZ'), 'ReleaseTag': release,
        'CommitID': commit, 'ShortCommitID': commit[:12], 'CopyrightYear': '2025'}.items())
    run(['go', 'build', '-mod=readonly', '-trimpath', '-buildvcs=false', '-ldflags', flags, '-o', str(directory / name), '.'], cwd=source, env=env)
    shutil.copyfile(source / 'LICENSE', directory / (name + '-LICENSE'))
    evidence = dict(release=release, commit=commit, source=url, source_sha256=digest,
                    binary_sha256=checksum(directory / name), goos='linux', goarch=architecture,
                    go_version=compiler)
    (directory / (name + '-provenance.json')).write_text(json.dumps(evidence, indent=2) + '\n')
    if images:
        run(['docker', 'build', '--platform', 'linux/' + architecture, '--pull=false', '-f', str(root / (name + '.Dockerfile')),
             '-t', 'datapipe-%s:%s' % (name, release), str(root)])
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=['minio', 'mc', 'all'], default='all')
    parser.add_argument('--arch', choices=['arm64', 'amd64'], default=None, help='Target Docker engine architecture (default: host)')
    parser.add_argument('--images', action='store_true', help='Build local Docker images after compiling')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        architecture = args.arch or host_architecture()
        for name in SOURCES if args.component == 'all' else [args.component]:
            print(json.dumps(build_one(name, root, architecture, args.images), indent=2))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, 'MinIO source build failed: %s\n' % error)


if __name__ == '__main__':
    main()
