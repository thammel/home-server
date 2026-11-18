"""Talks to the bank over FinTS (python-fints). Everything bank-facing lives here, so tests can replace it.

A `BankSession` runs one sync: open a dialog, list accounts, fetch transactions per account.
Any step can stop with a TAN challenge; the caller shows it, then calls `resume()`.
The PIN only lives in the session object and is gone once the session is dropped.
"""

import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from fints.client import FinTS3PinTanClient, FinTSOperations, NeedTANResponse
from fints.exceptions import FinTSClientPINError, FinTSConnectionError, FinTSError

log = logging.getLogger("app.bank")

_PLACEHOLDER_REFERENCES = {"", "NONREF", "NOTPROVIDED"}
_UNSET = object()


class BankError(Exception):
    """Sync failed. `kind`: "pin" (never retry automatically), "connection" or "bank"."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class FetchedTransaction:
    booking_date: datetime.date
    value_date: datetime.date | None
    amount: Decimal
    currency: str
    counterparty: str
    counterparty_iban: str
    purpose: str
    reference: str


@dataclass
class FetchedAccount:
    iban: str
    name: str
    transactions: list[FetchedTransaction] = field(default_factory=list)


@dataclass
class FetchResult:
    accounts: list[FetchedAccount]
    state: bytes
    tan_mechanism: str | None


@dataclass
class Challenge:
    text: str
    decoupled: bool


class _Client(FinTS3PinTanClient):
    """Keeps the bank's 9xxx messages: python-fints reports dialog-init failures only as "PIN wrong?"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bank_errors: list[str] = []

    def _process_response(self, dialog, segment, response):
        if response.code.startswith("9"):
            self.bank_errors.append(f"{response.code} {response.text}")
        return super()._process_response(dialog, segment, response)


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _reference(data: dict) -> str:
    for key in ("end_to_end_reference", "customer_reference", "bank_reference"):
        ref = _text(data.get(key))
        if ref.upper() not in _PLACEHOLDER_REFERENCES:
            return ref
    return ""


def _convert(data: dict) -> FetchedTransaction:
    amount = data["amount"]
    # MT940: `date` is the value date, `entry_date` the booking date (missing at some banks).
    value_date = data.get("date")
    booking_date = data.get("entry_date") or value_date
    return FetchedTransaction(
        booking_date=datetime.date(
            booking_date.year, booking_date.month, booking_date.day
        ),
        value_date=datetime.date(value_date.year, value_date.month, value_date.day)
        if value_date
        else None,
        amount=Decimal(amount.amount),
        currency=amount.currency or "EUR",
        counterparty=_text(data.get("applicant_name")),
        counterparty_iban=_text(data.get("applicant_iban")).replace(" ", ""),
        purpose=_text(data.get("purpose")),
        reference=_reference(data),
    )


class BankSession:
    def __init__(
        self,
        *,
        bank_code: str,
        server_url: str,
        login_name: str,
        pin: str,
        product_id: str,
        state: bytes | None,
        tan_mechanism: str | None,
        since: datetime.date,
        until: datetime.date,
        skip_ibans: set[str],
    ):
        self._client = _Client(
            bank_code,
            login_name,
            pin,
            server_url,
            product_id=product_id,
            from_data=state or None,
        )
        self._tan_mechanism = tan_mechanism
        self._since, self._until = since, until
        self._skip_ibans = skip_ibans
        self._pending: NeedTANResponse | None = None
        self._open = False
        self._init_done = False
        self._todo = None
        self._results: list[FetchedAccount] = []

    def start(self) -> FetchResult | Challenge:
        return self._guard(self._start)

    def resume(self, tan: str = "") -> FetchResult | Challenge:
        def step():
            res = self._client.send_tan(self._pending, tan)
            if isinstance(res, NeedTANResponse):
                return self._wait(res)
            self._pending = None
            if not self._init_done:
                self._init_done = True
                return self._advance()
            return self._advance(res)

        return self._guard(step)

    def close(self):
        """End the bank dialog. Safe to call more than once."""
        if self._open:
            self._open = False
            try:
                self._client.__exit__(None, None, None)
            except Exception:
                log.warning("Closing the FinTS dialog failed", exc_info=True)
        self._client.pin = None

    def _start(self):
        self._choose_tan_mechanism()
        self._client.__enter__()
        self._open = True
        if self._client.init_tan_response:
            return self._wait(self._client.init_tan_response)
        self._init_done = True
        return self._advance()

    def _choose_tan_mechanism(self):
        client = self._client
        if self._tan_mechanism:
            client.set_tan_mechanism(self._tan_mechanism)
        if not client.get_current_tan_mechanism():
            client.fetch_tan_mechanisms()
            mechanisms = client.get_tan_mechanisms()
            # Prefer an app approval ("decoupled"): no TAN to type.
            decoupled = [
                sf
                for sf, p in mechanisms.items()
                if getattr(p, "decoupled_max_poll_number", None)
            ]
            choice = (
                decoupled
                or [sf for sf in mechanisms if sf != "999"]
                or list(mechanisms)
            )[:1]
            if choice:
                client.set_tan_mechanism(choice[0])
        if client.selected_tan_medium is None and client.is_tan_media_required():
            media = client.get_tan_media()[1]
            if media:
                client.set_tan_medium(media[0])
            else:
                # Some banks need no medium for app approval but still ask for one.
                client.selected_tan_medium = ""

    def _wait(self, response: NeedTANResponse) -> Challenge:
        self._pending = response
        return Challenge(
            text=_text(response.challenge)
            or "Approve the request in your banking app.",
            decoupled=bool(response.decoupled),
        )

    def _advance(self, value=_UNSET):
        client = self._client
        while True:
            if self._todo is None:
                res = client.get_sepa_accounts() if value is _UNSET else value
                value = _UNSET
                if isinstance(res, NeedTANResponse):
                    return self._wait(res)
                ops = {
                    a["account_number"]: a["supported_operations"]
                    for a in client.get_information().get("accounts", [])
                }
                # Depots and the like cannot list transactions; asking them fails with 9210.
                self._todo = [
                    a
                    for a in res
                    if ops.get(a.accountnumber, {}).get(
                        FinTSOperations.GET_TRANSACTIONS, True
                    )
                    and (a.iban or "") not in self._skip_ibans
                ]
                continue
            if self._todo:
                account = self._todo[0]
                res = (
                    client.get_transactions(account, self._since, self._until)
                    if value is _UNSET
                    else value
                )
                value = _UNSET
                if isinstance(res, NeedTANResponse):
                    return self._wait(res)
                self._todo.pop(0)
                self._results.append(
                    FetchedAccount(
                        iban=account.iban or account.accountnumber,
                        name=account.accountnumber,
                        transactions=[_convert(t.data) for t in res or []],
                    )
                )
                continue
            return self._finish()

    def _finish(self) -> FetchResult:
        mechanism = self._client.get_current_tan_mechanism()
        self.close()
        return FetchResult(
            accounts=self._results,
            state=self._client.deconstruct(including_private=False),
            tan_mechanism=mechanism,
        )

    def _guard(self, step):
        try:
            return step()
        except FinTSClientPINError as err:
            self.close()
            raise BankError(
                "pin",
                self._message("The bank rejected the login. Check login name and PIN."),
            ) from err
        except FinTSConnectionError as err:
            self.close()
            raise BankError(
                "connection", "Could not reach the bank. Check the FinTS URL."
            ) from err
        except FinTSError as err:
            self.close()
            raise BankError(
                "bank", self._message(f"The bank refused the request: {err}")
            ) from err

    def _message(self, fallback: str) -> str:
        return (
            "Bank: " + "; ".join(self._client.bank_errors)
            if self._client.bank_errors
            else fallback
        )
