"""The only code that talks to the vision model: one OpenAI-compatible chat completions endpoint (ADR 0009)."""

import base64
import json
import urllib.error
import urllib.request

from pydantic import ValidationError

from app import config
from app.schemas import ReceiptResult

_INSTRUCTIONS = (
    "Return the shop name as customers know it (the brand, not the legal company name), purchase date (YYYY-MM-DD), currency code, "
    "the total paid, and every line item. A line like '2 Stk x 1,79' or '2 * 1,99' gives "
    "quantity and unit price of the item it belongs to; line_total is the amount at the "
    "right edge. Deposits (Pfand) and discounts are items; discounts are negative. "
    "Answer only with JSON matching the schema."
)
_IMAGE_PROMPT = "Read this receipt. " + _INSTRUCTIONS
_TEXT_PROMPT = "Read this receipt, given as text extracted from a PDF. " + _INSTRUCTIONS


_SCHEMA = {
    "type": "object",
    "properties": {
        "shop": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "currency": {"type": "string", "description": "ISO 4217 code, e.g. EUR"},
        "total": {"type": "number"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {
                        "type": "number",
                        "description": "price of one unit",
                    },
                    "line_total": {
                        "type": "number",
                        "description": "amount at the right edge of the line = quantity * unit_price",
                    },
                },
                "required": ["name", "quantity", "unit_price", "line_total"],
            },
        },
    },
    "required": ["shop", "date", "currency", "total", "items"],
}

_CHECK_TIMEOUT = 3
_SCAN_TIMEOUT = 300


def configured() -> bool:
    return bool(config.RECEIPT_SCANNER_URL and config.RECEIPT_SCANNER_MODEL)


class ScannerUnavailable(Exception):
    """The endpoint is down or overloaded; try again later without counting an attempt."""


class ScannerMisconfigured(ScannerUnavailable):
    """Wrong URL, model or key: no scan can succeed until the operator fixes the config."""

    def __init__(self, code: int):
        super().__init__(f"HTTP {code}, check the scanner URL, model and key")
        self.code = code


class ScanFailed(Exception):
    """The endpoint answered, but not with a usable result; counts as an attempt."""


# These answers mean the config is wrong, not this receipt; counting them as attempts
# would fail every queued scan within seconds.
_CONFIG_ERRORS = {401, 403, 404, 405}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would send the Authorization header on to the redirect target."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _request(path: str, body: dict | None, timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if config.RECEIPT_SCANNER_KEY:
        headers["Authorization"] = f"Bearer {config.RECEIPT_SCANNER_KEY}"
    req = urllib.request.Request(
        config.RECEIPT_SCANNER_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with _opener.open(req, timeout=timeout) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise ScannerUnavailable(f"HTTP {e.code}") from None
        if e.code in _CONFIG_ERRORS or 300 <= e.code < 400:
            raise ScannerMisconfigured(e.code) from None
        detail = e.read().decode(errors="replace")[:300]
        raise ScanFailed(f"HTTP {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ScannerUnavailable(str(e)) from None
    except json.JSONDecodeError:
        raise ScanFailed(
            "The scanner answered with something other than JSON"
        ) from None


class OpenAICompatibleScanner:
    def reachable(self) -> bool:
        """Any answer counts: not every endpoint serves /models. Auth errors do not."""
        try:
            _request("/models", None, _CHECK_TIMEOUT)
        except ScannerMisconfigured as e:
            return e.code in (404, 405)
        except ScannerUnavailable:
            return False
        except ScanFailed:
            pass
        return True

    def scan(self, jpeg: bytes) -> ReceiptResult:
        image_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        return self._ask(
            [
                {"type": "text", "text": _IMAGE_PROMPT},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        )

    def scan_text(self, text: str) -> ReceiptResult:
        return self._ask([{"type": "text", "text": f"{_TEXT_PROMPT}\n\n{text}"}])

    def _ask(self, content: list[dict]) -> ReceiptResult:
        body = {
            "model": config.RECEIPT_SCANNER_MODEL,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "receipt", "schema": _SCHEMA, "strict": True},
            },
            **config.RECEIPT_SCANNER_EXTRA,
        }
        response = _request("/chat/completions", body, _SCAN_TIMEOUT)
        return parse_answer(response)


def parse_answer(response: dict) -> ReceiptResult:
    try:
        content = response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise ScanFailed("The scanner answer has no message") from None
    text = content.strip()
    # Some models wrap JSON in a Markdown fence even when asked not to.
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return ReceiptResult.model_validate_json(text)
    except ValidationError as e:
        raise ScanFailed(
            f"The scanner answer does not match the receipt schema: {e.errors()[0]['msg']}"
        ) from None
