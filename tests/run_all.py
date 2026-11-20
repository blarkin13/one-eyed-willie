"""Run the whole unittest suite with output that survives non-blocking pipes.

Browser tests start Playwright's Node driver, which inherits this process's
stdout/stderr and switches the shared pipe to non-blocking. A later status
line can then fail with BlockingIOError even though every test passed, so
writes here put the pipe back to blocking and try again.
"""
import os
import sys
import unittest


class SteadyStream:
    def __init__(self, stream):
        self._stream = stream

    def _retry(self, action):
        for _ in range(1000):
            try:
                return action()
            except BlockingIOError:
                try:
                    os.set_blocking(self._stream.fileno(), True)
                except (OSError, ValueError):
                    pass
        return action()

    def write(self, text):
        return self._retry(lambda: self._stream.write(text))

    def flush(self):
        return self._retry(self._stream.flush)

    def __getattr__(self, name):
        return getattr(self._stream, name)


if __name__ == "__main__":
    for fd in (1, 2):
        try:
            os.set_blocking(fd, True)
        except OSError:
            pass
    sys.stdout = SteadyStream(sys.stdout)
    sys.stderr = SteadyStream(sys.stderr)
    tests = os.path.dirname(os.path.abspath(__file__))
    # Same import path as `python -m unittest discover -s tests` from the repo root.
    sys.path.insert(0, os.getcwd())
    unittest.main(module=None, argv=[sys.argv[0], "discover", "-s", tests, "-t", tests, "-v", *sys.argv[1:]])
