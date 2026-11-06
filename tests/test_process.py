import subprocess
import sys
import os
import tempfile
import unittest


class ShutdownTests(unittest.TestCase):
    def test_sigterm_closes_application_without_dialog(self):
        script = """
import os, signal
from PySide6.QtCore import QTimer
from minidv_capture import __main__ as entry
original_show = entry.MainWindow.show
def show(window):
    original_show(window)
    QTimer.singleShot(100, lambda: os.kill(os.getpid(), signal.SIGTERM))
entry.MainWindow.show = show
raise SystemExit(entry.main())
"""
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       XDG_DATA_HOME=directory, XDG_CONFIG_HOME=directory)
            result = subprocess.run([sys.executable, '-c', script], env=env,
                                    capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

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
