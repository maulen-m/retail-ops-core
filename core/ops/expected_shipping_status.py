"""Pure expected-shipping decisions with explicit current-site policies.

This module is the extraction seam for the seven existing expected-status sites.
It does not change any caller.  Each policy deliberately preserves the behavior
captured in ``tests/fixtures/expected_status/expected_status_goldens.json`` so a
later migration can move one adapter at a time without silently resolving a
known disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
)
from core.utils.kaspi_dates import parse_kaspi_date


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_SAME_DAY_CUTOFF = time(17, 0)

PACKABLE_STAGES = frozenset(
    {
        StageCode.ACCEPTED_PENDING_ASSEMBLY,
        StageCode.ASSEMBLED_PENDING_HANDOVER,
    }
)
TRANSITIONAL_NO_PACK_STAGES = frozenset(
    {
        StageCode.CANCELLING,
        StageCode.RETURN_REQUESTED,
    }
)
DISCHARGE_STAGES = frozenset(
    {
        StageCode.IN_DELIVERY,
        StageCode.ISSUED_COMPLETED,
        StageCode.CANCELLED,
        StageCode.RETURNED,
    }
)

_BOARD_SOURCE_TERMINAL_DETAILS = frozenset(
    {
        "COMPLETED",
        "CANCELLED",
        "RETURNED",
        "CANCELLING",
        "KASPI_DELIVERY_RETURN_REQUESTED",
        "RETURN_REQUESTED",
    }
)
_ARCHIVE_EXPLICIT_DETAILS = frozenset(
    {
        "COMPLETED",
        "CANCELLED",
        "RETURNED",
        "CANCELLING",
        "RETURN_REQUESTED",
        "KASPI_DELIVERY_RETURN_REQUESTED",
    }
)


class TemporalBucket(str, Enum):
    FUTURE = "FUTURE"
    TODAY = "TODAY"
    OVERDUE = "OVERDUE"


class ShippingDisposition(str, Enum):
    PACKABLE = "PACKABLE"
    SUSPENDED = "SUSPENDED"
    DISCHARGED = "DISCHARGED"
    UNCERTAIN = "UNCERTAIN"
    EXCLUDED = "EXCLUDED"


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_store_code(value: Any) -> str:
    """Delegate to the current canonical normalizer without a future import cycle."""

    from core.ops.waybill_shipping_obligations import (  # noqa: PLC0415
        normalize_store_code as canonical_normalize_store_code,
    )

    return canonical_normalize_store_code(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().casefold() not in {
        "",
        "0",
        "false",
        "no",
        "n",
        "none",
        "nan",
        "nat",
        "null",
        "<na>",
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if abs(seconds) >= 100_000_000_000:
            seconds /= 1000
        try:
            return datetime.fromtimestamp(seconds, tz=ALMATY_TZ)
        except (OSError, OverflowError, ValueError):
            return None
    text = _clean(value)
    if not text:
        return None
    if text.isdigit():
        return _parse_datetime(int(text))
    normalized = text.replace("Z", "+00:00")
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _line_value(line: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in line and line[name] is not None:
            return line[name]
    return None


def _api_order_from_line(line: Mapping[str, Any]) -> dict[str, Any]:
    delivery: dict[str, Any] = {}
    waybill = _line_value(line, "waybill_url", "waybill")
    courier_date = _line_value(
        line,
        "courier_transmission_date",
        "courierTransmissionDate",
    )
    if _clean(waybill):
        delivery["waybill"] = waybill
    if _clean(courier_date):
        delivery["courierTransmissionDate"] = courier_date
    attrs: dict[str, Any] = {
        "code": _line_value(line, "order_id", "code"),
        "state": _line_value(line, "state", "kaspi_status") or "",
        "status": _line_value(line, "status", "kaspi_status_detail") or "",
        "signatureRequired": _line_value(
            line, "signature_required", "signatureRequired"
        )
        or 0,
        "preOrder": _line_value(line, "pre_order", "preOrder") or 0,
        "deliveryMode": _line_value(line, "delivery_mode", "deliveryMode")
        or "DELIVERY",
        "returnedToWarehouse": _line_value(
            line, "returned_to_warehouse", "returnedToWarehouse"
        )
        or 0,
    }
    if delivery:
        attrs["kaspiDelivery"] = delivery
    return {"attributes": attrs}


def _db_row_from_line(line: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kaspi_status": _line_value(line, "kaspi_status", "state") or "",
        "kaspi_status_detail": _line_value(
            line, "kaspi_status_detail", "status"
        )
        or "",
        "internal_status": _line_value(line, "internal_status", "status_internal")
        or "",
        "signature_required": _line_value(
            line, "signature_required", "signatureRequired"
        )
        or 0,
        "pre_order": _line_value(line, "pre_order", "preOrder") or 0,
        "waybill_url": _line_value(line, "waybill_url", "waybill") or "",
        "delivery_mode": _line_value(line, "delivery_mode", "deliveryMode")
        or "DELIVERY",
        "returned_to_warehouse": _line_value(
            line, "returned_to_warehouse", "returnedToWarehouse"
        )
        or 0,
        "courier_transmission_date": _line_value(
            line,
            "courier_transmission_date",
            "courierTransmissionDate",
        )
        or "",
        "actual_shipment_date": _line_value(
            line, "actual_shipment_date", "actualShipmentDate"
        )
        or "",
    }


@dataclass(frozen=True)
class ExpectedShippingFacts:
    """Canonical grouped-order inputs used by every extracted policy."""

    store_code: str
    order_id: str
    lines: tuple[Mapping[str, Any], ...]
    target_date: date
    active_selector_member: bool | None = None
    durable_obligation_open: bool = False
    explicitly_excluded: bool = False
    day_state_excluded: bool = False
    same_day_cutoff: time = DEFAULT_SAME_DAY_CUTOFF

    @classmethod
    def from_lines(
        cls,
        lines: Sequence[Mapping[str, Any]],
        *,
        target_date: date,
        active_selector_member: bool | None = None,
        durable_obligation_open: bool = False,
        explicitly_excluded: bool = False,
        day_state_excluded: bool = False,
        same_day_cutoff: time = DEFAULT_SAME_DAY_CUTOFF,
    ) -> "ExpectedShippingFacts":
        if not lines:
            raise ValueError("expected shipping facts require at least one line")
        frozen_lines = tuple(dict(line) for line in lines)
        stores = {
            normalize_store_code(_line_value(line, "store_code", "store"))
            for line in frozen_lines
        }
        order_ids = {
            _clean(_line_value(line, "order_id", "code")) for line in frozen_lines
        }
        if len(stores) != 1 or "" in stores:
            raise ValueError("grouped expected-shipping lines require one store")
        if len(order_ids) != 1 or "" in order_ids:
            raise ValueError("grouped expected-shipping lines require one order_id")
        return cls(
            store_code=next(iter(stores)),
            order_id=next(iter(order_ids)),
            lines=frozen_lines,
            target_date=target_date,
            active_selector_member=active_selector_member,
            durable_obligation_open=durable_obligation_open,
            explicitly_excluded=explicitly_excluded,
            day_state_excluded=day_state_excluded,
            same_day_cutoff=same_day_cutoff,
        )

    @classmethod
    def from_mapping(
        cls,
        line: Mapping[str, Any],
        *,
        target_date: date,
        **context: Any,
    ) -> "ExpectedShippingFacts":
        return cls.from_lines([line], target_date=target_date, **context)

    @property
    def planned_dates(self) -> tuple[date, ...]:
        values = []
        for line in self.lines:
            value = parse_kaspi_date(
                _line_value(line, "planned_shipment_date", "planned_date")
            )
            if value is not None:
                values.append(value)
        return tuple(values)

    @property
    def planned_date(self) -> date | None:
        return min(self.planned_dates) if self.planned_dates else None

    @property
    def temporal_bucket(self) -> TemporalBucket:
        planned = self.planned_date
        if planned is None or planned == self.target_date:
            return TemporalBucket.TODAY
        if planned < self.target_date:
            return TemporalBucket.OVERDUE
        return TemporalBucket.FUTURE

    @property
    def api_stages(self) -> tuple[StageCode, ...]:
        return tuple(classify_kaspi_order_stage(_api_order_from_line(line)) for line in self.lines)

    @property
    def db_stages(self) -> tuple[StageCode, ...]:
        return tuple(
            classify_kaspi_stage_from_db_row(_db_row_from_line(line))
            for line in self.lines
        )

    @property
    def api_stage(self) -> StageCode:
        return self.api_stages[0]

    @property
    def db_stage(self) -> StageCode:
        return self.db_stages[0]

    @property
    def physically_handed_over(self) -> bool:
        return any(
            _clean(
                _line_value(
                    line,
                    "courier_transmission_date",
                    "courierTransmissionDate",
                )
            )
            or _clean(
                _line_value(line, "actual_shipment_date", "actualShipmentDate")
            )
            for line in self.lines
        )

    @property
    def signature_required(self) -> bool:
        return any(
            _truthy(_line_value(line, "signature_required", "signatureRequired"))
            for line in self.lines
        )

    @property
    def pre_order(self) -> bool:
        return any(
            _truthy(_line_value(line, "pre_order", "preOrder"))
            for line in self.lines
        )

    @property
    def returned_to_warehouse(self) -> bool:
        return any(
            _truthy(
                _line_value(
                    line, "returned_to_warehouse", "returnedToWarehouse"
                )
            )
            for line in self.lines
        )

    @property
    def size_ready(self) -> bool:
        return any(
            any(
                _clean(_line_value(line, name))
                for name in ("assigned_size", "my_size", "size")
            )
            for line in self.lines
        )

    @property
    def waybill_ready(self) -> bool:
        return any(
            _clean(_line_value(line, "waybill_url", "waybill"))
            or _truthy(_line_value(line, "waybill_downloaded"))
            for line in self.lines
        )

    @property
    def board_source_nonpackable(self) -> bool:
        for line in self.lines:
            state = _clean(_line_value(line, "state", "kaspi_status")).upper()
            detail = _clean(
                _line_value(line, "status", "kaspi_status_detail")
            ).upper()
            if (
                state in {"DELIVERY", "PICKUP"}
                or detail in _BOARD_SOURCE_TERMINAL_DETAILS
                or _truthy(
                    _line_value(
                        line, "returned_to_warehouse", "returnedToWarehouse"
                    )
                )
            ):
                return True
        return self.physically_handed_over

    @property
    def created_at(self) -> datetime | None:
        values = [
            parsed
            for parsed in (
                _parse_datetime(
                    _line_value(line, "created_at", "creation_at", "creationDate")
                )
                for line in self.lines
            )
            if parsed is not None
        ]
        return min(values) if values else None

    @property
    def created_before_or_at_cutoff(self) -> bool:
        created = self.created_at
        if created is None:
            return True
        cutoff = datetime.combine(
            self.target_date,
            self.same_day_cutoff,
            tzinfo=ALMATY_TZ,
        )
        return created <= cutoff


@dataclass(frozen=True)
class ExpectedShippingDecision:
    """Typed common result plus an exact projection for the selected site."""

    policy_name: str
    normalized_store: str
    order_id: str
    temporal_bucket: TemporalBucket
    disposition: ShippingDisposition
    stage: StageCode
    packable: bool
    discharged: bool
    carryforward: bool
    board_visible: bool
    board_label: str | None
    waybill_eligible: bool
    reason_codes: tuple[str, ...]
    projection: Any


class ExpectedShippingPolicy:
    """Base protocol implemented by the named, stateless site policies."""

    name = "base"
    divergence_ids: tuple[str, ...] = ()

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        raise NotImplementedError


def _make_decision(
    facts: ExpectedShippingFacts,
    *,
    policy_name: str,
    disposition: ShippingDisposition,
    stage: StageCode,
    projection: Any,
    packable: bool = False,
    discharged: bool = False,
    carryforward: bool = False,
    board_visible: bool = False,
    board_label: str | None = None,
    waybill_eligible: bool = False,
    reason_codes: Iterable[str] = (),
    temporal_bucket: TemporalBucket | None = None,
) -> ExpectedShippingDecision:
    return ExpectedShippingDecision(
        policy_name=policy_name,
        normalized_store=facts.store_code,
        order_id=facts.order_id,
        temporal_bucket=temporal_bucket or facts.temporal_bucket,
        disposition=disposition,
        stage=stage,
        packable=packable,
        discharged=discharged,
        carryforward=carryforward,
        board_visible=board_visible,
        board_label=board_label,
        waybill_eligible=waybill_eligible,
        reason_codes=tuple(reason_codes),
        projection=projection,
    )


def _normalize_order_ids_by_store(
    values: Mapping[str, Iterable[Any]] | None,
    *,
    merge_aliases: bool,
) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = {}
    for raw_store, raw_ids in dict(values or {}).items():
        store = normalize_store_code(raw_store)
        if not store:
            continue
        order_ids = {_clean(value) for value in raw_ids or [] if _clean(value)}
        if merge_aliases:
            normalized.setdefault(store, set()).update(order_ids)
        else:
            normalized[store] = order_ids
    return {store: set(order_ids) for store, order_ids in sorted(normalized.items())}


class BoardRenderPolicy(ExpectedShippingPolicy):
    """Board parity policy.

    Preserves KNOWN_DIVERGENCE_SAME_DAY_AFTER_CUTOFF and
    KNOWN_DIVERGENCE_OVERDUE_ACCEPTED_WITHOUT_WAYBILL.
    """

    name = "board_render"
    divergence_ids = (
        "KNOWN_DIVERGENCE_SAME_DAY_AFTER_CUTOFF",
        "KNOWN_DIVERGENCE_OVERDUE_ACCEPTED_WITHOUT_WAYBILL",
    )

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        nonpackable = facts.board_source_nonpackable
        pending_stage = any(stage in PACKABLE_STAGES for stage in facts.db_stages)
        pending_carryforward = (
            facts.temporal_bucket == TemporalBucket.OVERDUE
            and pending_stage
            and not nonpackable
        )
        today_pending = (
            facts.temporal_bucket == TemporalBucket.TODAY
            and facts.planned_date == facts.target_date
            and pending_stage
            and facts.created_before_or_at_cutoff
        )
        scope_excluded = facts.explicitly_excluded or facts.day_state_excluded
        selected = (
            not nonpackable
            and not scope_excluded
            and (pending_carryforward or today_pending)
        )
        rendered_status = "OVERDUE" if pending_carryforward else "TODAY"
        projection = {
            "normalized_store": facts.store_code,
            "pending_carryforward": pending_carryforward,
            "nonpackable": nonpackable,
            "selected": selected,
            "rendered_status": rendered_status,
        }
        reasons = []
        if nonpackable:
            reasons.append("BOARD_SOURCE_NONPACKABLE")
        elif scope_excluded:
            reasons.append("EXPLICIT_SCOPE_EXCLUSION")
        elif pending_carryforward:
            reasons.append("BOARD_PENDING_CARRYFORWARD")
        elif today_pending:
            reasons.append("BOARD_TODAY_PENDING")
        elif facts.planned_date == facts.target_date and not facts.created_before_or_at_cutoff:
            reasons.append("BOARD_AFTER_SAME_DAY_CUTOFF")
        else:
            reasons.append("BOARD_OUT_OF_SCOPE")
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=(
                ShippingDisposition.PACKABLE if selected else ShippingDisposition.EXCLUDED
            ),
            stage=facts.db_stage,
            packable=selected,
            carryforward=pending_carryforward,
            board_visible=selected,
            board_label=rendered_status,
            waybill_eligible=carryforward.evaluate(facts).waybill_eligible,
            reason_codes=reasons,
            projection=projection,
        )


class ExpectedOrdersPolicy(ExpectedShippingPolicy):
    """Closeout expected-order construction policy.

    Preserves KNOWN_DIVERGENCE_STORE_ALIAS_COLLISION,
    KNOWN_DIVERGENCE_SAME_DAY_AFTER_CUTOFF, and
    KNOWN_DIVERGENCE_ACTIVE_TERMINAL_TRUST.
    """

    name = "expected_orders"
    divergence_ids = (
        "KNOWN_DIVERGENCE_STORE_ALIAS_COLLISION",
        "KNOWN_DIVERGENCE_SAME_DAY_AFTER_CUTOFF",
        "KNOWN_DIVERGENCE_ACTIVE_TERMINAL_TRUST",
    )

    def normalize_active_order_ids_by_store(
        self, values: Mapping[str, Iterable[Any]] | None
    ) -> dict[str, set[str]]:
        return _normalize_order_ids_by_store(values, merge_aliases=False)

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        reasons = []
        if facts.planned_date is None:
            reasons.append("invalid_planned_date")
        elif facts.planned_date > facts.target_date:
            reasons.append("future_planned_date")
        if facts.signature_required:
            reasons.append("signature_required")
        if facts.returned_to_warehouse:
            reasons.append("returned_to_warehouse")
        if facts.physically_handed_over:
            reasons.append("already_handed_over")
        if facts.explicitly_excluded or facts.day_state_excluded:
            reasons.append("explicit_scope_exclusion")

        ready_stages = [stage for stage in facts.db_stages if stage in PACKABLE_STAGES]
        if facts.active_selector_member is None and not ready_stages:
            reasons.append("stage_" + facts.db_stage.value)
        if facts.active_selector_member is False:
            reasons.append("not_api_active")

        eligible = not reasons
        selected_stage = (
            ready_stages[0]
            if ready_stages
            else StageCode.ACCEPTED_PENDING_ASSEMBLY
        )
        projection = None
        if eligible:
            projection = {
                "store_code": facts.store_code,
                "planned_shipment_date": facts.planned_date.isoformat(),
                "stage": selected_stage.value,
                "overdue": facts.planned_date < facts.target_date,
            }
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=(
                ShippingDisposition.PACKABLE if eligible else ShippingDisposition.EXCLUDED
            ),
            stage=selected_stage,
            packable=eligible,
            carryforward=eligible
            and facts.temporal_bucket == TemporalBucket.OVERDUE,
            waybill_eligible=eligible and facts.waybill_ready,
            reason_codes=reasons or ("EXPECTED_ORDER_INCLUDED",),
            projection=projection,
        )


class ObligationsPolicy(ExpectedShippingPolicy):
    """Durable shipping-obligation reconciliation policy.

    Preserves KNOWN_DIVERGENCE_STORE_ALIAS_COLLISION,
    KNOWN_DIVERGENCE_ARCHIVE_AMBIGUITY, and
    KNOWN_DIVERGENCE_ACTIVE_TERMINAL_TRUST.
    """

    name = "obligations"
    divergence_ids = (
        "KNOWN_DIVERGENCE_STORE_ALIAS_COLLISION",
        "KNOWN_DIVERGENCE_ARCHIVE_AMBIGUITY",
        "KNOWN_DIVERGENCE_ACTIVE_TERMINAL_TRUST",
    )

    def normalize_active_order_ids_by_store(
        self, values: Mapping[str, Iterable[Any]] | None
    ) -> dict[str, set[str]]:
        return _normalize_order_ids_by_store(values, merge_aliases=True)

    @staticmethod
    def _stage(facts: ExpectedShippingFacts) -> StageCode:
        line = facts.lines[0]
        state = _clean(_line_value(line, "state", "kaspi_status")).upper()
        status = _clean(
            _line_value(line, "status", "kaspi_status_detail")
        ).upper()
        if facts.returned_to_warehouse:
            return StageCode.RETURNED
        if status in {"RETURN_REQUESTED", "KASPI_DELIVERY_RETURN_REQUESTED"}:
            return StageCode.RETURN_REQUESTED
        if state == "ARCHIVE" and status not in _ARCHIVE_EXPLICIT_DETAILS:
            return StageCode.UNKNOWN
        return facts.api_stage

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        stage = self._stage(facts)
        ledger_status = "unresolved"
        discharge_reason = ""
        suspension_reason = ""
        issue_code = ""
        if stage in PACKABLE_STAGES:
            disposition = ShippingDisposition.PACKABLE
        elif stage in TRANSITIONAL_NO_PACK_STAGES:
            disposition = ShippingDisposition.SUSPENDED
            ledger_status = "suspended"
            suspension_reason = stage.value
        elif stage in DISCHARGE_STAGES:
            disposition = ShippingDisposition.DISCHARGED
            ledger_status = "discharged"
            discharge_reason = stage.value
        else:
            disposition = ShippingDisposition.UNCERTAIN
            issue_code = "obligation_api_stage_uncertain"
        projection = {
            "ledger_status": ledger_status,
            "last_stage": stage.value,
            "discharge_reason": discharge_reason,
            "suspension_reason": suspension_reason,
            "issue_code": issue_code,
        }
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=disposition,
            stage=stage,
            packable=stage in PACKABLE_STAGES,
            discharged=stage in DISCHARGE_STAGES,
            carryforward=ledger_status in {"unresolved", "suspended"},
            waybill_eligible=stage == StageCode.ASSEMBLED_PENDING_HANDOVER
            and facts.waybill_ready,
            reason_codes=(
                issue_code
                or suspension_reason
                or discharge_reason
                or "OBLIGATION_PACKABLE",
            ),
            projection=projection,
        )


class CarryforwardPolicy(ExpectedShippingPolicy):
    """Waybill-ready overdue selector policy.

    Preserves KNOWN_DIVERGENCE_OVERDUE_ACCEPTED_WITHOUT_WAYBILL.
    """

    name = "carryforward"
    divergence_ids = ("KNOWN_DIVERGENCE_OVERDUE_ACCEPTED_WITHOUT_WAYBILL",)

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        eligible = (
            not facts.physically_handed_over
            and not facts.signature_required
            and any(stage == StageCode.ASSEMBLED_PENDING_HANDOVER for stage in facts.db_stages)
            and facts.size_ready
            and facts.temporal_bucket == TemporalBucket.OVERDUE
            and facts.waybill_ready
            and not facts.explicitly_excluded
            and not facts.day_state_excluded
        )
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=(
                ShippingDisposition.PACKABLE if eligible else ShippingDisposition.EXCLUDED
            ),
            stage=facts.db_stage,
            packable=eligible,
            carryforward=eligible,
            waybill_eligible=eligible,
            reason_codes=(
                "WAYBILL_READY_OVERDUE" if eligible else "NOT_WAYBILL_READY_OVERDUE",
            ),
            projection=eligible,
        )


class PrewindowPolicy(ExpectedShippingPolicy):
    """Prewindow parity rebuild policy; it consumes Board-render semantics unchanged."""

    name = "prewindow"
    divergence_ids: tuple[str, ...] = ()

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        decision = board_render.evaluate(facts)
        return replace(
            decision,
            policy_name=self.name,
            reason_codes=("PREWINDOW_BOARD_REBUILD", *decision.reason_codes),
        )


class WaybillSplitPolicy(ExpectedShippingPolicy):
    """Daily-waybill group split policy; future and missing dates remain TODAY."""

    name = "waybill_split"
    divergence_ids: tuple[str, ...] = ()

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        overdue = any(value < facts.target_date for value in facts.planned_dates)
        rendered = "OVERDUE" if overdue else "TODAY"
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=ShippingDisposition.PACKABLE,
            stage=facts.db_stage,
            packable=True,
            carryforward=overdue,
            board_label=rendered,
            reason_codes=("WAYBILL_GROUP_" + rendered,),
            projection=rendered,
        )


class ApiFallbackPolicy(ExpectedShippingPolicy):
    """API planned-date policy: explicit date wins, then inclusive 17:00 fallback."""

    name = "api_fallback"
    divergence_ids: tuple[str, ...] = ()

    @staticmethod
    def resolve_planned_date(facts: ExpectedShippingFacts) -> date | None:
        line = facts.lines[0]
        explicit = _line_value(line, "planned_at", "api_planned_at")
        if explicit:
            parsed_explicit = _parse_datetime(explicit)
            if parsed_explicit is not None:
                return parsed_explicit.date()
            parsed_date = parse_kaspi_date(explicit)
            if parsed_date is not None:
                return parsed_date

        planned = parse_kaspi_date(
            _line_value(line, "planned_shipment_date", "planned_date")
        )
        if planned is not None:
            return planned

        created = _parse_datetime(
            _line_value(line, "creation_at", "created_at", "creationDate")
        )
        if created is None:
            return None
        cutoff = datetime.combine(created.date(), facts.same_day_cutoff, tzinfo=ALMATY_TZ)
        return created.date() + (timedelta(days=1) if created > cutoff else timedelta())

    def evaluate(self, facts: ExpectedShippingFacts) -> ExpectedShippingDecision:
        planned = self.resolve_planned_date(facts)
        if planned is None:
            temporal = TemporalBucket.TODAY
            disposition = ShippingDisposition.UNCERTAIN
            reason = "API_DATE_MISSING"
        elif planned < facts.target_date:
            temporal = TemporalBucket.OVERDUE
            disposition = ShippingDisposition.PACKABLE
            reason = "API_DATE_RESOLVED"
        elif planned > facts.target_date:
            temporal = TemporalBucket.FUTURE
            disposition = ShippingDisposition.PACKABLE
            reason = "API_DATE_RESOLVED"
        else:
            temporal = TemporalBucket.TODAY
            disposition = ShippingDisposition.PACKABLE
            reason = "API_DATE_RESOLVED"
        return _make_decision(
            facts,
            policy_name=self.name,
            disposition=disposition,
            stage=facts.api_stage,
            packable=planned is not None,
            reason_codes=(reason,),
            temporal_bucket=temporal,
            projection=planned.isoformat() if planned is not None else None,
        )


board_render = BoardRenderPolicy()
expected_orders = ExpectedOrdersPolicy()
obligations = ObligationsPolicy()
carryforward = CarryforwardPolicy()
prewindow = PrewindowPolicy()
waybill_split = WaybillSplitPolicy()
api_fallback = ApiFallbackPolicy()

POLICIES = (
    board_render,
    expected_orders,
    obligations,
    carryforward,
    prewindow,
    waybill_split,
    api_fallback,
)
POLICY_BY_NAME = {policy.name: policy for policy in POLICIES}


def decide_expected_shipping_status(
    facts: ExpectedShippingFacts,
    *,
    policy: ExpectedShippingPolicy,
) -> ExpectedShippingDecision:
    """Evaluate one grouped order under one explicit current-site policy."""

    return policy.evaluate(facts)


__all__ = [
    "ApiFallbackPolicy",
    "BoardRenderPolicy",
    "CarryforwardPolicy",
    "DEFAULT_SAME_DAY_CUTOFF",
    "DISCHARGE_STAGES",
    "ExpectedOrdersPolicy",
    "ExpectedShippingDecision",
    "ExpectedShippingFacts",
    "ExpectedShippingPolicy",
    "ObligationsPolicy",
    "PACKABLE_STAGES",
    "POLICIES",
    "POLICY_BY_NAME",
    "PrewindowPolicy",
    "ShippingDisposition",
    "TRANSITIONAL_NO_PACK_STAGES",
    "TemporalBucket",
    "WaybillSplitPolicy",
    "api_fallback",
    "board_render",
    "carryforward",
    "decide_expected_shipping_status",
    "expected_orders",
    "normalize_store_code",
    "obligations",
    "prewindow",
    "waybill_split",
]
