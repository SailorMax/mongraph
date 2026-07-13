import signal
import sys
import time
import asyncio
from tools.metrics import RefreshMetrics

keep_running = True


def handle_kill_signal(signum, frame):
    """Callback function triggered when a registered signal is received."""
    global keep_running
    print(f"Received termination signal ({signum}). Shutting down...")
    keep_running = False


signal.signal(signal.SIGTERM, handle_kill_signal)  # (e.g., kill command)
signal.signal(signal.SIGINT, handle_kill_signal)  # (e.g., Ctrl+C)

try:
    # while keep_running:
    #     asyncio.run(RefreshMetrics())
    #     time.sleep(1)
    asyncio.run(RefreshMetrics())

except Exception as e:
    print(f"An unexpected error occurred: {e}")

print("Shutdown completed.")
sys.exit(0)
