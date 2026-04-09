# conftest.py (project root)

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Silence noisy uiautomation debug output
logging.getLogger("uiautomation").setLevel(logging.CRITICAL)
logging.getLogger("mbu_dev_shared_components").setLevel(logging.WARNING)
