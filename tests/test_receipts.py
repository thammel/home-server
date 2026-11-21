"""Receipt scanning (ADR 0009). Test images are generated; no real receipt is ever used."""

import io

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
from app.routers.api import receipts

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
        yield {"admin": admin, "anna": anna, "ben": ben, "dir": tmp_path / "receipts"}


def stored_image(flat, client, scan_id) -> Image.Image:
    res = client.get(f"/api/receipts/{scan_id}/image")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    return Image.open(io.BytesIO(res.content))


def test_feature_off_without_scanner_url(flat, monkeypatch):
    monkeypatch.setattr(config, "RECEIPT_SCANNER_URL", None)
    assert flat["anna"].get("/api/receipts/").json() == {"enabled": False, "scans": []}
    assert upload(flat["anna"], photo()).status_code == 404


def test_admin_cannot_scan_receipts(flat):
    assert flat["admin"].get("/api/receipts/").json() == {"enabled": False, "scans": []}
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
