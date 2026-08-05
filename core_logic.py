"""班次判定、跨天日期归属、每日任务自动生成。"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, Tuple, Optional, List

from database import DatabaseManager


# 班次 ID 常量，对应 Shifts 表主键
SHIFT_MORNING = 1
SHIFT_AFTERNOON = 2
SHIFT_NIGHT = 3
SHIFT_GENERAL = 0  # 通用模板

SHIFT_NAMES = {
    SHIFT_MORNING: "早班",
    SHIFT_AFTERNOON: "中班",
    SHIFT_NIGHT: "夜班",
    SHIFT_GENERAL: "通用",
}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _parse_hhmm(text: str) -> Tuple[int, int]:
    """将 'HH:MM' 解析为 (hour, minute)。"""
    h, m = text.split(":")
    return int(h), int(m)


def _crosses_midnight(start: str, end: str) -> bool:
    """判断班次是否跨过午夜（结束时间小于等于开始时间）。"""
    sh, sm = _parse_hhmm(start)
    eh, em = _parse_hhmm(end)
    return (eh, em) <= (sh, sm)


class ShiftResolver:
    """根据 Shifts 表中的时间配置，动态判定当前班次和业务日期。"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def _load_shifts(self) -> Dict[int, Dict[str, Any]]:
        rows = self.db.get_shifts()
        return {r["id"]: r for r in rows}

    @staticmethod
    def format_shift_label(shift: Dict[str, Any]) -> str:
        return f"{shift['name']} {shift['start_time']}-{shift['end_time']}"

    def resolve(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """返回当前业务日期、班次 ID、班次行。

        规则：
            早班 / 中班：业务日期 = 今天
            夜班（19:00-23:59）：业务日期 = 今天
            夜班（00:00-结束）：业务日期 = 昨天
        """
        now = now or datetime.now()
        shifts = self._load_shifts()

        morning = shifts.get(SHIFT_MORNING)
        afternoon = shifts.get(SHIFT_AFTERNOON)
        night = shifts.get(SHIFT_NIGHT)
        if not (morning and afternoon and night):
            raise RuntimeError("Shifts 表配置不完整，无法判定班次")

        cur_minutes = now.hour * 60 + now.minute

        m_start = _to_minutes(morning["start_time"])
        m_end = _to_minutes(morning["end_time"])
        a_start = _to_minutes(afternoon["start_time"])
        a_end = _to_minutes(afternoon["end_time"])
        n_start = _to_minutes(night["start_time"])
        n_end = _to_minutes(night["end_time"])

        # 早班
        if m_start <= cur_minutes < m_end:
            return {"date": now.date(), "shift_id": SHIFT_MORNING, "shift": morning}
        # 中班
        if a_start <= cur_minutes < a_end:
            return {"date": now.date(), "shift_id": SHIFT_AFTERNOON, "shift": afternoon}
        # 夜班（晚上段，>= 19:00 到 23:59）：业务日期=今天
        if cur_minutes >= n_start:
            return {"date": now.date(), "shift_id": SHIFT_NIGHT, "shift": night}
        # 夜班（凌晨段，< n_end，且 n_end 通常为次日早晨）：业务日期=昨天
        if cur_minutes < n_end:
            return {
                "date": now.date() - timedelta(days=1),
                "shift_id": SHIFT_NIGHT,
                "shift": night,
            }
        # 间隙时间（理论上 m_end..a_start 等空隙）：归到上一班次
        if m_end <= cur_minutes < a_start:
            return {"date": now.date(), "shift_id": SHIFT_MORNING, "shift": morning}
        if a_end <= cur_minutes < n_start:
            return {"date": now.date(), "shift_id": SHIFT_AFTERNOON, "shift": afternoon}
        # 兜底
        return {"date": now.date(), "shift_id": SHIFT_NIGHT, "shift": night}


def _to_minutes(hhmm: str) -> int:
    h, m = _parse_hhmm(hhmm)
    return h * 60 + m


def is_record_overdue(record: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """判断任务是否超时（有 due_time 且未完成且当前时间已过 due_time）。"""
    if record.get("is_completed"):
        return False
    due = record.get("due_time")
    if not due:
        return False
    now = now or datetime.now()
    try:
        due_h, due_m = _parse_hhmm(due)
    except ValueError:
        return False
    return (now.hour, now.minute) >= (due_h, due_m)


def ensure_daily_generated(
    db: DatabaseManager,
    record_date: date,
    shift_id: int,
) -> int:
    """若指定业务日期+班次的模板任务尚未生成，则批量生成。返回插入条数。"""
    return db.generate_daily_from_templates(record_date.isoformat(), shift_id)


def weekday_cn(d: date) -> str:
    return WEEKDAY_CN[d.weekday()]


def shift_label(db: DatabaseManager, shift_id: int) -> str:
    """根据 shift_id 拼出 '夜班 19:00-07:30' 样式的标签。"""
    shift = db.get_shift(shift_id)
    if not shift:
        return SHIFT_NAMES.get(shift_id, "未知")
    return ShiftResolver.format_shift_label(shift)


def build_handover_report(
    db: DatabaseManager,
    record_date: date,
    shift_id: int,
    resolver_now: Optional[datetime] = None,
) -> str:
    """生成交接班报告文本：未完成任务列表 + 已完成计数。"""
    rows = db.list_records(record_date.isoformat(), shift_id)
    pending = [r for r in rows if not r["is_completed"]]
    done = [r for r in rows if r["is_completed"]]

    now = resolver_now or datetime.now()
    shift = db.get_shift(shift_id)
    shift_name = shift["name"] if shift else SHIFT_NAMES.get(shift_id, "")
    head = (
        f"【交接班报告】{record_date.isoformat()} {weekday_cn(record_date)} {shift_name}\n"
        f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}\n"
        f"未完成 {len(pending)} 项，已完成 {len(done)} 项\n"
    )

    lines: List[str] = [head]
    if pending:
        lines.append("—— 待交接事项 ——")
        for i, r in enumerate(pending, 1):
            tag = "⚠️" if is_record_overdue(r, now) else "·"
            due = f" (due {r['due_time']})" if r.get("due_time") else ""
            tmp = " [临时]" if r.get("is_temp") else ""
            lines.append(f"{tag} {i}. {r['name']}{due}{tmp}")
    else:
        lines.append("—— 全部任务已完成 ——")
    return "\n".join(lines)
