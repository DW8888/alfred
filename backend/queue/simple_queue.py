import json
import threading
import os

class SimpleQueue:
    """
    A lightweight thread-safe JSON-backed FIFO queue.
    Perfect for agent-to-agent task passing.
    """

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()

        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump({"queue": []}, f)

    # --------------------------
    # Internal helpers
    # --------------------------
    def _read(self):
        with open(self.path, "r") as f:
            return json.load(f)["queue"]

    def _write(self, q):
        with open(self.path, "w") as f:
            json.dump({"queue": q}, f, indent=2)

    # --------------------------
    # Public API
    # --------------------------
    def push(self, item):
        """Add item to the back of queue."""
        with self.lock:
            q = self._read()
            q.append(item)
            self._write(q)

    def pop(self):
        """Retrieve and remove the next item. Returns None if empty."""
        with self.lock:
            q = self._read()
            if not q:
                return None
            item = q.pop(0)
            self._write(q)
            return item

    def peek(self):
        """Look at next item without consuming."""
        with self.lock:
            q = self._read()
            return q[0] if q else None

    def size(self):
        with self.lock:
            return len(self._read())

    def clear(self):
        with self.lock:
            self._write([])
