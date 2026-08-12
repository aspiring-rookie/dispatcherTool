"""程序入口：QApplication、托盘、数据备份、关闭拦截。"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from core_logic import ShiftResolver
from database import DatabaseManager
from ui_main import MainWindow


APP_NAME = "DispatcherTool"


def resource_path(*parts: str) -> Path:
    """获取打包资源路径，兼容 PyInstaller 解包目录。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return Path(base).joinpath(*parts)


def icon_path() -> Path:
    return resource_path("resources", "1.png")


def app_data_dir() -> Path:
    """跨平台的用户数据目录。"""
    home = Path.home()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(base) / APP_NAME


def db_path() -> Path:
    return app_data_dir() / "dispatcher.db"


def backup_db(db_file: Path) -> Optional[Path]:
    if not db_file.exists():
        return None
    backup_dir = app_data_dir() / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = backup_dir / f"dispatcher_{ts}.db"
    shutil.copy2(db_file, dst)
    shutil.copy2(db_file, backup_dir / "dispatcher_latest.db")
    files = sorted(backup_dir.glob("dispatcher_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[10:]:
        try:
            old.unlink()
        except OSError:
            pass
    return dst


def load_app_icon() -> QIcon:
    p = icon_path()
    if p.exists():
        return QIcon(str(p))
    # 兜底：纯色位图
    pix = QPixmap(64, 64)
    pix.fill(Qt.darkCyan)
    return QIcon(pix)


def make_tray_icon(app: QApplication, window: MainWindow, icon: QIcon) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("调度员任务清单")

    menu = QMenu()
    act_show = QAction("显示主界面", menu)
    act_quit = QAction("退出", menu)

    def on_show():
        window.show()
        window.raise_()
        window.activateWindow()

    def on_quit():
        window._quitting = True
        tray.hide()
        app.quit()

    act_show.triggered.connect(on_show)
    act_quit.triggered.connect(on_quit)
    menu.addAction(act_show)
    menu.addSeparator()
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show() if reason == QSystemTrayIcon.DoubleClick else None
    )
    return tray


def install_close_intercept(window: MainWindow, tray: QSystemTrayIcon) -> None:
    """重写主窗口的关闭事件：最小化到托盘而非退出。"""

    def on_close(event):
        if getattr(window, "_quitting", False):
            event.accept()
            return
        event.ignore()
        window.hide()
        tray.showMessage(
            "调度员任务清单",
            "已最小化到托盘，右键托盘图标可退出。",
            QSystemTrayIcon.Information,
            2000,
        )

    window.closeEvent = on_close


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    icon = load_app_icon()
    app.setWindowIcon(icon)

    db = DatabaseManager(str(db_path()))
    resolver = ShiftResolver(db)

    window = MainWindow(db, resolver, icon=icon)
    window._quitting = False

    tray = make_tray_icon(app, window, icon)
    install_close_intercept(window, tray)
    tray.show()

    window.show()

    exit_code = app.exec()

    try:
        db.close()
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] db.close failed: {e}", file=sys.stderr)
    try:
        backup_db(db_path())
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] backup failed: {e}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
