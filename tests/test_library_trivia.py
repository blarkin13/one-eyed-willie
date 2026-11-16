"""Trivia carousel sequence and responsive library masthead regression checks."""
import re
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"


class LibraryTriviaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (SERVER / "catalog.html").read_text()
        cls.settings = (SERVER / "settings_hub.html").read_text()
        cls.credits = (SERVER / "credits.html").read_text()
        cls.main = (SERVER / "main.py").read_text()

    def test_question_revealed_before_answer_and_next_question(self):
        page = self.page
        self.assertIn("const TRIVIA_QUESTION_MS=6200;", page)
        self.assertIn("const TRIVIA_ANSWER_MS=5200;", page)
        self.assertIn("scheduleTrivia(revealTriviaAnswer,TRIVIA_QUESTION_MS);", page)
        self.assertIn("scheduleTrivia(showNextTrivia,TRIVIA_ANSWER_MS);", page)
        self.assertIn("triviaAnswer.setAttribute('aria-hidden','true');", page)
        self.assertIn("triviaAnswerText.textContent='';", page)
        self.assertIn("triviaAnswerText.textContent=triviaCurrent?.answer||'';", page)
        self.assertIn("triviaAnswer.setAttribute('aria-hidden','false');", page)
        self.assertIn("triviaAnswer.classList.add('revealed');", page)

    def test_offline_fallback_is_in_question_answer_format(self):
        page = self.page
        movie = page.split("const fallbackTrivia={", 1)[1].split("tv:[", 1)[0]
        tv = page.split("tv:[", 1)[1].split("function triviaStorage", 1)[0]
        self.assertGreaterEqual(movie.count("{question:"), 10)
        self.assertGreaterEqual(tv.count("{question:"), 10)
        self.assertIn("nextTriviaFromQueue()||nextOfflineTrivia()", page)
        self.assertIn("fetchTriviaBatch()", page)

    def test_web_trivia_is_preserved_with_malformed_content_skipped(self):
        page = self.page
        self.assertIn("https://opentdb.com/api.php?amount=40&category=", page)
        self.assertIn("decodeURIComponent(row.question)", page)
        self.assertIn("decodeURIComponent(row.correct_answer)", page)
        self.assertIn("historyKey", page)
        self.assertIn("seen.has(question)", page)
        self.assertIn("triviaFetching", page)

    def test_no_header_attribution_but_accessible_credits_remain(self):
        self.assertNotIn("id=\"trivia-credit\"", self.page)
        self.assertNotIn("Trivia from <a", self.page)
        self.assertIn('href="/settings/credits"', self.settings)
        self.assertIn("Open Trivia Database", self.credits)
        self.assertIn("CC BY-SA 4.0", self.credits)
        self.assertIn("https://creativecommons.org/licenses/by-sa/4.0/", self.credits)
        self.assertIn("The app adapts the presentation", self.credits)
        self.assertIn('@app.get("/settings/credits")', self.main)

    def test_larger_trivia_and_tv_responsive_layout(self):
        page = self.page
        self.assertIn(".library-trivia .trivia-question{", page)
        self.assertIn("font-size:clamp(1.25rem,1.52vw,2rem)", page)
        self.assertIn("@media(min-width:1600px)", page)
        self.assertIn("font-size:clamp(1.65rem,1.6vw,2.4rem)", page)
        self.assertIn("@media(max-width:760px)", page)
        self.assertIn("@media(prefers-reduced-motion:reduce)", page)
        self.assertIn("document.addEventListener('visibilitychange'", page)
        self.assertIn("window.addEventListener('pagehide'", page)
        self.assertIn("min-height:155px", page)
        self.assertIn('id="trivia-question"', page)
        self.assertIn('id="trivia-answer-text"', page)


if __name__ == "__main__":
    unittest.main()
