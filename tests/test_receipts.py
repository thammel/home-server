"""Receipt scanning (ADR 0009). Test images are generated; no real receipt is ever used."""

import asyncio
import base64
import contextlib
import datetime
import io
import json
import urllib.error
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config, models
from app.auth import get_current_user, get_db, hash_password
from app.database import Base
from app.receipts import scanner, worker
from app.receipts.scanner import ScanFailed, ScannerUnavailable
from app.routers.api import expenses, receipts
from app.schemas import ReceiptItem, ReceiptResult

_ORIENTATION = 0x0112
_GPS_IFD = 0x8825


def photo(
    width=400, height=300, fmt="JPEG", rotate_tag=None, gps=False, mode="RGB"
) -> bytes:
    image = Image.new(mode, (width, height), "white")
    exif = Image.Exif()
    if rotate_tag:
        exif[_ORIENTATION] = rotate_tag
    if gps:
        exif[_GPS_IFD] = {1: "N", 2: (50.0, 46.0, 0.0)}
    out = io.BytesIO()
    image.save(out, format=fmt, exif=exif.tobytes() if fmt == "JPEG" else None)
    return out.getvalue()


def upload(client, data, name="receipt.jpg", mime="image/jpeg"):
    return client.post("/api/receipts/", files={"file": (name, data, mime)})


@pytest.fixture()
def flat(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RECEIPT_SCANNER_URL", "http://scanner.test/v1")
    monkeypatch.setattr(config, "RECEIPT_SCANNER_MODEL", "test-model")
    monkeypatch.setattr(config, "RECEIPT_SCANNER_KEY", None)
    monkeypatch.setattr(config, "RECEIPT_SCANNER_EXTRA", {})
    monkeypatch.setattr(config, "RECEIPTS_DIR", tmp_path / "receipts")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with session_factory() as db:
        people = [
            models.User(
                name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True
            ),
            models.User(name="Anna", password_hash=hash_password("testpass")),
            models.User(name="Ben", password_hash=hash_password("testpass")),
        ]
        db.add_all(people)
        db.commit()
        ids = {u.name: u.id for u in people}

    def make_app(user_id):
        app = FastAPI()
        app.include_router(receipts.router, prefix="/api/receipts")
        app.include_router(expenses.router, prefix="/api/expenses")

        def override_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        def override_user():
            with session_factory() as s:
                return s.get(models.User, user_id)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return app

    with (
        TestClient(make_app(ids["TestAdmin"])) as admin,
        TestClient(make_app(ids["Anna"])) as anna,
        TestClient(make_app(ids["Ben"])) as ben,
    ):
        yield {
            "admin": admin,
            "anna": anna,
            "ben": ben,
            "dir": tmp_path / "receipts",
            "db": session_factory,
            "ids": ids,
        }


def stored_image(flat, client, scan_id) -> Image.Image:
    res = client.get(f"/api/receipts/{scan_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    return Image.open(io.BytesIO(res.content))


def test_feature_off_without_scanner_url(flat, monkeypatch):
    monkeypatch.setattr(config, "RECEIPT_SCANNER_URL", None)
    assert flat["anna"].get("/api/receipts/").json()["enabled"] is False
    assert upload(flat["anna"], photo()).status_code == 404


def test_admin_cannot_scan_receipts(flat):
    assert flat["admin"].get("/api/receipts/").json()["enabled"] is False
    assert upload(flat["admin"], photo()).status_code == 403


def test_upload_queues_scan_and_stores_jpeg(flat):
    res = upload(flat["anna"], photo())
    assert res.status_code == 201, res.text
    scan = res.json()
    assert scan["status"] == "queued"
    assert scan["attempts"] == 0
    assert scan["result"] is None
    assert len(list(flat["dir"].glob("*.jpg"))) == 1
    assert not list(flat["dir"].glob("*.part"))

    listed = flat["anna"].get("/api/receipts/").json()
    assert listed["enabled"] is True
    assert [s["id"] for s in listed["scans"]] == [scan["id"]]


def test_upload_rotates_upright_scales_down_and_strips_exif(flat):
    scan = upload(flat["anna"], photo(4000, 3000, rotate_tag=6, gps=True)).json()
    image = stored_image(flat, flat["anna"], scan["id"])
    assert image.size == (1500, 2000)
    assert not image.getexif()


def test_upload_accepts_png_with_transparency(flat):
    res = upload(
        flat["anna"], photo(fmt="PNG", mode="RGBA"), name="r.png", mime="image/png"
    )
    assert res.status_code == 201, res.text
    assert stored_image(flat, flat["anna"], res.json()["id"]).mode == "RGB"


@pytest.mark.parametrize(
    "data",
    [b"not an image", photo(fmt="GIF", mode="P")],
    ids=["garbage", "gif"],
)
def test_upload_rejects_other_files(flat, data):
    assert upload(flat["anna"], data).status_code == 415
    assert not flat["dir"].exists() or not list(flat["dir"].iterdir())


def test_upload_rejects_too_large_file(flat, monkeypatch):
    monkeypatch.setattr(config, "RECEIPT_MAX_BYTES", 100)
    assert upload(flat["anna"], photo()).status_code == 413


def test_scans_are_private_to_the_uploader(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    ben = flat["ben"]
    assert ben.get("/api/receipts/").json()["scans"] == []
    assert ben.get(f"/api/receipts/{scan_id}").status_code == 404
    assert ben.get(f"/api/receipts/{scan_id}/image").status_code == 404
    assert ben.delete(f"/api/receipts/{scan_id}").status_code == 404
    assert flat["admin"].get(f"/api/receipts/{scan_id}").status_code == 403
    assert flat["admin"].get(f"/api/receipts/{scan_id}/image").status_code == 403
    assert flat["anna"].get(f"/api/receipts/{scan_id}").status_code == 200


def test_delete_removes_scan_and_image(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    assert flat["anna"].delete(f"/api/receipts/{scan_id}").status_code == 204
    assert flat["anna"].get(f"/api/receipts/{scan_id}").status_code == 404
    assert not list(flat["dir"].glob("*.jpg"))


# --- worker and scanner client ------------------------------------------------


class FakeScanner:
    """Scripted outcomes: each scan() pops the next one (ReceiptResult or exception)."""

    def __init__(self, *script):
        self.script = list(script)
        self.images = []

    def reachable(self):
        return True

    def scan(self, jpeg):
        self.images.append(jpeg)
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def result(total=6.0, items=((2, 1.5, 3.0), (1, 3.0, 3.0))):
    return ReceiptResult(
        shop="Corner Shop",
        date=datetime.date(2026, 11, 20),
        currency="EUR",
        total=total,
        items=[
            ReceiptItem(name=f"Item {n}", quantity=q, unit_price=u, line_total=t)
            for n, (q, u, t) in enumerate(items)
        ],
    )


def scan_row(flat, scan_id):
    with flat["db"]() as db:
        return db.get(models.ReceiptScan, scan_id)


def test_worker_stores_result_of_oldest_queued_scan(flat):
    first = upload(flat["anna"], photo()).json()["id"]
    second = upload(flat["anna"], photo()).json()["id"]
    fake = FakeScanner(result())

    assert worker.process_next(flat["db"], fake) is True

    assert scan_row(flat, second).status == "queued"
    scan = flat["anna"].get(f"/api/receipts/{first}").json()
    assert scan["status"] == "done"
    assert scan["model"] == "test-model"
    assert scan["result"]["total"] == 6.0
    assert scan["result"]["date"] == "2026-11-20"
    assert scan["result"]["warnings"] == []
    assert fake.images[0].startswith(b"\xff\xd8")


def test_worker_warns_when_items_do_not_add_up(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    worker.process_next(flat["db"], FakeScanner(result(total=7.5)))
    warnings = flat["anna"].get(f"/api/receipts/{scan_id}").json()["result"]["warnings"]
    assert warnings == ["Items add up to 6.00, the receipt total is 7.50"]


def test_worker_gives_up_after_three_bad_answers(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    fake = FakeScanner(*[ScanFailed("not JSON")] * 3)
    for expected in ("queued", "queued", "failed"):
        assert worker.process_next(flat["db"], fake) is True
        assert scan_row(flat, scan_id).status == expected
    scan = scan_row(flat, scan_id)
    assert scan.attempts == 3
    assert scan.error == "not JSON"


def test_worker_keeps_scan_queued_while_scanner_is_down(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    assert (
        worker.process_next(
            flat["db"], FakeScanner(ScannerUnavailable("connection refused"))
        )
        is False
    )
    scan = scan_row(flat, scan_id)
    assert (scan.status, scan.attempts) == ("queued", 0)


def test_worker_survives_scan_deleted_while_processing(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]

    class DeletingScanner(FakeScanner):
        def scan(self, jpeg):
            assert flat["anna"].delete(f"/api/receipts/{scan_id}").status_code == 204
            return result()

    assert worker.process_next(flat["db"], DeletingScanner()) is True
    assert scan_row(flat, scan_id) is None


def test_worker_fails_scan_whose_image_is_gone(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    for path in flat["dir"].glob("*.jpg"):
        path.unlink()
    worker.process_next(flat["db"], FakeScanner())
    scan = scan_row(flat, scan_id)
    assert (scan.status, scan.attempts, scan.error) == (
        "queued",
        1,
        "The receipt image is missing",
    )


def test_restart_requeues_interrupted_scans(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    with flat["db"]() as db:
        db.get(models.ReceiptScan, scan_id).status = "processing"
        db.commit()
    assert worker.reset_stuck(flat["db"]) == 1
    assert scan_row(flat, scan_id).status == "queued"


def answer(content):
    return {"choices": [{"message": {"content": content}}]}


def test_parse_answer_is_lenient_about_fences_dates_and_currency():
    content = '```json\n{"shop": "S", "date": "20.11.2026", "currency": "eur", "total": 1.005, "items": []}\n```'
    parsed = scanner.parse_answer(answer(content))
    assert (parsed.date, parsed.currency, parsed.total) == (None, "EUR", 1.0)


@pytest.mark.parametrize(
    "response", [answer("no json here"), answer('{"shop": "S"}'), {"choices": []}]
)
def test_parse_answer_rejects_unusable_answers(response):
    with pytest.raises(ScanFailed):
        scanner.parse_answer(response)


class FakeUrlopen:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.requests = reply, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return contextlib.nullcontext(io.BytesIO(json.dumps(self.reply).encode()))


def test_scanner_sends_openai_compatible_request(flat, monkeypatch):
    monkeypatch.setattr(config, "RECEIPT_SCANNER_KEY", "sk-test")
    monkeypatch.setattr(config, "RECEIPT_SCANNER_EXTRA", {"reasoning_effort": "low"})
    fake = FakeUrlopen(
        answer(
            '{"shop": "S", "date": "2026-11-20", "currency": "EUR", "total": 2, "items": []}'
        )
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    assert scanner.OpenAICompatibleScanner().scan(b"jpeg").total == 2.0

    request = fake.requests[0]
    assert request.full_url == "http://scanner.test/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-test"
    body = json.loads(request.data)
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "low"
    assert body["response_format"]["type"] == "json_schema"
    image = body["messages"][0]["content"][1]["image_url"]["url"]
    assert image == "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode()


def test_scanner_without_key_sends_no_authorization(flat, monkeypatch):
    fake = FakeUrlopen({"data": []})
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert scanner.OpenAICompatibleScanner().reachable() is True
    assert fake.requests[0].full_url == "http://scanner.test/v1/models"
    assert fake.requests[0].get_header("Authorization") is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (urllib.error.URLError("connection refused"), ScannerUnavailable),
        (
            urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"")),
            ScannerUnavailable,
        ),
        (
            urllib.error.HTTPError("u", 429, "limit", {}, io.BytesIO(b"")),
            ScannerUnavailable,
        ),
        (
            urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b"unknown model")),
            ScanFailed,
        ),
    ],
)
def test_scanner_errors_split_into_retry_later_and_attempt_failed(
    flat, monkeypatch, error, expected
):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(error=error))
    with pytest.raises(expected):
        scanner.OpenAICompatibleScanner().scan(b"jpeg")


def run_until_first_sleep(flat, monkeypatch, fake):
    sleeps = []

    async def stop(seconds):
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(worker.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.run(flat["db"], fake))
    return sleeps


def test_run_loop_scans_queue_then_idles(flat, monkeypatch):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    assert run_until_first_sleep(flat, monkeypatch, FakeScanner(result())) == [10]
    assert scan_row(flat, scan_id).status == "done"
    assert worker.status.reachable is True


def test_run_loop_backs_off_while_scanner_is_unreachable(flat, monkeypatch):
    scan_id = upload(flat["anna"], photo()).json()["id"]

    class Offline(FakeScanner):
        def reachable(self):
            return False

    assert run_until_first_sleep(flat, monkeypatch, Offline()) == [60]
    assert scan_row(flat, scan_id).status == "queued"
    assert worker.status.reachable is False


# --- review: accept, retry, expense deleted -----------------------------------


def set_status(flat, scan_id, status):
    with flat["db"]() as db:
        db.get(models.ReceiptScan, scan_id).status = status
        db.commit()


def expense_for(flat, client, payer, consumer, cost=6.0):
    res = client.post(
        "/api/expenses/",
        json={
            "date": "2026-11-20",
            "description": "Corner Shop",
            "category": "Groceries",
            "cost": cost,
            "shares": [
                {"user_id": flat["ids"][payer], "share": -cost},
                {"user_id": flat["ids"][consumer], "share": cost},
            ],
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def test_accept_links_expense_and_deleting_it_reopens_review(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    set_status(flat, scan_id, "done")
    expense_id = expense_for(flat, flat["anna"], "Anna", "Ben")

    res = flat["anna"].post(f"/api/receipts/{scan_id}/accept", json={"expense_id": expense_id})
    assert res.status_code == 200, res.text
    assert (res.json()["status"], res.json()["expense_id"]) == ("accepted", expense_id)

    assert flat["anna"].delete(f"/api/expenses/{expense_id}").status_code in (200, 204)
    scan = flat["anna"].get(f"/api/receipts/{scan_id}").json()
    assert (scan["status"], scan["expense_id"]) == ("done", None)


def test_accept_refuses_foreign_expense_and_unready_scan(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    foreign = expense_for(flat, flat["ben"], "Ben", "Ben")
    own = expense_for(flat, flat["anna"], "Anna", "Anna")
    assert flat["anna"].post(f"/api/receipts/{scan_id}/accept", json={"expense_id": own}).status_code == 409
    set_status(flat, scan_id, "done")
    assert flat["anna"].post(f"/api/receipts/{scan_id}/accept", json={"expense_id": foreign}).status_code == 404
    assert flat["anna"].post(f"/api/receipts/{scan_id}/accept", json={"expense_id": 9999}).status_code == 404


def test_retry_requeues_failed_scan_only(flat):
    scan_id = upload(flat["anna"], photo()).json()["id"]
    assert flat["anna"].post(f"/api/receipts/{scan_id}/retry").status_code == 409
    with flat["db"]() as db:
        scan = db.get(models.ReceiptScan, scan_id)
        scan.status, scan.attempts, scan.error = "failed", 3, "not JSON"
        db.commit()
    res = flat["anna"].post(f"/api/receipts/{scan_id}/retry").json()
    assert (res["status"], res["attempts"], res["error"]) == ("queued", 0, None)


def test_list_reports_scanner_status(flat, monkeypatch):
    monkeypatch.setattr(worker, "status", worker.ScannerStatus())
    assert flat["anna"].get("/api/receipts/").json()["scanner_reachable"] is None
    worker.status.record(True)
    listed = flat["anna"].get("/api/receipts/").json()
    assert listed["scanner_reachable"] is True
    assert listed["scanner_last_reachable_at"] is not None
