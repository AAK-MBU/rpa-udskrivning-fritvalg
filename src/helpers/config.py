"""Module for general configurations of the process"""

MAX_RETRY = 10

# ----------------------
# Queue population settings
# ----------------------
MAX_CONCURRENCY = 100  # tune based on backend capacity
MAX_RETRIES = 3  # transient failure retries per item
RETRY_BASE_DELAY = 0.5  # seconds (exponential backoff)

# ----------------------
# File settings
# ----------------------
TMP_FOLDER = "C:\\tmp\\tmt"

# ----------------------
# Process dashboard
# ----------------------
PROCESS_NAME = "Frit valg"
PROCESS_STEP_NAME = "Journalmateriale sendt og journaliseret"
