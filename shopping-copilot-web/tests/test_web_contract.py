from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


WEB_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = WEB_ROOT.parent
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from backend.app import create_app  # noqa: E402


class FakeService:
    def __init__(self, ready: bool) -> None:
        self.started = False
        self._status = {
            "ready": ready,
            "loading": not ready,
            "error": "",
            "phase": "ready" if ready else "algorithm_index",
            "progress": 100 if ready else 18,
            "message": "Catalog index is ready" if ready else "Building indexes",
            "elapsedSeconds": 1.2,
            "interfaceVersion": "1.0",
        }

    @property
    def status(self):
        return dict(self._status)

    def start_loading(self):
        self.started = True

    def list_samples(self):
        return [{"id": "public_0001", "scenario": "buying", "difficulty": "easy"}]

    def best_completed_run(self):
        return {"summary": {"technicalScore": 0.98}, "links": [], "scenarios": [], "results": []}

    def run_single(self, sample_id, paraphrase_level):
        if sample_id != "public_0001":
            raise KeyError(sample_id)
        return {"sample": {"id": sample_id}, "paraphraseLevel": paraphrase_level}


class FakeJobs:
    def create(self, paraphrase_level, limit):
        return {"id": "job1", "status": "queued", "current": 0, "total": limit, "mode": paraphrase_level}

    def get(self, job_id):
        if job_id != "job1":
            raise KeyError(job_id)
        return {"id": job_id, "status": "completed", "current": 20, "total": 20}


class WebContractTests(unittest.TestCase):
    def test_static_shell_is_available_while_index_builds(self):
        fake = FakeService(ready=False)
        with TestClient(create_app(fake, FakeJobs())) as client:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn('id="indexLoader"', page.text)
            self.assertIn('class="app-frame app-hidden"', page.text)
            self.assertNotIn("Demo mode", page.text)
            self.assertEqual(client.get("/static/app.css").status_code, 200)
            self.assertEqual(client.get("/static/app.js").status_code, 200)
        self.assertTrue(fake.started)

    def test_health_is_non_blocking_and_bootstrap_is_gated(self):
        with TestClient(create_app(FakeService(ready=False), FakeJobs())) as client:
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertFalse(health.json()["ready"])
            self.assertEqual(health.json()["progress"], 18)
            self.assertEqual(client.get("/api/bootstrap").status_code, 425)

    def test_ready_bootstrap_and_default_config(self):
        with TestClient(create_app(FakeService(ready=True), FakeJobs())) as client:
            payload = client.get("/api/bootstrap")
            self.assertEqual(payload.status_code, 200)
            self.assertEqual(payload.json()["config"], "default.json")
            self.assertEqual(len(payload.json()["samples"]), 1)
            rejected = client.post("/api/eval/jobs", json={"config": "other.json"})
            self.assertEqual(rejected.status_code, 400)

    def test_session_and_job_routes_keep_the_existing_contract(self):
        with TestClient(create_app(FakeService(ready=True), FakeJobs())) as client:
            session = client.post(
                "/api/session/run",
                json={"sampleId": "public_0001", "paraphraseLevel": 9},
            )
            self.assertEqual(session.status_code, 200)
            self.assertEqual(session.json()["paraphraseLevel"], 2)
            job = client.post(
                "/api/eval/jobs",
                json={"config": "default.json", "paraphraseLevel": 1, "limit": 20},
            )
            self.assertEqual(job.status_code, 200)
            self.assertEqual(job.json()["total"], 20)
            self.assertEqual(client.get("/api/eval/jobs/job1").status_code, 200)

    def test_framework_and_algorithm_boundaries(self):
        javascript = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        html = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        adapter = (WEB_ROOT / "backend" / "evaluation_service.py").read_text(encoding="utf-8")
        self.assertNotIn("React", javascript)
        self.assertNotIn("demoMode", javascript)
        self.assertNotIn("Demo mode", html)
        for internal in ("from copilot.algo", "from copilot.core", "from copilot.agent", "from copilot.eval"):
            self.assertNotIn(internal, adapter)
        self.assertIn("from copilot.public_api import ShoppingCopilotRuntime", adapter)

    def test_default_is_the_only_config(self):
        development = sorted(path.name for path in (WORKSPACE / "shopping-copilot" / "configs").glob("*.json"))
        submission = sorted(path.name for path in (WORKSPACE / "submission" / "configs").glob("*.json"))
        self.assertEqual(development, ["default.json"])
        self.assertEqual(submission, ["default.json"])


if __name__ == "__main__":
    unittest.main()
