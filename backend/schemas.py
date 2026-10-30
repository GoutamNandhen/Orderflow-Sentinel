from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

ERRORS = [
    "API_TIMEOUT",
    "RATE_LIMIT",
    "TOKEN_EXPIRED",
    "ADDRESS_REJECTED",
    "PAYMENT_DECLINED",
    "UNMATCHED_DEBIT",
    "DUPLICATE_ORDER",
    "OUT_OF_STOCK",
    "STORE_CLOSED",
    "RIDER_LATE",
]
ACTIONS = [
    "RETRY",
    "REFRESH_TOKEN",
    "SWITCH_GATEWAY",
    "CHECK_PAYMENT",
    "SEND_PAYMENT_LINK",
    "CONFIRM_ORDER",
    "REFUND",
    "REASSIGN_STORE",
    "OFFER_SUBSTITUTE",
    "NEW_SLOT",
    "PRIORITY_RIDER",
    "NOTIFY_CUSTOMER",
    "CANCEL",
    "ESCALATE",
    "CORRECT_ADDRESS",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Item(Strict):
    product_id: str
    qty: int = Field(ge=1, le=20)


class Booking(Strict):
    user_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(max_length=30)
    address: str = Field(min_length=8, max_length=400)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    items: list[Item] = Field(min_length=1, max_length=20)
    payment_method: Literal["UPI", "CARD", "WALLET", "COD"] = "UPI"
    promise_minutes: int = Field(default=40, ge=15, le=1440)
    contact_mode: Literal["customer", "demo"] = "customer"

    @model_validator(mode="after")
    def validate_contact(self):
        if self.contact_mode == "demo":
            if self.phone != "DEMO_CONTACT" or self.address != "DEMO_LOCATION":
                raise ValueError(
                    "Anonymized demo mode requires the exact non-personal contact markers"
                )
        elif not re.fullmatch(r"(?:\+91)?[6-9][0-9]{9}", self.phone):
            raise ValueError("Customer mode requires a valid mobile number")
        return self


class Settings(Strict):
    enabled: bool = True
    failing_positions: list[int] = Field(
        default_factory=lambda: [2, 4, 5], max_length=5
    )
    selection: Literal["rotation", "weighted"] = "rotation"
    seed: int = Field(default=42, ge=0, le=2147483647)
    force_error: str | None = None
    auto_confidence: float = Field(default=0.90, ge=0.90, le=1)
    auto_risk: float = Field(default=30, ge=0, le=30)
    high_value_paise: int = Field(default=500000, ge=10000, le=100000000)
    close_deadline_minutes: int = Field(default=12, ge=1, le=30)
    alert_fraction: float = Field(default=0.70, ge=0.1, le=0.95)
    retry_failures: int = Field(default=0, ge=0, le=3)

    @field_validator("failing_positions")
    @classmethod
    def positions(cls, v):
        if len(set(v)) != len(v) or any(i not in range(1, 6) for i in v):
            raise ValueError("Use unique positions from 1 through 5")
        return sorted(v)

    @field_validator("force_error")
    @classmethod
    def force(cls, v):
        if v is not None and v not in ERRORS:
            raise ValueError("Unknown forced error")
        return v


class ActionRequest(Strict):
    action: str
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=1000)
    confirmed: bool = False

    @field_validator("action")
    @classmethod
    def valid_action(cls, v):
        if v not in ACTIONS:
            raise ValueError("Unknown action")
        return v


class Acceptance(Strict):
    expected_version: int = Field(ge=1)
    accept: bool


class DemoRequest(Strict):
    profile: Literal["next", "judge", "exhaustion"] = "next"
    error_type: str | None = None

    @field_validator("error_type")
    @classmethod
    def valid(cls, v):
        if v is not None and v not in ERRORS:
            raise ValueError("Unknown error")
        return v


class Login(Strict):
    password: str = Field(max_length=200)


class NoteRequest(Strict):
    note: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
