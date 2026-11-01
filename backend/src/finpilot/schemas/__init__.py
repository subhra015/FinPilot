"""Domain schemas and validation contracts (Layer 3).

Governed by ARCHITECTURE.md §5, PROJECT_SPEC.md §3, §10-11,
and Layer 3 Gate.
"""

from __future__ import annotations

from .candles import CandleBar, CandleBatch
from .common import (
    DateRangeFilter,
    PaginationParams,
    SortDirection,
    SortOrderSpec,
    normalize_to_utc,
)
from .datasets import (
    DatasetManifestBase,
    DatasetManifestCreate,
    DatasetManifestRead,
    DataSourceMetadata,
)
from .errors import (
    DomainValidationError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ResourceNotFoundError,
    sanitize_error_message,
)
from .execution_cost import (
    CostBreakdown,
    OrderBase,
    OrderCreate,
    OrderRead,
    PositionRead,
)
from .instruments import (
    InstrumentBase,
    InstrumentCreate,
    InstrumentRead,
    KnownInstrumentRegistry,
)
from .scoping import (
    UserScope,
    enforce_account_access,
    enforce_resource_owner,
)
from .state_transitions import (
    VALID_ORDER_TRANSITIONS,
    validate_ledger_sequence,
    validate_order_transition,
)
from .trade_policy import (
    TradePolicyV1Contract,
    TradeProposal,
)

__all__ = [
    "ErrorCode",
    "ErrorDetail",
    "ErrorResponse",
    "DomainValidationError",
    "InvalidStateTransitionError",
    "PermissionDeniedError",
    "ResourceNotFoundError",
    "sanitize_error_message",
    "PaginationParams",
    "DateRangeFilter",
    "SortDirection",
    "SortOrderSpec",
    "normalize_to_utc",
    "InstrumentBase",
    "InstrumentCreate",
    "InstrumentRead",
    "KnownInstrumentRegistry",
    "CandleBar",
    "CandleBatch",
    "DataSourceMetadata",
    "DatasetManifestBase",
    "DatasetManifestCreate",
    "DatasetManifestRead",
    "TradePolicyV1Contract",
    "TradeProposal",
    "CostBreakdown",
    "OrderBase",
    "OrderCreate",
    "OrderRead",
    "PositionRead",
    "VALID_ORDER_TRANSITIONS",
    "validate_order_transition",
    "validate_ledger_sequence",
    "UserScope",
    "enforce_resource_owner",
    "enforce_account_access",
]
