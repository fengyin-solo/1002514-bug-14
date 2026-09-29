"""转辙机业务规则：筛选、排序、分页口径与状态流转都收在这里。

排序只有 :func:`order_rows` 一个实现，台账列表与记录详情都通过它确定顺序，
避免两处各排各的、给出两套位置结论。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "pointmachine"
REQUIRED_FIELDS = ["转辙机编号", "所属道岔", "转辙机型号"]
STATUS_ORDER = ["正常", "电流偏高", "润滑不足", "已更换"]
ACTION_RULES = {"登记异常": "电流偏高", "安排润滑": "润滑不足", "办理更换": "已更换"}
NEGATIVE_ACTIONS = []

# 可排序字段：查询参数键 -> (台账列名, 是否按数值比较)
SORT_COLUMNS: dict[str, tuple[str, bool]] = {
    "code": ("转辙机编号", False),
    "action": ("动作电流", True),
    "friction": ("摩擦电流", True),
}
DEFAULT_SORT = "code"

_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def to_number(value: Any) -> float | None:
    """把「1.8」「2.3A」之类的取值解析成数值；解析不出（空值、未测等）返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    return float(match.group()) if match else None


def _sort_value(row: dict[str, Any], column: str, numeric: bool) -> Any:
    raw = row.get(column)
    if raw is None or str(raw).strip() == "":
        return None
    if numeric:
        return to_number(raw)
    return str(raw).strip()


def order_rows(
    rows: list[dict[str, Any]],
    sort_key: str = DEFAULT_SORT,
    descending: bool = False,
) -> list[dict[str, Any]]:
    """按选定字段稳定排序，返回新列表（不改动原始数据顺序）。

    - 动作电流、摩擦电流按数值大小比较，不做字符串比较；
    - 空值或无法解析成数值的记录排到最后，绝不丢弃，顺序由唯一 id 兜底；
    - id 是主键，业务编号允许重复或缺失，排序里不做任何合并去重。
    """
    column, numeric = SORT_COLUMNS[sort_key]

    # 先按唯一 id 排一遍，保证同值并列时顺序确定，翻页不会跳动。
    base = sorted(rows, key=lambda row: int(row.get("id", 0)))

    def value(row: dict[str, Any]) -> Any:
        return _sort_value(row, column, numeric)

    present = [row for row in base if value(row) is not None]
    missing = [row for row in base if value(row) is None]
    present.sort(key=value, reverse=descending)
    return present + missing


class PointmachineService:
    def _filter(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None,
        turnout: str | None,
        model: str | None,
        status: str | None,
    ) -> list[dict[str, Any]]:
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("转辙机编号") or "")]
        if turnout:
            rows = [row for row in rows if turnout in str(row.get("所属道岔") or "")]
        if model:
            rows = [row for row in rows if model in str(row.get("转辙机型号") or "")]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        turnout: str | None = None,
        model: str | None = None,
        status: str | None = None,
        sort_key: str = DEFAULT_SORT,
        descending: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """筛选 -> 统一排序 -> 按页切片；缺字段的记录照样参与分页，不会被剔除。"""
        rows = self._filter(
            store.rows(MODULE),
            keyword=keyword,
            turnout=turnout,
            model=model,
            status=status,
        )
        ordered = order_rows(rows, sort_key, descending)
        total = len(ordered)
        start = max(page - 1, 0) * size
        return ordered[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_entry_detail(
        self,
        entry_id: int,
        *,
        keyword: str | None = None,
        turnout: str | None = None,
        model: str | None = None,
        status: str | None = None,
        sort_key: str = DEFAULT_SORT,
        descending: bool = False,
    ) -> tuple[dict[str, Any] | None, str]:
        """读取记录详情，并按与列表完全相同的口径计算它在台账中的位置。

        返回的 rank/total/prev_id/next_id 都基于同一个 :func:`order_rows` 结果，
        列表与详情不可能排出两套顺序。若该记录不在当前筛选结果内，则保持相同排序、
        去掉筛选后再定位，并在 in_scope 上如实标注。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"转辙机 {entry_id} 不存在或已归档"

        filtered = self._filter(
            store.rows(MODULE),
            keyword=keyword,
            turnout=turnout,
            model=model,
            status=status,
        )
        ordered = order_rows(filtered, sort_key, descending)
        in_scope = True
        index = next(
            (i for i, row in enumerate(ordered) if int(row.get("id", 0)) == entry_id),
            -1,
        )
        if index < 0:
            # 记录被筛选条件排除时，不允许给不出位置：用相同排序、全量数据重新定位。
            in_scope = False
            ordered = order_rows(store.rows(MODULE), sort_key, descending)
            index = next(
                i for i, row in enumerate(ordered) if int(row.get("id", 0)) == entry_id
            )

        label, numeric = SORT_COLUMNS[sort_key]
        prev_id = ordered[index - 1].get("id") if index > 0 else None
        next_id = ordered[index + 1].get("id") if index + 1 < len(ordered) else None
        payload = {
            "entry": entry,
            "sort": sort_key,
            "sort_label": label,
            "numeric": numeric,
            "order": "desc" if descending else "asc",
            "in_scope": in_scope,
            "rank": index + 1,
            "total": len(ordered),
            "prev_id": prev_id,
            "next_id": next_id,
        }
        return payload, ""

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"转辙机 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于转辙机可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"转辙机已{action}"
