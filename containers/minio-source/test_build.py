import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from build import build_one, checksum, host_architecture, run, source_archive, unpack


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_host_architecture_mapping_and_unsupported_host(self):
        for host, target in [('arm64', 'arm64'), ('aarch64', 'arm64'), ('x86_64', 'amd64'), ('AMD64', 'amd64')]:
            with self.subTest(host=host), patch('build.platform.machine', return_value=host):
                self.assertEqual(target, host_architecture())
        with patch('build.platform.machine', return_value='unsupported'), self.assertRaisesRegex(RuntimeError, '--arch'):
            host_architecture()

    def test_image_platform_matches_crossbuilt_binary(self):
        source = self.root / 'build' / 'mc-7394ce0dd2a80935aded936b09fa12cbb3cb8096'
        source.mkdir(parents=True)
        (source / 'LICENSE').write_text('license')
        (source.parent / 'mc').write_bytes(b'binary')
        with patch('build.source_archive'), patch('build.unpack'), patch('build.run') as execute, patch('build.subprocess.check_output', return_value='go version go1.24.2'):
            evidence = build_one('mc', self.root, 'amd64', images=True)
        self.assertEqual('amd64', evidence['goarch'])
        docker = execute.call_args.args[0]
        self.assertEqual('linux/amd64', docker[docker.index('--platform') + 1])
        self.assertEqual('amd64', execute.call_args_list[0].kwargs['env']['GOARCH'])

    def test_cached_binary_is_verified_before_reuse(self):
        source = self.root / 'build' / 'mc-7394ce0dd2a80935aded936b09fa12cbb3cb8096'
        source.mkdir(parents=True)
        (source / 'LICENSE').write_text('license')
        (source.parent / 'mc').write_bytes(b'binary')
        with patch('build.source_archive'), patch('build.unpack'), patch('build.run'), patch('build.subprocess.check_output', return_value='go version go1.24.2'):
            build_one('mc', self.root, 'amd64')
        with patch('build.source_archive'), patch('build.unpack') as extract, patch('build.run') as execute, patch('build.subprocess.check_output', return_value='go version go1.24.2'):
            build_one('mc', self.root, 'amd64')
            extract.assert_not_called()
            execute.assert_not_called()
        (source.parent / 'mc').write_bytes(b'tampered')
        with patch('build.source_archive'), patch('build.unpack') as extract, patch('build.run') as execute, patch('build.subprocess.check_output', return_value='go version go1.24.2'):
            build_one('mc', self.root, 'amd64')
            extract.assert_called_once()
            execute.assert_called_once()

    def test_corrupt_archive_prevents_compile(self):
        with patch('build.source_archive', side_effect=RuntimeError('checksum mismatch')), patch('build.run') as execute:
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                build_one('minio', self.root, 'arm64')
            execute.assert_not_called()

    def test_cached_archive_is_still_verified(self):
        archive = self.root / 'source.tar.gz'
        archive.write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
            source_archive(archive, 'https://unused', '0' * 64)

    def test_download_failure_leaves_no_partial_archive(self):
        archive = self.root / 'source.tar.gz'
        with patch('build.urllib.request.urlopen', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                source_archive(archive, 'https://unused', '0' * 64)
        self.assertFalse(archive.exists())
        self.assertFalse(archive.with_suffix('.download').exists())

    def test_archive_traversal_and_symlinks_rejected(self):
        for name, kind in (('../outside', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            archive = self.root / 'unsafe.tar.gz'
            with tarfile.open(archive, 'w:gz') as output:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = '../outside'
                output.addfile(member)
            with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                unpack(archive, self.root)
        self.assertFalse((self.root.parent / 'outside').exists())

    def test_build_command_failure_is_not_swallowed(self):
        with patch('build.subprocess.run', side_effect=subprocess.CalledProcessError(2, ['go'])):
            with self.assertRaises(subprocess.CalledProcessError):
                run(['go', 'build'])


if __name__ == '__main__':
    unittest.main()
