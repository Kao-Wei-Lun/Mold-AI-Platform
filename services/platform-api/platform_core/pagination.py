from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.request import Request


class PaginationValueError(ValueError):
    pass


def paginate(
    request: Request,
    queryset: QuerySet,
    *,
    allowed_sort: dict[str, str],
    default_sort: str,
) -> tuple[list, dict[str, object]]:
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 25))))
    except ValueError as exc:
        raise PaginationValueError("Invalid page or page_size.") from exc
    requested_sort = str(request.query_params.get("sort", "")).strip()
    descending = requested_sort.startswith("-")
    sort_key = requested_sort.removeprefix("-") or default_sort.removeprefix("-")
    field = allowed_sort.get(sort_key)
    if field is None:
        raise PaginationValueError(f"Unsupported sort field: {sort_key}")
    if requested_sort:
        ordering = f"-{field}" if descending else field
    else:
        ordering = default_sort
    ordered = queryset.order_by(ordering)
    total = ordered.count()
    start = (page - 1) * page_size
    items = list(ordered[start : start + page_size])
    return items, {
        "number": page,
        "size": page_size,
        "total": total,
        "sort": requested_sort or default_sort,
        "has_next": start + page_size < total,
    }
