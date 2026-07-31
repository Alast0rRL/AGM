"""Configuration settings for Nekto.me chat automator."""

import os
from dotenv import load_dotenv

load_dotenv()

REMOTE_DEBUGGING_PORT = int(os.getenv("REMOTE_DEBUGGING_PORT", "9222"))
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "")
