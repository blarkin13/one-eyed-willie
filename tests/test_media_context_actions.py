"""Guardrails for explicitly confirmed media-manager delete actions."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from server.media_actions import (
    DeleteSelection, _selection, _manager_match,
    delete_media, media_action_preview,
)


class MediaContextDeletionTests(unittest.TestCase):
    def setUp(self):
        self.movie = patch(
            "server.media_actions.movies._movie_path",
            return_value=({"title": "Arrival", "year": 2016}, None, None),
        )
        self.movie.start()
        self.addCleanup(self.movie.stop)
        self.show = patch(
            "server.media_actions.tv.local_show",
            return_value={
                "title": "Example", "year": 2019,
                "episodes": [
                    {"id": 5, "season": 1, "episode": 1},
                    {"id": 6, "season": 1, "episode": 2},
                    {"id": 7, "season": 2, "episode": 1},
                ],
            },
        )
        self.show.start()
        self.addCleanup(self.show.stop)

    def test_scope_validation_never_expands_movie_or_episode(self):
        with self.assertRaises(HTTPException):
            _selection("movies", 1, "arrival:2016", "series")
        with self.assertRaises(HTTPException):
            _selection("tv", 2, "example:2019", "episode", 999)
        info = _selection("tv", 2, "example:2019", "episode", 5)
        self.assertEqual(info["name"], "Example S01E01")
        self.assertEqual(info["season_number"], 1)

    @patch("server.media_actions.arr._get")
    @patch("server.media_actions.arr._settings", return_value={"url": "http://localhost"})
    def test_ambiguous_manager_titles_refuse_deletion(self, settings, get):
        get.return_value = [
            {"id": 11, "title": "Arrival", "year": 2016},
            {"id": 12, "title": "Arrival", "year": 2016},
        ]
        with self.assertRaises(HTTPException) as raised:
            _manager_match(_selection("movies", 1, "arrival:2016", "movie"))
        self.assertEqual(raised.exception.status_code, 409)

    @patch("server.media_actions._delete_manager")
    @patch("server.media_actions._manager_match")
    def test_exact_confirmation_and_manager_id_required(self, match, delete):
        match.return_value = {"id": 42, "title": "Arrival"}
        selection = DeleteSelection(
            kind="movies", library_id=1, key="arrival:2016", scope="movie",
            manager_id=42, confirm_title="A different movie",
            remove_from_manager=True,
        )
        with self.assertRaises(HTTPException):
            delete_media(selection)
        delete.assert_not_called()
        selection.confirm_title = "Arrival"
        selection.manager_id = 43
        with self.assertRaises(HTTPException):
            delete_media(selection)
        delete.assert_not_called()

    @patch("server.media_actions._delete_manager")
    @patch("server.media_actions._manager_match")
    def test_delete_manager_record_without_files_is_explicit(self, match, delete):
        match.return_value = {"id": 42, "title": "Arrival"}
        selection = DeleteSelection(
            kind="movies", library_id=1, key="arrival:2016", scope="movie",
            manager_id=42, confirm_title="Arrival",
            remove_from_manager=True, delete_files=False,
        )
        result = delete_media(selection)
        self.assertTrue(result["manager_record_removed"])
        self.assertFalse(result["rescan_required"])
        delete.assert_called_once_with("radarr", "movie", 42, {
            "deleteFiles": "false", "addImportExclusion": "false"
        })

    @patch("server.media_actions._episode_file_ids", return_value=[15, 17])
    @patch("server.media_actions._delete_manager")
    @patch("server.media_actions._manager_match")
    def test_episode_and_season_never_remove_sonarr_series(self, match, delete, files):
        match.return_value = {"id": 80, "title": "Example"}
        selection = DeleteSelection(
            kind="tv", library_id=2, key="example:2019",
            scope="season", season_number=1,
            manager_id=80, confirm_title="Example Season 1",
            delete_files=True, remove_from_manager=False,
        )
        result=delete_media(selection)
        self.assertEqual(result["files_requested"],2)
        self.assertFalse(result["manager_record_removed"])
        self.assertEqual(delete.call_args_list[0].args,
                         ("sonarr", "episodefile", 15))
        self.assertEqual(delete.call_args_list[1].args,
                         ("sonarr", "episodefile", 17))
        selection.remove_from_manager=True
        with self.assertRaises(HTTPException):
            delete_media(selection)

    @patch("server.media_actions._manager_match", return_value=None)
    @patch("server.media_actions.arr._settings", return_value={"url": "http://localhost"})
    def test_preview_does_not_offer_unknown_title(self, settings, match):
        response=media_action_preview(
            kind="movies",library_id=1,key="arrival:2016",scope="movie"
        )
        self.assertIsNone(response["manager_id"])
        self.assertFalse(response["media_files_writable"])


if __name__ == "__main__":
    unittest.main()
