import os
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded for tests
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
