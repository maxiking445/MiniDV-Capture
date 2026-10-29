import os
from pathlib import Path
import subprocess
import unittest


class InstallerTests(unittest.TestCase):
    def run_installer(self, manager, native_qt=True, full_ffmpeg=False, fail=False):
        # Source the installer, replacing all external commands that could
        # install software. Never call main() or change system access rules.
        script = '''
source "$INSTALLER"
command() {
    if [[ "$1" == -v ]]; then
        [[ "$2" == "$MANAGER" ]]
    else
        builtin command "$@"
    fi
}
pacman() { echo "pacman $*"; [[ "$FAIL" == 0 ]]; }
apt-get() { echo "apt-get $*"; [[ "$FAIL" == 0 ]]; }
apt-cache() { [[ "$NATIVE_QT" == 1 ]]; }
dnf() {
    if [[ "$1" == list ]]; then [[ "$FULL_FFMPEG" == 1 ]]; return; fi
    echo "dnf $*"
    [[ "$FAIL" == 0 ]]
}
install_components
'''
        env = dict(os.environ, INSTALLER=str(Path('scripts/setup-system.sh').resolve()),
                   MANAGER=manager, NATIVE_QT=str(int(native_qt)), FULL_FFMPEG=str(int(full_ffmpeg)),
                   FAIL=str(int(fail)))
        return subprocess.run(['/bin/bash', '-c', script], env=env, capture_output=True, text=True)

    def test_pacman_without_partial_upgrade(self):
        result = self.run_installer('pacman')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('pacman -S --needed --noconfirm', result.stdout)
        self.assertNotIn('-Sy', result.stdout)

    def test_apt_native_and_user_runtime_fallback(self):
        for native in (True, False):
            with self.subTest(native=native):
                result = self.run_installer('apt-get', native_qt=native)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('apt-get update', result.stdout)
                self.assertIn('python3-venv dvgrab ffmpeg', result.stdout)
                self.assertEqual('python3-pyside6.qtwidgets' in result.stdout, native)
                if not native:
                    self.assertIn('user-owned virtual environment', result.stdout)

    def test_dnf_full_or_restricted_ffmpeg(self):
        for full in (True, False):
            with self.subTest(full=full):
                result = self.run_installer('dnf', full_ffmpeg=full)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('python3-pyside6', result.stdout)
                self.assertIn('dnf install -y ffmpeg' + ('\n' if full else '-free\n'), result.stdout)

    def test_install_failure_and_unsupported_manager_are_not_successful(self):
        for manager in ('pacman', 'apt-get', 'dnf', 'unknown'):
            with self.subTest(manager=manager):
                self.assertNotEqual(self.run_installer(manager, fail=True).returncode, 0)
