import unittest

from scripts.local_server import build_fetch_command, sanitize_output, validate_run_payload


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


if __name__ == "__main__":
    unittest.main()
