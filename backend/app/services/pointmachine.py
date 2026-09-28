"""转辙机业务规则：筛选、排序、分页、状态流转与字段校验都收在这里。

排序口径只有这一份，列表分页与详情定位都走 _query_rows / _sorted_rows，
避免出现「列表里一个顺序、详情里另一个顺序」两套结论。
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

# 允许排序的列；数值列先解析成数字再比大小，其余列按文本比较。
SORTABLE_FIELDS = ["转辙机编号", "动作电流", "摩擦电流"]
NUMERIC_FIELDS = {"动作电流", "摩擦电流"}
SORT_DIRECTIONS = ("asc", "desc")

_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _to_number(value: Any) -> float | None:
    """把 '2.3A'、'1.8'、' 2.0 安 ' 这类值解析成数字；解析不出来返回 None。

    None 表示「这条没有可比的数值」，排序时统一沉到最后，而不是按 0 处理
    （按 0 会把没填的排到最前，等于把缺失当成了极小值）。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _NUMBER_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _sort_key(sort_by: str, sort_dir: str):
    """生成排序键。

    - 数值列：按解析出的数值比较，空值/无法解析的值沉底；
    - 文本列：按字符串比较，空串沉底；
    - 最后一律用记录 id 做兜底 tie-break，保证编号重复或电流相同时顺序仍然稳定，
      分页时不会出现两条相同排序键的记录来回串、被漏掉或重复出现。
    """
    is_numeric = sort_by in NUMERIC_FIELDS
    reverse = sort_dir == "desc"

    def key(row: dict[str, Any]) -> tuple:
        row_id = int(row.get("id", 0))
        if is_numeric:
            number = _to_number(row.get(sort_by))
            if number is None:
                # 缺失值永远排在有效值之后（升序降序都沉底）；
                # 同是缺失值再按 id 升序，保证顺序稳定可复现。
                return (1, 0, row_id)
            value: Any = -number if reverse else number
            return (0, value, row_id)
        text = str(row.get(sort_by) or "").strip()
        if not text:
            return (1, "", row_id)
        return (0, _ReversedText(text) if reverse else text, row_id)

    return key


class _ReversedText:
    """文本降序时的反向比较包装，缺失值沉底的规则仍由排序键的第一段控制。"""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text

    def __lt__(self, other: "_ReversedText") -> bool:
        return self.text > other.text

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ReversedText) and self.text == other.text


class PointmachineService:
    def _query_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """按筛选条件取记录。注意：不按编号去重、不合并任何记录。

        编号重复是数据问题，台账必须原样展示出来；编号缺失（空值）的记录
        也照常保留，只在按编号检索时因为匹配不上而不出现。
        """
        rows = list(store.rows(MODULE))
        if keyword:
            needle = keyword.strip()
            rows = [
                row for row in rows
                if needle in str(row.get("转辙机编号") or "")
            ]
        if status:
            # 同时兼容内部流转状态 status 与展示用的「转辙机状态」列，
            # 过滤只做「筛出匹配项」，绝不能因为某列为空而把整条记录删掉。
            rows = [
                row for row in rows
                if row.get("status") == status or str(row.get("转辙机状态") or "").strip() == status
            ]
        return rows

    def _sorted_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> list[dict[str, Any]]:
        """唯一的排序入口：未指定排序列时按记录 id 升序（登记先后）。"""
        if not sort_by:
            return sorted(rows, key=lambda row: int(row.get("id", 0)))
        return sorted(rows, key=_sort_key(sort_by, sort_dir))

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        """先筛选、再排序、最后切片——顺序不能反，否则分页会漏数据。"""
        rows = self._query_rows(keyword=keyword, status=status)
        rows = self._sorted_rows(rows, sort_by=sort_by, sort_dir=sort_dir)
        total = len(rows)
        page = max(page, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def locate_entry(
        self,
        entry_id: int,
        *,
        keyword: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> dict[str, Any] | None:
        """在与列表完全相同的筛选 + 排序结果里定位一条记录。

        返回记录本体、它在当前排序下的位置（从 1 开始）、总数以及上一条/下一条
        的记录 id。详情页据此显示「第 N / M 条」并做上一条/下一条翻页，
        与列表页看到的顺序严格一致。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        rows = self._query_rows(keyword=keyword, status=status)
        rows = self._sorted_rows(rows, sort_by=sort_by, sort_dir=sort_dir)
        ids = [int(row.get("id", 0)) for row in rows]
        if entry_id not in ids:
            # 记录存在，但不属于当前筛选结果：仍返回本体，不提供定位信息，
            # 由上层决定如何提示，而不是静默报 404。
            return {"entry": entry, "position": None, "total": len(rows),
                    "prev_id": None, "next_id": None}
        position = ids.index(entry_id)
        return {
            "entry": entry,
            "position": position + 1,
            "total": len(rows),
            "prev_id": ids[position - 1] if position > 0 else None,
            "next_id": ids[position + 1] if position + 1 < len(ids) else None,
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

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
