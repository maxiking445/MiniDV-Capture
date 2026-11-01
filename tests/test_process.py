import subprocess
import sys
import unittest


class ShutdownTests(unittest.TestCase):
    def test_watchdog_exits_blocked_app_and_terminates_owned_child(self):
        # The child inherits stdout. communicate() only finishes promptly when
        # both the stuck application and its child have actually exited.
        script = '''
import subprocess
import sys
import time
from minidv_capture.process import start_shutdown_watchdog
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'])
start_shutdown_watchdog([child.pid], timeout=0.1)
time.sleep(4)
raise SystemExit(7)
'''
        result = subprocess.run([sys.executable, '-c', script],
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
