"""转辙机接口：维护转辙机，覆盖登记异常、安排润滑、办理更换等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.pointmachine import (
    DEFAULT_SORT,
    SORT_COLUMNS,
    STATUS_ORDER,
    PointmachineService,
)

router = APIRouter(prefix="/api/pointmachine", tags=["转辙机"])

service = PointmachineService()

LIST_FIELDS = ["转辙机编号", "所属道岔", "转辙机型号", "动作电流", "摩擦电流", "表示缺口", "润滑状态", "转辙机状态"]
STATUSES = STATUS_ORDER


def _resolve_query(
    keyword: str | None,
    turnout: str | None,
    model: str | None,
    status: str | None,
    sort: str,
    order: str,
    page: int,
    size: int,
) -> dict[str, Any]:
    """统一解析列表/详情共用的查询参数，非法值直接给出可读反馈。"""
    if sort not in SORT_COLUMNS:
        options = "、".join(SORT_COLUMNS)
        raise HTTPException(status_code=400, detail=f"不支持的排序字段「{sort}」，可选：{options}")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="排序方向只支持 asc（升序）或 desc（降序）")
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的状态「{status}」，可选：{'、'.join(STATUSES)}",
        )
    return {
        "keyword": keyword or None,
        "turnout": turnout or None,
        "model": model or None,
        "status": status or None,
        "sort_key": sort,
        "descending": order == "desc",
        "page": page,
        "size": size,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按转辙机编号检索"),
    turnout: str | None = Query(default=None, description="按所属道岔检索"),
    model: str | None = Query(default=None, alias="model", description="按转辙机型号检索"),
    status: str | None = Query(default=None, description="正常、电流偏高、润滑不足、已更换"),
    sort: str = Query(default=DEFAULT_SORT, description="排序字段：code、action、friction"),
    order: str = Query(default="asc", description="排序方向：asc、desc"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号/道岔/型号/状态筛选，并在动作电流、摩擦电流等字段上做数值排序后分页。

    缺字段（如未填润滑状态、编号缺失）的记录仍参与排序分页，只是统一排在最后，不会被丢掉。
    """
    query = _resolve_query(keyword, turnout, model, status, sort, order, page, size)
    items, total = service.list_entries(**query)
    return PageResult(items=items, total=total, page=page, size=size)


# export 必须声明在 /{entry_id} 之前，否则会被当成 entry_id="export" 拦下。
@router.get("/export")
def export_entries(
    sort: str = Query(default=DEFAULT_SORT),
    order: str = Query(default="asc"),
) -> dict[str, Any]:
    """导出转辙机清单：顺序与台账列表保持一致，不另起一套排列。"""
    # 导出不受分页 200 条上限限制；页码/页大小给合法占位值只为复用参数校验。
    query = _resolve_query(None, None, None, None, sort, order, 1, 1)
    items, total = service.list_entries(
        keyword=None,
        turnout=None,
        model=None,
        status=None,
        sort_key=query["sort_key"],
        descending=query["descending"],
        page=1,
        size=10000,
    )
    return {"module": "pointmachine", "total": total, "sort": sort, "order": order, "items": items}


@router.get("/{entry_id}/detail")
def get_entry_detail(
    entry_id: int,
    keyword: str | None = None,
    turnout: str | None = None,
    model: str | None = None,
    status: str | None = None,
    sort: str = Query(default=DEFAULT_SORT),
    order: str = Query(default="asc"),
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """读取单条转辙机明细及其在当前排序/筛选下的位置；位置口径与列表完全一致。"""
    _resolve_query(keyword, turnout, model, status, sort, order, page, size)
    payload, message = service.get_entry_detail(
        entry_id,
        keyword=keyword or None,
        turnout=turnout or None,
        model=model or None,
        status=status or None,
        sort_key=sort,
        descending=order == "desc",
    )
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return payload


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条转辙机明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"转辙机 {entry_id} 不存在或已归档")
    return entry


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
