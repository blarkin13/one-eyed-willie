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

    def test_compact_top_row_controls_and_trivia_below(self):
        page = self.page
        header = page.split('<div class="page-head library-head"', 1)[1].split(
            '<div class="section-heading">', 1)[0]
        self.assertLess(header.index('class="library-heading"'),
                        header.index('class="library-head-actions"'))
        self.assertLess(header.index('class="library-head-actions"'),
                        header.index('class="library-trivia"'))
        self.assertIn('class="library-head-top"', header)
        self.assertIn('id="search"', header)
        self.assertIn('id="sort-toggle"', header)
        self.assertIn('id="genre-toggle"', header)
        self.assertIn('id="refresh-metadata"', header)
        self.assertIn('id="explore-library"', header)
        self.assertIn(".library-head-top{display:flex;align-items:center;justify-content:space-between;", page)
        self.assertIn("flex-wrap:nowrap;overflow:visible", page)
        self.assertIn(".library-header-art-frame{position:absolute;inset:0;overflow:hidden;", page)
        self.assertNotIn(".library-head-actions{align-self:flex-end", page)
        self.assertNotIn(".library-head{min-height:355px", page)
        self.assertNotIn(".library-head{min-height:305px", page)
        self.assertIn("#status:empty{display:none}", page)

    def test_trivia_height_stays_fixed_when_question_or_answer_wraps(self):
        page = self.page
        # Fixed four-line question and three-line answer reservations prevent
        # layout reflow as the timed question/answer carousel changes text.
        self.assertIn("height:5.44em;min-height:0;", page)
        self.assertIn("height:4.2em;min-height:0;flex:none;overflow:hidden;", page)
        self.assertIn("-webkit-line-clamp:4", page)
        self.assertIn("-webkit-line-clamp:3", page)
        self.assertIn(".library-trivia .trivia-answer{font-size:clamp(1rem,3.3vw,1.32rem)}", page)
        self.assertIn("scheduleTrivia(showNextTrivia,TRIVIA_ANSWER_MS)", page)

    def test_trivia_remains_large_on_tv_and_responsive(self):
        page = self.page
        self.assertIn(".library-trivia .trivia-question{", page)
        self.assertIn("font-size:clamp(1.25rem,1.52vw,2rem)", page)
        self.assertIn("min-height:2.6em", page)
        self.assertIn("min-height:2.5em", page)
        self.assertIn("@media(min-width:1600px)", page)
        self.assertIn("font-size:clamp(1.65rem,1.6vw,2.4rem)", page)
        self.assertIn("@media(min-width:761px) and (hover:none)", page)
        self.assertIn("@media(max-width:760px)", page)
        self.assertIn("@media(prefers-reduced-motion:reduce)", page)
        self.assertIn("document.addEventListener('visibilitychange'", page)
        self.assertIn("window.addEventListener('pagehide'", page)
        self.assertIn('id="trivia-question"', page)
        self.assertIn('id="trivia-answer-text"', page)


if __name__ == "__main__":
    unittest.main()
