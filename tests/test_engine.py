"""The engine's own behaviour, with the provider faked.

The shared conformance suite asserts the fleet contract; this file keeps the
provider-specific promise: a happy path, a refused empty prompt, and a failure
reported per file.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine_deepinfra import Engine, EngineError, InputFile  # noqa: E402
from engine_deepinfra.catalog import load_catalog  # noqa: E402
from engine_deepinfra.transport import ProviderError  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
SAMPLE = b'a paragraph of prose'
TEXT_MODEL = 'deepinfra/completions'


class FakeClient:
    def __init__(self, script, payload=SAMPLE):
        self.script = list(script)
        self.payload = payload
        self.calls = []

    def request_json(self, method, path, payload=None, *, headers=None, params=None):
        self.calls.append({"method": method, "path": path, "payload": payload})
        if not self.script:
            raise AssertionError("unexpected extra request")
        response = self.script.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def download(self, url):
        return self.payload


def make_engine(tmp_path, monkeypatch, client, **profile):
    monkeypatch.setattr(Engine, "_client", lambda self: client)
    base = {
        "platform": 'deepinfra',
        "endpoint": TEXT_MODEL,
        "media_type": 'text',
        "parameters": {},
        "poll_interval": 0,
        "timeout_seconds": 0,
        "retry_on_429": 0,
    }
    base.update(profile)
    return Engine(base, tmp_path, api_key="test-key")


def an_input(tmp_path, prompt="a paper lantern"):
    path = tmp_path / "input.md"
    path.write_text(prompt + "\n")
    return InputFile(path=path, prompt=prompt)


def test_a_good_run_saves_a_file_and_records_the_payload(tmp_path, monkeypatch):
    client = FakeClient([
        {"id": "job-1", "status": "starting"},
        {"id": "job-1", "status": "succeeded", "output": ["https://cdn.invalid/out.png"]},
    ])
    results = make_engine(tmp_path, monkeypatch, client).run([an_input(tmp_path)])
    assert [result.status for result in results] == ["ok"]
    assert results[0].path.is_file()
    assert results[0].metadata["api_payload"]["prompt"] == "a paper lantern"


def test_an_empty_prompt_fails_before_any_call(tmp_path, monkeypatch):
    client = FakeClient([])
    results = make_engine(tmp_path, monkeypatch, client).run([an_input(tmp_path, prompt="")])
    assert results[0].status == "error"
    assert client.calls == []


def test_a_fatal_error_stops_the_batch(tmp_path, monkeypatch):
    client = FakeClient([ProviderError(401, "unauthorized")])
    results = make_engine(tmp_path, monkeypatch, client).run(
        [an_input(tmp_path), an_input(tmp_path)]
    )
    assert len(results) == 1


def test_the_catalogue_parses():
    assert len(load_catalog()) >= 1
