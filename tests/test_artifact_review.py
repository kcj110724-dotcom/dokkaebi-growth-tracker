"""Offline integrity checks for the isolated review driver, no Git credentials."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from artifact_ui_trial import members, verify_payload


def archive(files):
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    return target.getvalue()


class ArtifactReviewTests(unittest.TestCase):
    def fixture(self, wrong_inner=False):
        payload=b'review-payload'
        sha=hashlib.sha256(payload).hexdigest()
        data=archive({'dokkaebi-launcher.zip':payload,
            'dokkaebi-launcher.zip.sha256':('0'*64 if wrong_inner else sha)+'  dokkaebi-launcher.zip',
            'build-info.json':json.dumps({'source_sha':'a'*40,'component':'launcher','sha256':sha})})
        return data,{'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'source_sha':'a'*40}

    def test_outer_digest_and_source_pin_required(self):
        data,pin=self.fixture()
        verify_payload(data,pin)
        with self.assertRaises(ValueError):verify_payload(data+b'changed',pin)
        with self.assertRaises(ValueError):verify_payload(data,{**pin,'source_sha':'b'*40})

    def test_inner_sidecar_required_even_with_valid_outer_digest(self):
        data,pin=self.fixture(True)
        with self.assertRaises(ValueError):verify_payload(data,pin)

    def test_nested_artifact_paths_rejected(self):
        with self.assertRaises(ValueError):members(archive({'../launch_host.pyw':'bad'}))
