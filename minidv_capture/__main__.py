import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from PySide6.QtCore import QLockFile, QStandardPaths, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from .storage import Store
from .gui import MainWindow, apply_theme
from .process import available, start_shutdown_watchdog


def main():
    smoke_test = '--smoke-test' in sys.argv
    if len(sys.argv) == 3 and sys.argv[1] in ('--media-status', '--transport-stop'):
        from .tape_change import query_medium
        try:
            print(query_medium(sys.argv[2], stop_transport=sys.argv[1] == '--transport-stop'))
        except (OSError, ValueError, AttributeError):
            print('unsupported')
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName('MiniDV Capture')
    app.setOrganizationName('MiniDVCapture')
    app.setDesktopFileName('minidv-capture')
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    data.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / 'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if smoke_test:
            print('Smoke test failed: application lock is already held.', file=sys.stderr)
            return 1
        QMessageBox.information(None, 'MiniDV Capture', 'MiniDV Capture is already running. Open the existing window.')
        return 0
    handler = RotatingFileHandler(data / 'application.log', maxBytes=2_000_000, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    smoke_exit_code = 0
    def exception_hook(kind, value, traceback):
        nonlocal smoke_exit_code
        logging.error('Unhandled error', exc_info=(kind, value, traceback))
        if smoke_test:
            smoke_exit_code = 1
            sys.__excepthook__(kind, value, traceback)
            app.exit(1)
            return
        QMessageBox.critical(None, 'MiniDV Capture', f'Error: {value}\nLog: {data / "application.log"}')
    sys.excepthook = exception_hook
    try:
        store = Store(data / 'queue.json')
    except (OSError, RuntimeError) as exc:
        if smoke_test:
            print(f'Smoke test failed: {exc}', file=sys.stderr)
            return 1
        QMessageBox.critical(None, 'Cannot read queue', str(exc))
        return 1
    apply_theme(app)
    window = MainWindow(store)
    window.quit_requested.connect(app.quit)
    window.shutdown_requested.connect(start_shutdown_watchdog)
    window.captures.log.connect(logging.info)
    window.queue.log.connect(logging.info)
    window.show()
    if smoke_test:
        QTimer.singleShot(500, lambda: app.exit(smoke_exit_code))
    elif not all(available(name) for name in ('dvgrab', 'ffmpeg', 'ffprobe')):
        QTimer.singleShot(300, window.setup)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
