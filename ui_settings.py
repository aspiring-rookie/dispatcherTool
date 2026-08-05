"""设置对话框：班次时间修改 + 任务模板管理。"""

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from database import DatabaseManager
from core_logic import SHIFT_AFTERNOON, SHIFT_MORNING, SHIFT_NAMES, SHIFT_NIGHT, SHIFT_GENERAL


SHIFT_LABELS = [
    ("通用", SHIFT_GENERAL),
    ("早班", SHIFT_MORNING),
    ("中班", SHIFT_AFTERNOON),
    ("夜班", SHIFT_NIGHT),
]


class SettingsDialog(QDialog):
    """设置对话框，包含“班次时间”和“任务模板”两个 Tab。"""

    def __init__(self, db: DatabaseManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("设置")
        self.resize(720, 480)
        self.setModal(True)

        self._shift_edits: dict[int, tuple[QLineEdit, QTimeEdit, QTimeEdit]] = {}

        self._build_ui()
        self._load_shifts()
        self._load_templates()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import QTabWidget

        outer = QVBoxLayout(self)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_shift_tab(), "班次时间")
        tabs.addTab(self._build_template_tab(), "任务模板")
        outer.addWidget(tabs)

        bb = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        outer.addWidget(bb)

    def _build_shift_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignLeft)

        for sid, label_default in [
            (SHIFT_MORNING, "早班"),
            (SHIFT_AFTERNOON, "中班"),
            (SHIFT_NIGHT, "夜班"),
        ]:
            name_edit = QLineEdit(label_default)
            start_edit = QTimeEdit()
            start_edit.setDisplayFormat("HH:mm")
            start_edit.setTime(QTime(0, 0))
            end_edit = QTimeEdit()
            end_edit.setDisplayFormat("HH:mm")
            end_edit.setTime(QTime(0, 0))

            row = QHBoxLayout()
            row.addWidget(name_edit, 2)
            row.addWidget(start_edit, 1)
            row.addWidget(end_edit, 1)

            holder = QWidget()
            holder.setLayout(row)
            form.addRow(f"班次 ID={sid}", holder)
            self._shift_edits[sid] = (name_edit, start_edit, end_edit)

        save_btn = QPushButton("保存班次时间")
        save_btn.clicked.connect(self._save_shifts)
        form.addRow(save_btn)

        tip = QLabel("提示：夜班结束时间通常落在次日早晨（如 07:30）。")
        tip.setStyleSheet("color: #888;")
        form.addRow(tip)
        return page

    def _build_template_tab(self) -> QWidget:
        page = QWidget(self)
        h = QHBoxLayout(page)

        # 左：模板列表
        left = QVBoxLayout()
        left.addWidget(QLabel("任务模板列表"))
        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        left.addWidget(self.template_list, 1)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("新增模板")
        new_btn.clicked.connect(self._new_template)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._delete_template)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)

        # 右：详情编辑
        right = QFormLayout()
        self.tpl_name = QLineEdit()
        self.tpl_name.setPlaceholderText("任务名称")
        self.tpl_shift = QComboBox()
        for label, sid in SHIFT_LABELS:
            self.tpl_shift.addItem(label, sid)
        self.tpl_active = QPushButton("启用")
        self.tpl_active.setCheckable(True)
        self.tpl_active.setChecked(True)
        self.tpl_active.toggled.connect(
            lambda checked: self.tpl_active.setText("启用" if checked else "停用")
        )
        self.tpl_due = QLineEdit()
        self.tpl_due.setPlaceholderText("HH:MM（可空）")
        self.tpl_due.setInputMask("99:99;_")

        save_tpl_btn = QPushButton("保存当前模板")
        save_tpl_btn.clicked.connect(self._save_current_template)

        right.addRow("名称", self.tpl_name)
        right.addRow("班次", self.tpl_shift)
        right.addRow("启用", self.tpl_active)
        right.addRow("截止时间", self.tpl_due)
        right.addRow(save_tpl_btn)

        h.addLayout(left, 1)
        h.addLayout(right, 1)
        return page

    # ---------- 班次时间 ----------

    def _load_shifts(self) -> None:
        rows = {r["id"]: r for r in self.db.get_shifts()}
        for sid, (name_edit, start_edit, end_edit) in self._shift_edits.items():
            r = rows.get(sid)
            if not r:
                continue
            name_edit.setText(r["name"])
            start_edit.setTime(_qtime_from_hhmm(r["start_time"]))
            end_edit.setTime(_qtime_from_hhmm(r["end_time"]))

    def _save_shifts(self) -> None:
        try:
            for sid, (name_edit, start_edit, end_edit) in self._shift_edits.items():
                name = name_edit.text().strip()
                if not name:
                    raise ValueError(f"班次 ID={sid} 的名称不能为空")
                start = _hhmm_from_qtime(start_edit.time())
                end = _hhmm_from_qtime(end_edit.time())
                self.db.update_shift(sid, name, start, end)
            QMessageBox.information(self, "已保存", "班次时间已更新。")
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))

    # ---------- 任务模板 ----------

    def _load_templates(self) -> None:
        self.template_list.clear()
        for r in self.db.list_templates():
            label = f"[{SHIFT_NAMES.get(r['shift_type'], '?')}] {r['name']}"
            if not r["is_active"]:
                label += "（停用）"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, r["id"])
            self.template_list.addItem(item)

    def _on_template_selected(self, cur: QListWidgetItem, _prev: QListWidgetItem) -> None:
        if cur is None:
            return
        tid = cur.data(Qt.UserRole)
        for r in self.db.list_templates():
            if r["id"] == tid:
                self.tpl_name.setText(r["name"])
                idx = self.tpl_shift.findData(r["shift_type"])
                if idx >= 0:
                    self.tpl_shift.setCurrentIndex(idx)
                self.tpl_active.setChecked(bool(r["is_active"]))
                self.tpl_due.setText(r["due_time"] or "")
                return

    def _new_template(self) -> None:
        new_id = self.db.create_template("新任务", SHIFT_GENERAL, True)
        self._load_templates()
        for i in range(self.template_list.count()):
            if self.template_list.item(i).data(Qt.UserRole) == new_id:
                self.template_list.setCurrentRow(i)
                break

    def _delete_template(self) -> None:
        cur = self.template_list.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选中一个模板。")
            return
        tid = cur.data(Qt.UserRole)
        if (
            QMessageBox.question(
                self,
                "确认删除",
                "确定删除该模板？历史已生成记录不会被删除。",
            )
            != QMessageBox.Yes
        ):
            return
        self.db.delete_template(tid)
        self._load_templates()

    def _save_current_template(self) -> None:
        cur = self.template_list.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选中一个模板。")
            return
        tid = cur.data(Qt.UserRole)
        name = self.tpl_name.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "任务名称不能为空。")
            return
        shift_type = self.tpl_shift.currentData()
        due = self.tpl_due.text().strip()
        if due and due.count(":") != 1:
            QMessageBox.warning(self, "输入错误", "截止时间格式应为 HH:MM。")
            return
        self.db.update_template(
            tid,
            name,
            shift_type,
            self.tpl_active.isChecked(),
            due or None,
        )
        self._load_templates()
        QMessageBox.information(self, "已保存", "模板已保存。")


def _qtime_from_hhmm(text: str) -> QTime:
    h, m = text.split(":")
    return QTime(int(h), int(m))


def _hhmm_from_qtime(t: QTime) -> str:
    return f"{t.hour():02d}:{t.minute():02d}"
