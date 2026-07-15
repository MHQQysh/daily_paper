from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicSiteContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        self.javascript = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        self.styles = (ROOT / "docs" / "styles.css").read_text(encoding="utf-8")

    def test_public_mode_hides_every_mutation_control(self):
        self.assertIn('id="searchModeLabel"', self.html)
        self.assertIn('id="runPanel"', self.html)
        self.assertIn("runPanel.hidden = !IS_LOCAL_MODE;", self.javascript)
        self.assertIn("editTopicsButton.hidden = !IS_LOCAL_MODE;", self.javascript)
        self.assertIn("addPaperButton.hidden = !IS_LOCAL_MODE;", self.javascript)
        self.assertIn('[hidden]', self.styles)

    def test_public_mode_is_search_only_and_ignores_browser_topic_edits(self):
        self.assertIn(
            'searchModeLabel.textContent = IS_LOCAL_MODE ? "Search or add paper" : "Search papers";',
            self.javascript,
        )
        self.assertIn(
            "state.topics = IS_LOCAL_MODE ? loadStoredTopics(state.serverTopics) : state.serverTopics;",
            self.javascript,
        )
        self.assertNotIn("dailyPaper.githubToken", self.javascript)
        self.assertNotIn("api.github.com/repos", self.javascript)

    def test_local_mode_keeps_the_existing_search_action(self):
        self.assertIn('runSearchButton.textContent = "Run local search";', self.javascript)
        self.assertIn(
            'runSearchButton.addEventListener("click", () => {\n  triggerLocalRun().catch',
            self.javascript,
        )

    def test_pages_workflow_only_deploys_the_committed_snapshot(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("push:", workflow)
        self.assertIn("path: docs", workflow)
        self.assertNotIn("fetch_papers.py", workflow)
        self.assertNotIn("schedule:", workflow)


if __name__ == "__main__":
    unittest.main()
