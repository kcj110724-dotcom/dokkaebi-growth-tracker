import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_package import SOURCE_FILES, build
from prepare_release import load_request, prepare, safe_member, validate_zip
from publish_release import publish
from release_gate import check_environment, check_request, check_run

SHA = 'a' * 40


def archive_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return stream.getvalue()


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.output = Path(cls.folder.name) / 'package'
        cls.metadata = build('tracker', SHA, cls.output)
        cls.payload = (cls.output / 'dokkaebi-app.zip').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def request(self):
        return {**self.metadata, 'approved': True, 'mode': 'artifact',
                'build_run_id': 123, 'title': 'Tracker test release',
                'notes': 'Reviewed build', 'latest': False}

    def test_extracted_sources_are_byte_identical_to_original(self):
        with zipfile.ZipFile(ROOT / 'release-payloads/tracker-v0.0.1/dokkaebi-app.zip') as archive:
            for name in SOURCE_FILES:
                self.assertEqual((ROOT / 'src/tracker' / name).read_bytes(), archive.read('app/' + name), name)

    def test_all_sources_compile(self):
        for path in (ROOT / 'src/tracker').rglob('*.py'):
            compile(path.read_bytes(), str(path), 'exec')

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            build('tracker', SHA, folder)
            self.assertEqual(self.payload, (Path(folder) / 'dokkaebi-app.zip').read_bytes())

    def test_legacy_zip_still_validates(self):
        payload = (ROOT / 'release-payloads/tracker-v0.0.1/dokkaebi-app.zip').read_bytes()
        validate_zip(payload, '0.0.1', 'tracker')

    def test_new_package_retains_manifest_contract(self):
        validate_zip(self.payload, self.metadata['version'], 'tracker')
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['schema'], 1)
            self.assertEqual(manifest['entrypoint'], 'tracker.py')
            self.assertEqual(set(archive.namelist()), {'manifest.json', *('app/' + p for p in SOURCE_FILES)})

    def test_tracker_zip_cannot_be_used_as_launcher(self):
        with self.assertRaises(ValueError):
            validate_zip(self.payload, '0.0.2', 'launcher')

    def test_invalid_source_sha_blocks_build(self):
        with self.assertRaises(ValueError):
            build('tracker', 'main', self.output)

    def test_artifact_hash_matches(self):
        self.assertEqual(self.metadata['sha256'], hashlib.sha256(self.payload).hexdigest())

    def test_approved_artifact_prepares_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as folder:
            prepare(self.request(), self.output, out=Path(folder))
            self.assertEqual((Path(folder) / 'dokkaebi-app.zip').read_bytes(), self.payload)

    def test_changed_artifact_or_source_is_rejected(self):
        for key in ('sha256', 'source_sha', 'version', 'component', 'tag'):
            obj = self.request()
            obj[key] = 'b' * 64 if key == 'sha256' else 'incorrect'
            if key == 'component':
                obj[key] = 'launcher'
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder, self.assertRaises(SystemExit):
                prepare(obj, self.output, out=Path(folder))

    def test_modified_zip_member_is_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            members = {n: archive.read(n) for n in archive.namelist()}
        members['app/tracker.py'] += b'\n# changed\n'
        with self.assertRaises(SystemExit):
            validate_zip(archive_bytes(members), '0.0.1', 'tracker')

    def test_windows_unsafe_names_rejected(self):
        for name in ('../x', '/x', 'C:/x', 'a\\b', 'a/../b', 'a//b',
                     'app/NUL.py', 'app/COM1.txt', 'app/file.', 'app/file ', 'app/a:b',
                     'app/a?b', 'app/a\nb'):
            with self.subTest(name=name):
                self.assertFalse(safe_member(name))

    def test_private_data_rejected_even_with_valid_manifest_hash(self):
        for name in ('config.json', 'user_data/private.csv', 'combat_power.csv',
                     'assets/user_background.gif', 'stat_latest.json'):
            with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
                members = {n: archive.read(n) for n in archive.namelist()}
            manifest = json.loads(members['manifest.json'])
            members['app/' + name] = b'private'
            manifest['files'][name] = hashlib.sha256(b'private').hexdigest()
            members['manifest.json'] = json.dumps(manifest).encode()
            with self.subTest(name=name), self.assertRaises(SystemExit):
                validate_zip(archive_bytes(members), '0.0.1', 'tracker')

    def test_missing_entrypoint_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            members = {n: archive.read(n) for n in archive.namelist() if n != 'app/tracker.py'}
        manifest = json.loads(members['manifest.json'])
        del manifest['files']['tracker.py']
        members['manifest.json'] = json.dumps(manifest).encode()
        with self.assertRaises(SystemExit):
            validate_zip(archive_bytes(members), '0.0.1', 'tracker')

    def test_case_collision_rejected(self):
        with self.assertRaises(SystemExit):
            validate_zip(archive_bytes({'app/A.py': b'a', 'app/a.py': b'b'}), '0.0.1', 'tracker')

    def test_symlink_zip_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            info = zipfile.ZipInfo('link')
            info.external_attr = 0o120777 << 16
            archive.writestr(info, 'target')
        with self.assertRaises(SystemExit):
            validate_zip(stream.getvalue(), '0.0.1', 'tracker')

    def test_zip_limits_reject_unbounded_payloads(self):
        for limit in ('MAX_MEMBERS', 'MAX_UNPACKED'):
            with self.subTest(limit=limit), patch('prepare_release.' + limit, 1), self.assertRaises(SystemExit):
                validate_zip(self.payload, '0.0.1', 'tracker')

    def test_build_ignores_private_records_and_does_not_modify_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            import shutil
            shutil.copytree(ROOT / 'src/tracker', root / 'src/tracker')
            shutil.copytree(ROOT / 'release-config', root / 'release-config')
            private = root / 'src/tracker/config.json'
            private.write_bytes(b'{"private": true}')
            user_data = root / 'src/tracker/user_data'
            user_data.mkdir()
            records = user_data / 'combat_power.csv'
            records.write_bytes(b'private records')
            metadata = build('tracker', SHA, root / 'dist', root=root)
            self.assertEqual(metadata['sha256'], self.metadata['sha256'])
            self.assertEqual(private.read_bytes(), b'{"private": true}')
            self.assertEqual(records.read_bytes(), b'private records')

    def test_request_requires_explicit_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'release-requests').mkdir()
            for approved in (False, 'true', 1, None):
                obj = {**self.request(), 'approved': approved}
                (root / 'release-requests/test.json').write_text(json.dumps(obj), encoding='utf-8')
                with self.subTest(approved=approved), self.assertRaises(SystemExit):
                    load_request('release-requests/test.json', root)

    def test_historical_request_is_readable_but_cannot_publish(self):
        obj = load_request('release-requests/tracker-v0.0.1.json')
        with self.assertRaises(SystemExit):
            check_request(obj, {'status': 'verified', 'evidence': ['report.md']})

    def test_pending_launcher_compatibility_blocks_publish(self):
        config = json.loads((ROOT / 'release-config/compatibility.json').read_text())
        with self.assertRaises(SystemExit):
            check_request(self.request(), config)

    def test_release_request_policy_fields(self):
        compatibility = {'status': 'verified', 'evidence': ['report.md']}
        check_request(self.request(), compatibility)
        for key, value in (('mode', 'staged'), ('source_sha', 'main'),
                           ('build_run_id', True), ('build_run_id', 0), ('latest', 'false')):
            with self.subTest(key=key), self.assertRaises(SystemExit):
                check_request({**self.request(), key: value}, compatibility)

    def test_environment_requires_owner_as_sole_reviewer(self):
        env = {'protection_rules': [{'type': 'required_reviewers', 'reviewers': [
            {'type': 'User', 'reviewer': {'login': 'owner'}}]}]}
        check_environment(env, 'owner')
        for candidate in ({}, {'protection_rules': []},
                          {'protection_rules': [{'type': 'required_reviewers', 'reviewers': [
                              {'type': 'User', 'reviewer': {'login': 'someone-else'}}]}]}):
            with self.assertRaises(SystemExit):
                check_environment(candidate, 'owner')
        env['protection_rules'][0]['reviewers'].append({'type': 'User', 'reviewer': {'login': 'other'}})
        with self.assertRaises(SystemExit):
            check_environment(env, 'owner')

    def test_ci_provenance_rejects_forks_failed_runs_and_wrong_commits(self):
        run = {'status': 'completed', 'conclusion': 'success', 'head_sha': SHA,
               'event': 'push', 'path': '.github/workflows/build.yml',
               'head_repository': {'full_name': 'owner/repo'}}
        check_run(run, self.request(), 'owner/repo')
        for key, value in (('conclusion', 'failure'), ('status', 'in_progress'),
                           ('head_sha', 'b' * 40), ('event', 'pull_request'),
                           ('path', '.github/workflows/other.yml'),
                           ('head_repository', {'full_name': 'fork/repo'})):
            with self.subTest(key=key), self.assertRaises(SystemExit):
                check_run({**run, key: value}, self.request(), 'owner/repo')

    def test_upload_failure_keeps_release_unpublished(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args[1:3] == ['release', 'upload']:
                raise subprocess.CalledProcessError(1, args)
        with self.assertRaises(subprocess.CalledProcessError):
            publish(self.request(), 'owner/repo', run)
        self.assertFalse(any(args[1:3] == ['release', 'edit'] for args in calls))
        self.assertIn('--draft', calls[1])

    def test_existing_tag_stops_before_creating_release(self):
        runner = Mock(side_effect=subprocess.CalledProcessError(1, 'tag already exists'))
        with self.assertRaises(subprocess.CalledProcessError):
            publish(self.request(), 'owner/repo', runner)
        self.assertEqual(runner.call_count, 1)

    def test_publish_pins_source_and_sets_latest_explicitly(self):
        runner = Mock()
        publish(self.request(), 'owner/repo', runner)
        calls = [call.args[0] for call in runner.call_args_list]
        self.assertIn('sha=' + SHA, calls[0])
        self.assertEqual(calls[1][calls[1].index('--target') + 1], SHA)
        self.assertIn('--latest=false', calls[-1])

    def test_csv_reader_preserves_existing_bom_data(self):
        # Exercise the real dashboard function without starting a GUI or importing
        # capture modules. This is the unchanged CSV compatibility boundary.
        tree = ast.parse((ROOT / 'src/tracker/tracker.py').read_bytes())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'read_rows')
        import csv
        namespace = {'csv': csv}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'read_rows', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'combat_power.csv'
            original = 'timestamp,combat_power,change,source\n2026-01-01,123456,,screen_ocr_exact\n'.encode('utf-8-sig')
            path.write_bytes(original)
            self.assertEqual(namespace['read_rows'](path)[0]['combat_power'], '123456')
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
