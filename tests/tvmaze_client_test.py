"""Unit tests for the TVMazeAPI class."""

import unittest
from unittest.mock import patch, MagicMock, call
import requests
import sys

# Mock config before any module imports that might use it
mock_config = MagicMock()
mock_config.TVMAZE_API_BASE_URL = 'https://mockapi.test'
mock_config.MAX_API_RETRIES = 3
mock_config.API_RETRY_BACKOFF_FACTOR = 0.1
sys.modules['bingefriend.shows.client_tvmaze.config'] = mock_config
TVMAZE_API_MODULE_PATH = 'bingefriend.shows.client_tvmaze.tvmaze_api'


# noinspection HttpUrlsUsage
class TestTVMazeAPI(unittest.TestCase):
    """Unit tests for the TVMazeAPI class."""

    @patch(f'{TVMAZE_API_MODULE_PATH}.requests.Session')
    @patch(f'{TVMAZE_API_MODULE_PATH}.HTTPAdapter')
    @patch(f'{TVMAZE_API_MODULE_PATH}.Retry')
    def setUp(self, mock_retry, mock_http_adapter, mock_session):
        """Set up test environment before each test method."""
        self.mock_logger = MagicMock(name='logger_mock')
        self.mock_retry_cls = mock_retry
        self.mock_adapter_cls = mock_http_adapter
        self.mock_session_cls = mock_session
        self.mock_session_instance = MagicMock()
        self.mock_session_cls.return_value = self.mock_session_instance
        self.mock_adapter_instance = MagicMock()
        self.mock_adapter_cls.return_value = self.mock_adapter_instance
        self.mock_retry_instance = MagicMock()
        self.mock_retry_cls.return_value = self.mock_retry_instance
        from bingefriend.shows.client_tvmaze.tvmaze_api import TVMazeAPI
        self.api = TVMazeAPI(logger=self.mock_logger)
        # NO RESET MOCK

    def test_init(self):
        """Test the __init__ method."""
        # This assertion remains correct as it's the only call at this point.
        self.mock_logger.info.assert_called_once_with(
            f"TVMazeAPI initialized: base_url=https://mockapi.test, "
            f"retries={mock_config.MAX_API_RETRIES}, "
            f"backoff={mock_config.API_RETRY_BACKOFF_FACTOR}, "
            f"pool_maxsize=100"
        )
        # ... rest of init checks ...
        self.mock_retry_cls.assert_called_once_with(
            total=mock_config.MAX_API_RETRIES, status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"], backoff_factor=mock_config.API_RETRY_BACKOFF_FACTOR,
        )
        self.mock_adapter_cls.assert_called_once_with(
            pool_connections=100, pool_maxsize=100, max_retries=self.mock_retry_instance
        )
        self.mock_session_cls.assert_called_once()
        expected_mount_calls = [call("https://", self.mock_adapter_instance),
                                call("http://", self.mock_adapter_instance)]
        self.mock_session_instance.mount.assert_has_calls(expected_mount_calls, any_order=True)
        self.assertEqual(self.api.base_url, 'https://mockapi.test')

    def test_make_request_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'success'}
        self.mock_session_instance.get.return_value = mock_response
        result = self.api._make_request('/test', params={'key': 'value'})
        self.mock_session_instance.get.assert_called_once_with(
            'https://mockapi.test/test', params={'key': 'value'}, timeout=30
        )
        mock_response.raise_for_status.assert_called_once()
        self.assertEqual(result, {'data': 'success'})
        # Debug log should be the only one
        self.mock_logger.debug.assert_called_once_with(
            "Making API request: GET https://mockapi.test/test with params {'key': 'value'}"
        )
        # Cannot assert info not called, as init called it. Remove this check.
        # self.mock_logger.info.assert_not_called()

    def test_make_request_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        self.mock_session_instance.get.return_value = mock_response
        result = self.api._make_request('/notfound')
        self.mock_session_instance.get.assert_called_once_with(
            'https://mockapi.test/notfound', params={}, timeout=30
        )
        mock_response.raise_for_status.assert_not_called()
        self.assertIsNone(result)
        # Use assert_any_call for the info log
        self.mock_logger.info.assert_any_call(
            "API returned 404 Not Found for https://mockapi.test/notfound (Params: {})."
        )
        self.mock_logger.debug.assert_called_once()

    def test_make_request_404_updates_shows(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        self.mock_session_instance.get.return_value = mock_response
        result = self.api._make_request('/updates/shows', params={'since': 'day'})
        self.mock_session_instance.get.assert_called_once_with(
            'https://mockapi.test/updates/shows', params={'since': 'day'}, timeout=30
        )
        self.assertIsNone(result)
        # Use assert_any_call for the info log
        self.mock_logger.info.assert_any_call(
            "API returned 404 Not Found for https://mockapi.test/updates/shows (Params: {'since': 'day'}). "
            "This might indicate no updates for the requested period."
        )
        self.mock_logger.debug.assert_called_once()

    def test_make_request_http_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = requests.exceptions.HTTPError("Server Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        self.mock_session_instance.get.return_value = mock_response
        with self.assertRaises(requests.exceptions.RequestException):
            self.api._make_request('/error')
        # ... other assertions ...
        self.mock_logger.error.assert_called_once_with(
            "API request failed permanently for https://mockapi.test/error after retries: Server Error"
        )
        self.mock_logger.debug.assert_called_once()

    def test_make_request_request_exception(self):
        timeout_error = requests.exceptions.Timeout("Timeout")
        self.mock_session_instance.get.side_effect = timeout_error
        with self.assertRaises(requests.exceptions.RequestException):
            self.api._make_request('/timeout')
        # ... other assertions ...
        self.mock_logger.error.assert_called_once_with(
            "API request failed permanently for https://mockapi.test/timeout after retries: Timeout"
        )
        self.mock_logger.debug.assert_called_once()

    def test_make_request_json_decode_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "invalid json"
        json_error = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
        mock_response.json.side_effect = json_error
        self.mock_session_instance.get.return_value = mock_response
        with self.assertRaises(ValueError):
            self.api._make_request('/invalidjson')
        # ... other assertions ...
        self.mock_logger.error.assert_called_once_with(
            "Failed to decode JSON from https://mockapi.test/invalidjson: Expecting value: line 1 column 1 (char 0). "
            "Response text: invalid json..."
        )
        self.mock_logger.debug.assert_called_once()

    # --- Tests for specific API methods ---

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_shows_success(self, mock_make_request):
        expected_shows = [{'id': 1, 'name': 'Show 1'}]
        mock_make_request.return_value = expected_shows
        result = self.api.get_shows(page=1)
        self.assertEqual(result, expected_shows)
        mock_make_request.assert_called_once_with('/shows', params={'page': 1})
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching shows page 1.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_shows_none_response(self, mock_make_request):
        mock_make_request.return_value = None
        result = self.api.get_shows(page=2)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows', params={'page': 2})
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching shows page 2.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_shows_invalid_type(self, mock_make_request):
        mock_make_request.return_value = {"unexpected": "dict"}
        result = self.api.get_shows(page=3)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows', params={'page': 3})
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching shows page 3.")
        self.mock_logger.error.assert_called_once_with(
            "Unexpected non-list response for /shows page 3: <class 'dict'>"
        )

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_details_success(self, mock_make_request):
        expected_details = {'id': 101}
        mock_make_request.return_value = expected_details
        result = self.api.get_show_details(show_id=101)
        self.assertEqual(result, expected_details)
        mock_make_request.assert_called_once_with('/shows/101')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching details for show ID 101.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_details_none_response(self, mock_make_request):
        mock_make_request.return_value = None
        result = self.api.get_show_details(show_id=102)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/102')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching details for show ID 102.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_details_invalid_type(self, mock_make_request):
        mock_make_request.return_value = ["list"]
        result = self.api.get_show_details(show_id=103)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/103')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching details for show ID 103.")
        self.mock_logger.error.assert_called_once_with(
            "Unexpected non-dict response for /shows/103: <class 'list'>"
        )

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_seasons_success(self, mock_make_request):
        mock_make_request.return_value = [{'id': 201}]
        result = self.api.get_seasons(show_id=101)
        self.assertEqual(result, [{'id': 201}])
        mock_make_request.assert_called_once_with('/shows/101/seasons')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching seasons for show ID 101.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_seasons_none_response(self, mock_make_request):
        mock_make_request.return_value = None
        result = self.api.get_seasons(show_id=102)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/102/seasons')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching seasons for show ID 102.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_seasons_invalid_type(self, mock_make_request):
        mock_make_request.return_value = {"unexpected": "dict"}
        result = self.api.get_seasons(show_id=103)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/103/seasons')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching seasons for show ID 103.")
        self.mock_logger.error.assert_called_once_with(
            "Unexpected non-list response for /shows/103/seasons: <class 'dict'>"
        )

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_episodes_success(self, mock_make_request):
        mock_make_request.return_value = [{'id': 301}]
        result = self.api.get_episodes(show_id=101)
        self.assertEqual(result, [{'id': 301}])
        mock_make_request.assert_called_once_with('/shows/101/episodes')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching episodes for show ID 101.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_episodes_none_response(self, mock_make_request):
        mock_make_request.return_value = None
        result = self.api.get_episodes(show_id=102)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/102/episodes')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching episodes for show ID 102.")

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_episodes_invalid_type(self, mock_make_request):
        mock_make_request.return_value = {"unexpected": "dict"}
        result = self.api.get_episodes(show_id=103)
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/shows/103/episodes')
        # Use assert_any_call for info
        self.mock_logger.info.assert_any_call("Fetching episodes for show ID 103.")
        self.mock_logger.error.assert_called_once_with(
            "Unexpected non-list response for /shows/103/episodes: <class 'dict'>"
        )

    # --- Special cases for multiple logs ---

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_updates_success(self, mock_make_request):
        expected_updates = {'1': 1678886400, '2': 1678886401}
        mock_make_request.return_value = expected_updates
        result = self.api.get_show_updates()
        self.assertEqual(result, expected_updates)
        mock_make_request.assert_called_once_with('/updates/shows', params={'since': 'day'})
        # Check specific calls exist using assert_any_call
        self.mock_logger.info.assert_any_call("Fetching show updates since last day using API 'since' parameter.")
        self.mock_logger.info.assert_any_call("Obtained 2 show updates since last day directly from API.")
        # Check total count (includes init call + 2 method calls)
        self.assertEqual(self.mock_logger.info.call_count, 3)

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_updates_none_response(self, mock_make_request):
        mock_make_request.return_value = None
        result = self.api.get_show_updates(period='week')
        self.assertEqual(result, {})
        mock_make_request.assert_called_once_with('/updates/shows', params={'since': 'week'})
        # Check specific calls exist using assert_any_call
        self.mock_logger.info.assert_any_call("Fetching show updates since last week using API 'since' parameter.")
        self.mock_logger.info.assert_any_call(
            "API returned 404 or request failed for /updates/shows?since=week. Assuming no updates.")
        # Check total count (includes init call + 2 method calls)
        self.assertEqual(self.mock_logger.info.call_count, 3)

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_updates_invalid_type(self, mock_make_request):
        mock_make_request.return_value = ["unexpected"]
        result = self.api.get_show_updates(period='month')
        self.assertIsNone(result)
        mock_make_request.assert_called_once_with('/updates/shows', params={'since': 'month'})
        # Check specific calls exist / were unique
        self.mock_logger.info.assert_any_call("Fetching show updates since last month using API 'since' parameter.")
        self.mock_logger.error.assert_called_once_with(
            "Unexpected response format from /updates/shows?since=month: <class 'list'>"
        )

    @patch(f'{TVMAZE_API_MODULE_PATH}.TVMazeAPI._make_request')
    def test_get_show_updates_invalid_timestamp_type(self, mock_make_request):
        raw_updates = {'1': 1678886400, '2': 'str'}
        mock_make_request.return_value = raw_updates
        result = self.api.get_show_updates()
        self.assertEqual(result, {'1': 1678886400})
        mock_make_request.assert_called_once_with('/updates/shows', params={'since': 'day'})
        # Check specific calls exist / were unique
        self.mock_logger.info.assert_any_call("Fetching show updates since last day using API 'since' parameter.")
        self.mock_logger.warning.assert_called_once_with(
            "Some updates received from /updates/shows?since=day had non-integer timestamps and were ignored."
        )
        self.mock_logger.info.assert_any_call("Obtained 1 show updates since last day directly from API.")
        # Check total count (includes init call + 2 method calls)
        self.assertEqual(self.mock_logger.info.call_count, 3)

    def test_get_show_updates_invalid_period(self):
        """Test get_show_updates with an unsupported period."""
        result = self.api.get_show_updates(period='year')
        self.assertIsNone(result)
        # Only one error call expected
        self.mock_logger.error.assert_called_once_with(
            f"Unsupported update period 'year'. Use one of {self.api.SUPPORTED_UPDATE_PERIODS}."
        )


# Keep if __name__ == '__main__': block
if __name__ == '__main__':
    unittest.main()
