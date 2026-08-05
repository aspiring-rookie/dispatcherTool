"""主窗口：迷你侧边栏样式 - 状态栏 + 班次 Tab + 任务列表 + 底部操作栏。"""

import sys
from datetime import date, datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core_logic import (
    SHIFT_AFTERNOON,
    SHIFT_MORNING,
    SHIFT_NAMES,
    SHIFT_NIGHT,
    ShiftResolver,
    build_handover_report,
    ensure_daily_generated,
    is_record_overdue,
    shift_label,
    weekday_cn,
)
from database import DatabaseManager
from ui_settings import SettingsDialog


def _default_font_family() -> str:
    if sys.platform == "darwin":
        return '"PingFang SC", "Helvetica Neue"'
    if sys.platform.startswith("win"):
        return '"Microsoft YaHei", "Segoe UI"'
    return '"Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"'


APP_QSS = """
* {
    font-family: __FONT_FAMILY__;
    font-size: 12px;
    color: #2c3e50;
}
QMainWindow, QWidget#central {
    background: #f7f8fa;
}
QLabel {
    color: #2c3e50;
}
QFrame#topBar {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 6px;
}
QLabel#labelDate {
    font-size: 12px;
    font-weight: 600;
    color: #2c3e50;
}
QLabel#labelShift {
    font-size: 11px;
    color: #0a8;
    font-weight: 600;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 4px;
    padding: 3px 8px;
    color: #2c3e50;
}
QPushButton:hover { background: #eef2f7; }
QPushButton:pressed { background: #dde3ec; }
QPushButton:checked {
    background: #0a8;
    color: white;
    border-color: #0a8;
}
QTabWidget::pane {
    border: 1px solid #e3e7ee;
    border-radius: 6px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #eef2f7;
    padding: 4px 10px;
    margin-right: 2px;
    border: 1px solid #d8dee8;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #5a6878;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #0a8;
    font-weight: 600;
    border-color: #e3e7ee;
}
QTreeWidget {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 6px;
    padding: 4px;
}
QTreeWidget::item {
    padding: 2px 0;
    min-height: 18px;
}
QHeaderView::section {
    background: #f2f4f8;
    padding: 3px;
    border: none;
    border-bottom: 1px solid #e3e7ee;
    color: #5a6878;
    font-weight: 600;
}
QLineEdit {
    border: 1px solid #d8dee8;
    border-radius: 4px;
    padding: 3px 6px;
    background: #ffffff;
    selection-background-color: #0a8;
    selection-color: #ffffff;
}
QLineEdit:focus {
    border-color: #0a8;
}
QStatusBar {
    background: transparent;
    color: #6a7686;
}
QStatusBar::item { border: none; }
"""


class MainWindow(QMainWindow):
    def __init__(self, db: DatabaseManager, resolver: ShiftResolver, icon: Optional[QIcon] = None):
        super().__init__()
        self.db = db
        self.resolver = resolver
        self._icon = icon
        if icon is not None:
            self.setWindowIcon(icon)
        self.setWindowTitle("任务清单")
        # 迷你侧边栏尺寸
        self.resize(320, 560)
        self.setMinimumSize(280, 420)

        self._current_view: dict = self.resolver.resolve()
        self._build_ui()
        self.setStyleSheet(APP_QSS.replace("__FONT_FAMILY__", _default_font_family()))

        # 每分钟刷新顶部状态栏 + 任务列表（超时高亮）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60_000)

        self._refresh_status()
        self._ensure_today_generated()
        self._refresh_active_tab()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_tabs(), 1)
        root.addLayout(self._build_bottom_bar())

        self.setCentralWidget(central)

    def _build_top_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("topBar")
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(2)

        self.label_date = QLabel("…")
        self.label_date.setObjectName("labelDate")
        self.label_shift = QLabel("…")
        self.label_shift.setObjectName("labelShift")

        # 第二行：操作按钮
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)
        self.btn_pin = QPushButton("📌 置顶")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setCursor(Qt.PointingHandCursor)
        self.btn_pin.toggled.connect(self._on_toggle_pin)
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("刷新")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._manual_refresh)
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setToolTip("设置")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)

        btn_row.addWidget(self.label_shift)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_pin)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_settings)

        v.addWidget(self.label_date)
        v.addLayout(btn_row)
        return frame

    def _build_tabs(self) -> QWidget:
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        # 每个 Tab 的元数据保存在 Python 字典里
        self._tab_meta: dict = {}

        self.tabs.addTab(self._build_task_tab(-1, dynamic=True), "当前")
        self.tabs.addTab(self._build_task_tab(SHIFT_MORNING), "早")
        self.tabs.addTab(self._build_task_tab(SHIFT_AFTERNOON), "中")
        self.tabs.addTab(self._build_task_tab(SHIFT_NIGHT), "夜")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        return self.tabs

    def _build_task_tab(self, shift_id: int, dynamic: bool = False) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        tree = QTreeWidget(page)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(True)
        tree.setIndentation(12)
        tree.setColumnCount(1)
        tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(tree, 1)

        self._tab_meta[page] = {
            "shift_id": shift_id,
            "dynamic": dynamic,
            "tree": tree,
        }
        return page

    def _build_bottom_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(4)

        self.input_temp = QLineEdit(self)
        self.input_temp.setPlaceholderText("临时任务…")
        self.input_temp.returnPressed.connect(self._on_add_temp)

        btn_add = QPushButton("➕")
        btn_add.setToolTip("添加临时任务")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._on_add_temp)

        btn_handover = QPushButton("📋")
        btn_handover.setToolTip("生成交接班报告（复制到剪贴板）")
        btn_handover.setCursor(Qt.PointingHandCursor)
        btn_handover.clicked.connect(self._on_handover)

        bar.addWidget(self.input_temp, 1)
        bar.addWidget(btn_add)
        bar.addWidget(btn_handover)
        return bar

    # ---------- 业务逻辑 ----------

    def _tick(self) -> None:
        new_view = self.resolver.resolve()
        if (
            new_view["shift_id"] != self._current_view["shift_id"]
            or new_view["date"] != self._current_view["date"]
        ):
            self._current_view = new_view
            self._ensure_today_generated()
        self._refresh_status()
        self._refresh_active_tab()

    def _manual_refresh(self) -> None:
        self._current_view = self.resolver.resolve()
        self._ensure_today_generated()
        self._refresh_status()
        self._refresh_active_tab()

    def _refresh_status(self) -> None:
        view = self._current_view
        d: date = view["date"]
        shift = view["shift"]
        self.label_date.setText(
            f"📅 {d.month}月{d.day}日 {weekday_cn(d)}"
        )
        self.label_shift.setText(
            f"🛰 {self.resolver.format_shift_label(shift)}"
        )

    def _ensure_today_generated(self) -> None:
        view = self._current_view
        try:
            inserted = ensure_daily_generated(self.db, view["date"], view["shift_id"])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "生成失败", str(e))
            return
        if inserted:
            self.statusBar().showMessage(f"已自动生成 {inserted} 条今日任务", 4000)

    def _active_shift_id(self) -> tuple[int, date]:
        page = self.tabs.currentWidget()
        meta = self._tab_meta.get(page) if page is not None else None
        if meta is None or meta["dynamic"]:
            return self._current_view["shift_id"], self._current_view["date"]
        return meta["shift_id"], self._current_view["date"]

    def _on_tab_changed(self, _idx: int) -> None:
        self._refresh_active_tab()

    def _refresh_active_tab(self) -> None:
        page = self.tabs.currentWidget()
        meta = self._tab_meta.get(page) if page is not None else None
        if meta is None:
            return
        sid, d = self._active_shift_id()
        # 切换到某班次 Tab 时，确保该班次今日任务已从模板生成（已存在则跳过）
        try:
            inserted = ensure_daily_generated(self.db, d, sid)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "生成失败", str(e))
            inserted = 0
        if inserted:
            self.statusBar().showMessage(f"已生成 {inserted} 条 {SHIFT_NAMES.get(sid, '')} 任务", 3000)
        tree: QTreeWidget = meta["tree"]
        self._load_tree(tree, d, sid)

    def _load_tree(self, tree: QTreeWidget, d: date, shift_id: int) -> None:
        tree.blockSignals(True)
        tree.clear()

        records = self.db.list_records(d.isoformat(), shift_id)
        pending = [r for r in records if not r["is_completed"]]
        done = [r for r in records if r["is_completed"]]
        now = datetime.now()

        pending_root = QTreeWidgetItem([f"📌 待办任务（{len(pending)}）"])
        f = pending_root.font(0)
        f.setBold(True)
        pending_root.setFont(0, f)
        pending_root.setForeground(0, QColor("#c0392b"))
        pending_root.setFlags(pending_root.flags() & ~Qt.ItemIsUserCheckable)
        tree.addTopLevelItem(pending_root)

        for r in pending:
            overdue = is_record_overdue(r, now)
            label = r["name"]
            if r.get("due_time"):
                label += f"  ⏰{r['due_time']}"
            if r.get("is_temp"):
                label = "🏷 " + label
            if overdue:
                label = "⚠️ " + label
            item = QTreeWidgetItem([label])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            item.setData(0, Qt.UserRole, r["id"])
            if overdue:
                item.setBackground(0, QColor("#fdecea"))
                item.setForeground(0, QColor("#a93226"))
            elif r.get("is_temp"):
                item.setForeground(0, QColor("#8e44ad"))
            pending_root.addChild(item)

        done_root = QTreeWidgetItem([f"✅ 已完成（{len(done)}）"])
        df = done_root.font(0)
        df.setBold(True)
        done_root.setFont(0, df)
        done_root.setForeground(0, QColor("#27ae60"))
        done_root.setFlags(done_root.flags() & ~Qt.ItemIsUserCheckable)
        tree.addTopLevelItem(done_root)

        for r in done:
            ts = (r.get("completed_time") or "")[-5:]  # HH:MM
            label = f"✓ {r['name']}"
            if ts:
                label += f"  · {ts}"
            item = QTreeWidgetItem([label])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setData(0, Qt.UserRole, r["id"])
            lf = item.font(0)
            lf.setStrikeOut(True)
            item.setFont(0, lf)
            item.setForeground(0, QColor("#95a5a6"))
            done_root.addChild(item)

        tree.blockSignals(False)
        # 默认展开所有任务（待办与已完成）
        tree.expandAll()

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        rid = item.data(0, Qt.UserRole)
        if rid is None:
            return
        completed = item.checkState(0) == Qt.Checked
        self.db.set_record_completed(int(rid), completed)
        self._refresh_active_tab()

    def _on_add_temp(self) -> None:
        text = self.input_temp.text().strip()
        if not text:
            return
        sid, d = self._active_shift_id()
        self.db.add_temp_task(d.isoformat(), sid, text)
        self.input_temp.clear()
        self._refresh_active_tab()
        self.statusBar().showMessage("已添加临时任务", 3000)

    def _on_handover(self) -> None:
        sid, d = self._active_shift_id()
        text = build_handover_report(self.db, d, sid)
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("交接班报告已复制到剪贴板", 5000)
        QMessageBox.information(self, "交接班报告（已复制）", text)

    def _on_toggle_pin(self, checked: bool) -> None:
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.btn_pin.setText("📌 已置顶")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.btn_pin.setText("📌 置顶")
        self.show()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.db, self)
        if dlg.exec() == dlg.Accepted:
            self._current_view = self.resolver.resolve()
            self._refresh_status()
            self._refresh_active_tab()
