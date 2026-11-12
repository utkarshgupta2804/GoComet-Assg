from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator


DB_PATH = Path(os.getenv("AUCTION_DB", Path(__file__).resolve().parents[1] / "auction.db"))
TRIGGERS = {"bid_received", "any_rank_change", "l1_change"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"Invalid date/time: {value}") from exc
    if parsed.tzinfo is None:
        raise HTTPException(422, "Date/time values must include a timezone")
    return parsed.astimezone(timezone.utc)


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            reference_id TEXT NOT NULL UNIQUE,
            starts_at TEXT NOT NULL,
            closes_at TEXT NOT NULL,
            forced_closes_at TEXT NOT NULL,
            effective_closes_at TEXT NOT NULL,
            service_date TEXT NOT NULL,
            trigger_minutes INTEGER NOT NULL,
            extension_minutes INTEGER NOT NULL,
            triggers TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
            supplier TEXT NOT NULL,
            freight REAL NOT NULL,
            origin REAL NOT NULL,
            destination REAL NOT NULL,
            transit_days INTEGER NOT NULL,
            valid_until TEXT NOT NULL,
            total REAL NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(auction_id, supplier)
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        """)


app = FastAPI(title="British Auction RFQ API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


class AuctionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    reference_id: str = Field(min_length=2, max_length=40)
    starts_at: str
    closes_at: str
    forced_closes_at: str
    service_date: str
    trigger_minutes: int = Field(ge=1, le=180)
    extension_minutes: int = Field(ge=1, le=60)
    triggers: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_schedule(self):
        start, close, forced = map(parse_time, (self.starts_at, self.closes_at, self.forced_closes_at))
        if not start < close < forced:
            raise ValueError("Start time must be before bid close, and forced close must be later than bid close")
        if len(set(self.triggers)) != len(self.triggers) or any(t not in TRIGGERS for t in self.triggers):
            raise ValueError("Select one or more valid extension triggers")
        return self


class BidCreate(BaseModel):
    supplier: str = Field(min_length=2, max_length=100)
    freight: float = Field(ge=0)
    origin: float = Field(ge=0)
    destination: float = Field(ge=0)
    transit_days: int = Field(ge=0, le=365)
    valid_until: str


def auction_status(row: sqlite3.Row, now: datetime | None = None) -> str:
    now = now or now_utc()
    if now < parse_time(row["starts_at"]):
        return "scheduled"
    if now < parse_time(row["effective_closes_at"]):
        return "active"
    if parse_time(row["effective_closes_at"]) >= parse_time(row["forced_closes_at"]):
        return "force_closed"
    return "closed"


def auction_summary(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    lowest = db.execute("SELECT MIN(total) FROM bids WHERE auction_id=?", (row["id"],)).fetchone()[0]
    result = dict(row)
    result["triggers"] = json.loads(result["triggers"])
    result["current_lowest_bid"] = lowest
    result["status"] = auction_status(row)
    return result


@app.get("/api/auctions")
def list_auctions():
    with connect() as db:
        rows = db.execute("SELECT * FROM auctions ORDER BY created_at DESC").fetchall()
        return [auction_summary(db, row) for row in rows]


@app.post("/api/auctions", status_code=201)
def create_auction(payload: AuctionCreate):
    with connect() as db:
        try:
            cursor = db.execute("""INSERT INTO auctions
                (name, reference_id, starts_at, closes_at, forced_closes_at, effective_closes_at,
                 service_date, trigger_minutes, extension_minutes, triggers, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload.name.strip(), payload.reference_id.strip(), payload.starts_at, payload.closes_at,
                 payload.forced_closes_at, payload.closes_at, payload.service_date, payload.trigger_minutes,
                 payload.extension_minutes, json.dumps(payload.triggers), now_utc().isoformat()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "That RFQ reference ID already exists") from exc
        row = db.execute("SELECT * FROM auctions WHERE id=?", (cursor.lastrowid,)).fetchone()
        return auction_summary(db, row)


@app.get("/api/auctions/{auction_id}")
def get_auction(auction_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM auctions WHERE id=?", (auction_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Auction not found")
        bids = db.execute("SELECT * FROM bids WHERE auction_id=? ORDER BY total, submitted_at", (auction_id,)).fetchall()
        ranked = [dict(bid) | {"rank": f"L{i + 1}"} for i, bid in enumerate(bids)]
        activity = db.execute("SELECT * FROM activity WHERE auction_id=? ORDER BY occurred_at DESC", (auction_id,)).fetchall()
        return auction_summary(db, row) | {"bids": ranked, "activity": [dict(item) for item in activity]}


@app.post("/api/auctions/{auction_id}/bids", status_code=201)
def submit_bid(auction_id: int, payload: BidCreate):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        auction = db.execute("SELECT * FROM auctions WHERE id=?", (auction_id,)).fetchone()
        if not auction:
            raise HTTPException(404, "Auction not found")
        current = now_utc()
        if current < parse_time(auction["starts_at"]):
            raise HTTPException(409, "Bidding has not started")
        if auction_status(auction, current) != "active":
            raise HTTPException(409, "This auction is closed")
        total = round(payload.freight + payload.origin + payload.destination, 2)
        previous = db.execute("SELECT * FROM bids WHERE auction_id=? AND supplier=?", (auction_id, payload.supplier.strip())).fetchone()
        old_ranks = {row["supplier"]: i for i, row in enumerate(db.execute(
            "SELECT supplier FROM bids WHERE auction_id=? ORDER BY total, submitted_at", (auction_id,)).fetchall())}
        old_l1 = next(iter(old_ranks), None)
        if previous and total >= previous["total"]:
            raise HTTPException(422, "A replacement bid must be lower than your previous bid")
        at = current.isoformat()
        db.execute("""INSERT INTO bids (auction_id, supplier, freight, origin, destination, transit_days, valid_until, total, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(auction_id, supplier) DO UPDATE SET freight=excluded.freight, origin=excluded.origin,
            destination=excluded.destination, transit_days=excluded.transit_days, valid_until=excluded.valid_until,
            total=excluded.total, submitted_at=excluded.submitted_at""",
            (auction_id, payload.supplier.strip(), payload.freight, payload.origin, payload.destination,
             payload.transit_days, payload.valid_until, total, at))
        db.execute("INSERT INTO activity (auction_id, kind, message, occurred_at) VALUES (?, 'bid', ?, ?)",
                   (auction_id, f"{payload.supplier.strip()} submitted a bid of {total:.2f}", at))
        new_ranks = {row["supplier"]: i for i, row in enumerate(db.execute(
            "SELECT supplier FROM bids WHERE auction_id=? ORDER BY total, submitted_at", (auction_id,)).fetchall())}
        new_l1 = next(iter(new_ranks), None)
        triggers = set(json.loads(auction["triggers"]))
        close = parse_time(auction["effective_closes_at"])
        forced = parse_time(auction["forced_closes_at"])
        in_window = (close - current).total_seconds() <= auction["trigger_minutes"] * 60
        reasons = []
        if in_window:
            if "bid_received" in triggers:
                reasons.append("bid received in trigger window")
            if "any_rank_change" in triggers and old_ranks != new_ranks:
                reasons.append("supplier ranking changed in trigger window")
            if "l1_change" in triggers and old_l1 != new_l1:
                reasons.append("lowest bidder changed in trigger window")
        if reasons:
            next_close = min(close.timestamp() + auction["extension_minutes"] * 60, forced.timestamp())
            if next_close > close.timestamp():
                updated = datetime.fromtimestamp(next_close, timezone.utc)
                db.execute("UPDATE auctions SET effective_closes_at=? WHERE id=?", (updated.isoformat(), auction_id))
                db.execute("INSERT INTO activity (auction_id, kind, message, occurred_at) VALUES (?, 'extension', ?, ?)",
                           (auction_id, f"Close extended to {updated.isoformat()} because " + "; ".join(reasons), at))
        bid = db.execute("SELECT * FROM bids WHERE auction_id=? AND supplier=?", (auction_id, payload.supplier.strip())).fetchone()
        return dict(bid)


@app.get("/api/health")
def health():
    return {"status": "ok"}
