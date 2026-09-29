"""转辙机排序/分页/详情一致性回归测试。

不依赖 pytest，直接 ``python3 tests/test_pointmachine.py`` 即可运行；
失败时以非 0 退出码结束，方便接入 CI。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许直接从 backend 目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pointmachine import order_rows, to_number  # noqa: E402
from app.store import store  # noqa: E402
from app.services.pointmachine import MODULE, PointmachineService  # noqa: E402


def test_to_number() -> None:
    assert to_number("2.3A") == 2.3
    assert to_number(1.5) == 1.5
    assert to_number("未测") is None
    assert to_number("") is None
    assert to_number(None) is None


def _ids(rows: list[dict]) -> list[int]:
    return [int(r["id"]) for r in rows]


def test_numeric_sort_and_pagination_stable() -> None:
    service = PointmachineService()
    first, total = service.list_entries(sort_key="action", descending=False, page=1, size=7)
    second, total2 = service.list_entries(sort_key="action", descending=False, page=2, size=7)
    assert total == total2 == len(store.rows(MODULE))
    joined = _ids(first) + _ids(second)
    all_rows, _ = service.list_entries(sort_key="action", descending=False, page=1, size=10000)
    assert joined == _ids(all_rows), "翻页拼接必须与全量顺序一致，不丢不重"
    assert len(joined) == len(set(joined)) == total

    # 数值单调性：解析出的电流值必须真的按数值排
    values = [to_number(r.get("动作电流")) for r in all_rows]
    present = [v for v in values if v is not None]
    assert present == sorted(present)
    # 无法解析（未测）的记录排到最后而不是丢弃
    assert values[-1] is None and all(v is not None for v in values[:-1])


def test_stable_on_equal_values() -> None:
    rows = [
        {"id": 3, "动作电流": "2.0A"},
        {"id": 1, "动作电流": "2.0A"},
        {"id": 2, "动作电流": "2.0A"},
    ]
    once = order_rows(rows, "action", False)
    twice = order_rows([dict(r) for r in rows], "action", False)
    assert _ids(once) == _ids(twice) == [1, 2, 3], "同值并列时按唯一 id 兜底，保证翻页不乱序"


def test_duplicate_and_missing_codes_kept() -> None:
    """业务编号允许重复/缺失，排序与分页不得以编号为键合并记录。"""
    service = PointmachineService()
    rows, total = service.list_entries(sort_key="code", descending=False, page=1, size=10000)
    ids = _ids(rows)
    assert len(ids) == total == len(set(ids))
    by_code: dict[str, list[int]] = {}
    missing_code = []
    for row in rows:
        code = row.get("转辙机编号")
        if code is None:
            missing_code.append(int(row["id"]))
        else:
            by_code.setdefault(str(code), []).append(int(row["id"]))
    assert len(by_code.get("POIN-0002", [])) == 2, "重复编号不能被合并"
    assert missing_code, "编号缺失的记录不能被丢弃"


def test_detail_rank_matches_list() -> None:
    """列表与详情必须共用一套顺序：逐条核对 rank/prev/next。"""
    service = PointmachineService()
    for sort_key in ("code", "action", "friction"):
        for descending in (False, True):
            rows, total = service.list_entries(
                sort_key=sort_key, descending=descending, page=1, size=10000
            )
            ids = _ids(rows)
            for position, entry_id in enumerate(ids, start=1):
                payload, message = service.get_entry_detail(
                    entry_id, sort_key=sort_key, descending=descending
                )
                assert payload is not None, message
                assert payload["rank"] == position
                assert payload["total"] == total
                assert payload["prev_id"] == (ids[position - 2] if position > 1 else None)
                assert payload["next_id"] == (ids[position] if position < total else None)
                assert payload["in_scope"] is True


def test_detail_for_record_excluded_by_filter() -> None:
    service = PointmachineService()
    # id=8 型号为 S700K，按 ZD6 筛选时不在结果内，仍需给出全量定位并如实标注
    payload, message = service.get_entry_detail(8, model="ZD6", sort_key="action")
    assert payload is not None, message
    assert payload["in_scope"] is False
    full, _ = service.list_entries(sort_key="action", page=1, size=10000)
    assert payload["rank"] == _ids(full).index(8) + 1


def main() -> int:
    tests = [
        test_to_number,
        test_numeric_sort_and_pagination_stable,
        test_stable_on_equal_values,
        test_duplicate_and_missing_codes_kept,
        test_detail_rank_matches_list,
        test_detail_for_record_excluded_by_filter,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} 个回归用例全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
