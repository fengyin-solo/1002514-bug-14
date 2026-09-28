"""转辙机接口：维护转辙机，覆盖登记异常、安排润滑、办理更换等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.pointmachine import (
    SORTABLE_FIELDS,
    SORT_DIRECTIONS,
    STATUS_ORDER,
    PointmachineService,
)

router = APIRouter(prefix="/api/pointmachine", tags=["转辙机"])

service = PointmachineService()

LIST_FIELDS = ["转辙机编号", "所属道岔", "转辙机型号", "动作电流", "摩擦电流", "表示缺口", "润滑状态", "转辙机状态"]
STATUSES = STATUS_ORDER


def _validate_page(page: int, size: int) -> None:
    """分页参数统一校验，错误信息里带上收到的值，方便前端与调用方定位。"""
    if page < 1:
        raise HTTPException(status_code=400, detail=f"页码必须从 1 开始，当前收到 page={page}")
    if size < 1:
        raise HTTPException(status_code=400, detail=f"每页条数不能小于 1，当前收到 size={size}")
    if size > 200:
        raise HTTPException(status_code=400, detail=f"每页最多 200 条，请缩小分页范围，当前收到 size={size}")


def _validate_sort(sort_by: str | None, sort_dir: str) -> None:
    if sort_by is not None and sort_by not in SORTABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持按「{sort_by}」排序，可选列：{'、'.join(SORTABLE_FIELDS)}",
        )
    if sort_dir not in SORT_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"排序方向只能是 {' 或 '.join(SORT_DIRECTIONS)}，当前收到 sort_dir={sort_dir}",
        )


# 注意：/export 必须写在 /{entry_id} 之前，否则 "export" 会被当成 entry_id 匹配。
@router.get("/export")
def export_entries(
    sort_by: str | None = None,
    sort_dir: str = "asc",
    status: str | None = None,
) -> dict[str, Any]:
    """导出转辙机清单：按当前筛选与排序口径导出全量数据，编号重复/缺失的记录都保留。"""
    _validate_sort(sort_by, sort_dir)
    items, total = service.list_entries(
        page=1, size=10000, sort_by=sort_by, sort_dir=sort_dir, status=status
    )
    return {"module": "pointmachine", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按转辙机编号检索"),
    status: str | None = Query(default=None, description="正常、电流偏高、润滑不足、已更换"),
    sort_by: str | None = Query(default=None, description="排序列：转辙机编号、动作电流、摩擦电流"),
    sort_dir: str = Query(default="asc", description="排序方向：asc / desc"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按转辙机编号与状态过滤、按选定列排序后分页；没有数据时返回空页，不报错。"""
    _validate_page(page, size)
    _validate_sort(sort_by, sort_dir)
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"状态「{status}」不在允许范围内：{'、'.join(STATUSES)}",
        )
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}")
def get_entry(
    entry_id: int,
    keyword: str | None = Query(default=None, description="列表当前的编号检索条件"),
    status: str | None = Query(default=None, description="列表当前的状态过滤条件"),
    sort_by: str | None = Query(default=None, description="列表当前的排序列"),
    sort_dir: str = Query(default="asc", description="列表当前的排序方向"),
) -> dict[str, Any]:
    """读取单条转辙机明细，并给出它在当前排序下的位置与上一条/下一条。

    定位逻辑与列表接口共用同一份筛选 + 排序口径，保证两处顺序一致。
    """
    _validate_sort(sort_by, sort_dir)
    located = service.locate_entry(
        entry_id,
        keyword=keyword,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    if located is None:
        raise HTTPException(status_code=404, detail=f"转辙机 {entry_id} 不存在或已归档")
    return located


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条转辙机，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="转辙机已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条转辙机执行登记异常、安排润滑、办理更换；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
