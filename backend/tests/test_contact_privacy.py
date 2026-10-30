import pytest
from pydantic import ValidationError
from backend.schemas import Booking


def test_demo_requires_nonpersonal_markers(booking):
    assert Booking(**booking).phone == "DEMO_CONTACT"
    for field in ("phone", "address"):
        with pytest.raises(ValidationError):
            Booking(**{**booking, field: "arbitrary contact text"})


def test_demo_markers_are_not_customer_contacts(booking):
    with pytest.raises(ValidationError):
        Booking(**{**booking, "contact_mode": "customer"})
