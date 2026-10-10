"""Run safety checks without starting Spark or contacting Google Cloud."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'rf_sensitivity_runner', ROOT / 'jobs/rf_sensitivity.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FreshOutputTests(unittest.TestCase):
    def test_existing_checkpoint_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'legacy'
            protocol = root / 'short_term/protocol/part-00000.txt'
            protocol.parent.mkdir(parents=True)
            protocol.write_text('{"seed": 2026}')
            checkpoint = root / 'short_term/original15/result/_SUCCESS'
            checkpoint.parent.mkdir(parents=True)
            checkpoint.touch()
            writes = []
            with self.assertRaisesRegex(FileExistsError, 'Resume is not supported'):
                runner.claim_new_output(str(root), lambda path: Path(path).exists(), writes.append)
            self.assertEqual(writes, [])
            self.assertEqual(protocol.read_text(), '{"seed": 2026}')
            self.assertTrue(checkpoint.exists())

    def test_new_output_is_reserved_and_cannot_be_claimed_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fresh'

            def create_marker(path):
                marker = Path(path)
                marker.parent.mkdir(parents=True, exist_ok=True)
                with marker.open('x'):
                    pass

            runner.claim_new_output(str(root), lambda path: Path(path).exists(), create_marker)
            self.assertTrue((root / '_RUN_CREATED').is_file())
            with self.assertRaises(FileExistsError):
                runner.claim_new_output(str(root), lambda path: Path(path).exists(), create_marker)

    def test_access_errors_and_races_propagate(self):
        def denied(_):
            raise PermissionError('Cannot inspect output')

        writes = []
        with self.assertRaises(PermissionError):
            runner.claim_new_output('gs://example/new', denied, writes.append)
        self.assertEqual(writes, [])

        def race(_):
            raise FileExistsError('Another invocation reserved this run')

        with self.assertRaises(FileExistsError):
            runner.claim_new_output('gs://example/new', lambda _: False, race)

    def test_modes_cannot_duplicate_output_paths(self):
        self.assertEqual(runner.parse_modes('short_term, calendar'), ('short_term', 'calendar'))
        for value in ('', 'short_term,', 'short_term,short_term', 'unknown'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                runner.parse_modes(value)


class CloudPreflightTests(unittest.TestCase):
    def run_wrapper(self, scenario, arguments=('fresh-run',)):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            commands = work / 'commands.txt'
            env_file = work / 'env.sh'
            env_file.write_text(
                'PROJECT_ID=test-project\nBUCKET=test-bucket\nREGION=test-region\n'
                'SA_NAME=test-sa\nRUN_ID=test-run\nCLUSTER=test-cluster\n')
            gcloud = work / 'gcloud'
            gcloud.write_text('''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$MOCK_COMMANDS"
if [[ "$1 $2" == 'storage ls' ]]; then
  case "$MOCK_SCENARIO" in
    denied) echo 'Permission denied' >&2; exit 1 ;;
    existing) echo 'gs://test-bucket/project/steps/fresh-run/' ;;
    source) echo 'gs://test-bucket/project/steps/fresh-run-source/' ;;
    *) echo 'gs://test-bucket/project/steps/task2-dual-v1/' ;;
  esac
elif [[ "$1 $2" == 'storage cp' && "$MOCK_SCENARIO" == 'race' ]]; then
  echo 'Generation precondition failed' >&2
  exit 1
fi
''')
            gcloud.chmod(0o755)
            python = work / 'python3'
            python.write_text('#!/usr/bin/env bash\n'
                              'printf "build %s\\n" "$*" >> "$MOCK_COMMANDS"\n')
            python.chmod(0o755)
            env = dict(os.environ, PATH=str(work) + os.pathsep + os.environ['PATH'],
                       RAINFALL_ENV_FILE=str(env_file), MOCK_COMMANDS=str(commands),
                       MOCK_SCENARIO=scenario)
            result = subprocess.run(
                ['bash', str(ROOT / 'cloud/09_rf_sensitivity.sh'), *arguments],
                env=env, capture_output=True, text=True, check=False)
            calls = commands.read_text() if commands.exists() else ''
            return result, calls

    def test_requires_explicit_safe_run_name(self):
        for arguments in ((), ('../old-run',), ('has space',), ('one', 'two')):
            with self.subTest(arguments=arguments):
                result, calls = self.run_wrapper('fresh', arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Usage:', result.stderr)
                self.assertEqual(calls, '')

    def test_existing_or_unreadable_prefix_aborts_before_build_or_upload(self):
        for scenario in ('existing', 'source', 'denied'):
            with self.subTest(scenario=scenario):
                result, calls = self.run_wrapper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls.splitlines()), 1)
                self.assertTrue(calls.startswith('storage ls '))

    def test_fresh_run_uses_create_only_separate_source_and_original_output_layout(self):
        result, calls = self.run_wrapper('fresh')
        self.assertEqual(result.returncode, 0, result.stderr)
        uploads = [line for line in calls.splitlines() if line.startswith('storage cp ')]
        self.assertEqual(len(uploads), 2)
        for line in uploads:
            self.assertIn('--if-generation-match=0', line)
            self.assertIn('/steps/fresh-run-source/', line)
        self.assertIn('--output gs://test-bucket/project/steps/fresh-run', calls)

    def test_upload_race_does_not_submit_job(self):
        result, calls = self.run_wrapper('race')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('dataproc jobs submit', calls)


if __name__ == '__main__':
    unittest.main()
