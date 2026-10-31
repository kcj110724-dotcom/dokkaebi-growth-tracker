"""Network failures must never masquerade as a successful no-update result."""
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/launcher/launcher'))
import update_engine as engine
import unified_updater as updater


class OnlineStatusTests(unittest.TestCase):
    def test_empty_releases_are_successful_no_update(self):
        with patch.object(updater, 'github_get', return_value=b'[]'):
            self.assertEqual(updater.get_available_releases('owner/repo'), {'app':None,'launcher':None})

    def test_dns_failure_is_not_no_update(self):
        with patch.object(engine.urllib.request.OpenerDirector, 'open',
                          side_effect=urllib.error.URLError('getaddrinfo failed')):
            with self.assertRaisesRegex(RuntimeError, 'DNS'):
                engine.github_get('https://api.github.com/repos/owner/repo/releases')

    def test_rate_limit_and_permission_denial_are_distinct(self):
        for code, headers, message in [(403, {'X-RateLimit-Remaining':'0'}, '한도'),
                                       (429, {}, '한도'), (403, {}, '접근이 거부')]:
            error = urllib.error.HTTPError('https://api.github.com', code, 'test', headers, io.BytesIO())
            with patch.object(engine.urllib.request.OpenerDirector, 'open', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, message):
                    engine.github_get('https://api.github.com/repos/owner/repo/releases')
