"""The four answers the conformance suite needs from this engine."""

from __future__ import annotations

from engine_conformance import Behaviours, Call, Connector, Provider


class Connector(Connector):
    package = "engine_deepinfra"

    entries = {'text_to_image': 'LLM-Models/completions.toml', 'image_to_video': 'VID-Models/videos.toml'}

    provider_modules = ()

    def install(self, monkeypatch, behaviours: Behaviours) -> Provider:
        provider = Provider()
        state = {"submit": list(behaviours.submit_errors), "polls": 0}

        class FakeClient:
            def request_json(self, method, path, payload=None, *, headers=None, params=None):
                if method == "POST":
                    provider.calls.append(Call(kind="submit", payload=payload, path=path))
                    if behaviours.submit_error is not None:
                        raise behaviours.submit_error
                    if state["submit"]:
                        raise state["submit"].pop(0)
                    return {"id": "job-1", "status": "starting"}

                provider.calls.append(Call(kind="poll", path=path))
                if behaviours.poll_error is not None:
                    raise behaviours.poll_error
                statuses = behaviours.poll_statuses
                index = min(state["polls"], len(statuses) - 1)
                state["polls"] += 1
                status = statuses[index]
                record = {"id": "job-1", "status": status}
                if status == "succeeded":
                    record["output"] = list(behaviours.result_urls)
                return record

            def download(self, url):
                provider.downloads.append(url)
                provider.calls.append(Call(kind="download", url=url))
                if behaviours.download_error is not None:
                    raise behaviours.download_error
                return behaviours.result_bytes

        fake = FakeClient()
        monkeypatch.setattr(self.engine_class(), "_client", lambda _self: fake)
        return provider
