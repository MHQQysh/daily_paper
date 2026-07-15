import json
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

from http.server import ThreadingHTTPServer

from scripts import paper_service
from scripts.local_server import OPERATION_LOCK, LocalRequestHandler, build_fetch_command, sanitize_output, validate_run_payload


class LocalServerValidationTests(unittest.TestCase):
    def test_valid_request_is_normalized(self):
        request = validate_run_payload(
            {
                "lookback_days": "3",
                "target_date": "2026-07-13",
                "max_results": "20",
                "min_score": "18",
                "fresh": True,
                "topics": [{"id": "token-pruning", "name": "Token pruning", "keywords": ["token pruning"]}],
                "deepseek_api_key": "sk-test",
            }
        )

        self.assertEqual(request["lookback_days"], 3)
        self.assertEqual(request["target_date"], "2026-07-13")
        self.assertEqual(request["max_results"], 20)
        self.assertNotIn("fresh", request)

    def test_invalid_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "target_date"):
            validate_run_payload({"target_date": "2026-99-99"})

    def test_out_of_range_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_results"):
            validate_run_payload({"max_results": 1001})

    def test_command_contains_selected_options(self):
        request = validate_run_payload(
            {
                "lookback_days": 7,
                "target_date": "2026-07-13",
                "max_results": 10,
                "min_score": 12,
                "fresh": True,
                "topics": [{"id": "visual-token-pruning", "name": "Visual token pruning", "keywords": ["visual token"]}],
            }
        )

        command = build_fetch_command(request)

        self.assertIn("--date", command)
        self.assertIn("2026-07-13", command)
        self.assertNotIn("--fresh", command)
        self.assertIn("--topics-json", command)
        self.assertNotIn("deepseek_api_key", " ".join(command))

    def test_api_key_is_removed_from_output(self):
        self.assertEqual(sanitize_output("failed for sk-secret", "sk-secret"), "failed for [redacted]")

    def test_topic_catalog_route_returns_project_configuration(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            expected = [{"id": "topic-example", "name": "Example", "keywords": ["example"]}]
            with mock.patch.object(paper_service, "load_topic_catalog", return_value=expected) as load:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/api/topics", timeout=5
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(body, {"topics": expected})
            load.assert_called_once()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_delete_route_returns_service_result(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            payload = json.dumps({"paper": {"title": "Paper", "source_id": "2607.12345v1"}}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/papers/delete",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            expected = {"deleted": 1, "total": 4}
            with mock.patch.object(paper_service, "delete_paper", return_value=expected) as delete:
                with urllib.request.urlopen(request, timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(body, expected)
            delete.assert_called_once()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_delete_route_maps_missing_paper_to_404(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            payload = json.dumps({"paper": {"title": "Missing", "source_id": "2607.12345v1"}}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/papers/delete",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with mock.patch.object(paper_service, "delete_paper", side_effect=LookupError("Paper was not found")):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 404)
            body = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual(body["error"], "Paper was not found")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_topic_save_route_returns_persisted_catalog(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            topics = [{"id": "topic-example", "name": "Example", "keywords": ["example"]}]
            payload = json.dumps({"topics": topics}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/topics/save",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            expected = {"topics": topics, "count": 1}
            with mock.patch.object(paper_service, "save_topics", return_value=expected) as save:
                with urllib.request.urlopen(request, timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(body, expected)
            save.assert_called_once_with(topics)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_pdf_resolution_returns_conflict_while_another_operation_runs(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        acquired = OPERATION_LOCK.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            payload = json.dumps({"input": "https://example.org/paper.pdf"}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/papers/resolve",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with mock.patch.object(paper_service, "resolve_paper_input", return_value=[]):
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 409)
            body = json.loads(raised.exception.read().decode("utf-8"))
            self.assertIn("Another paper operation", body["error"])
        finally:
            OPERATION_LOCK.release()
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
