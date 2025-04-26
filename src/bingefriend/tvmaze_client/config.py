"""Configuration for TVMaze API client."""

import os

TVMAZE_API_BASE_URL = os.getenv('TVMAZE_API_BASE_URL', 'https://api.tvmaze.com')
MAX_API_RETRIES = int(os.getenv('MAX_API_RETRIES', 5))
API_RETRY_BACKOFF_FACTOR = float(os.getenv('API_RETRY_BACKOFF_FACTOR', 0.5))
