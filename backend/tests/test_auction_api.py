import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import main


class AuctionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test-auctions.db"
        self.db_path_patch = patch.object(main, "DB_PATH", self.database)
        self.db_path_patch.start()
        main.init_db()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def create_auction(self, *, trigger_minutes=5, forced_offset=2):
        return main.create_auction(
            main.AuctionCreate(
                name="Northbound freight",
                reference_id="RFQ-TEST-1",
                starts_at=self.now - timedelta(minutes=1),
                closes_at=self.now + timedelta(minutes=1),
                forced_closes_at=self.now + timedelta(minutes=forced_offset),
                service_date=date.today(),
                trigger_minutes=trigger_minutes,
                extension_minutes=5,
                triggers=["bid_received", "any_rank_change", "l1_change"],
            )
        )

    def submit(self, auction_id, supplier="Carrier A", total=100):
        return main.submit_bid(
            auction_id,
            main.BidCreate(
                supplier=supplier,
                freight=total - 10,
                origin=5,
                destination=5,
                transit_days=12,
                valid_until=date.today() + timedelta(days=30),
            ),
        )

    def test_creation_starts_with_bid_close_as_effective_close(self):
        auction = self.create_auction()

        self.assertEqual(auction["status"], "active")
        self.assertEqual(auction["closes_at"], auction["effective_closes_at"])
        self.assertEqual(auction["triggers"], ["bid_received", "any_rank_change", "l1_change"])

    def test_bid_is_ranked_and_extension_stops_at_forced_close(self):
        auction = self.create_auction(forced_offset=2)

        bid = self.submit(auction["id"])
        detail = main.get_auction(auction["id"])

        self.assertEqual(bid["total"], 100)
        self.assertEqual(detail["bids"][0]["rank"], "L1")
        self.assertEqual(detail["effective_closes_at"], detail["forced_closes_at"])
        self.assertTrue(any(event["kind"] == "extension" for event in detail["activity"]))

    def test_supplier_must_lower_their_replacement_bid(self):
        auction = self.create_auction()
        self.submit(auction["id"], total=100)

        with self.assertRaises(HTTPException) as raised:
            self.submit(auction["id"], total=100)

        self.assertEqual(raised.exception.status_code, 422)

    def test_bid_outside_trigger_window_does_not_extend_close(self):
        auction = main.create_auction(
            main.AuctionCreate(
                name="Northbound freight",
                reference_id="RFQ-TEST-2",
                starts_at=self.now - timedelta(minutes=1),
                closes_at=self.now + timedelta(hours=1),
                forced_closes_at=self.now + timedelta(hours=2),
                service_date=date.today(),
                trigger_minutes=1,
                extension_minutes=5,
                triggers=["bid_received"],
            )
        )

        self.submit(auction["id"])
        detail = main.get_auction(auction["id"])

        self.assertEqual(detail["effective_closes_at"], detail["closes_at"])
        self.assertFalse(any(event["kind"] == "extension" for event in detail["activity"]))

    def test_schedule_requires_timezone_and_forced_close_after_bid_close(self):
        with self.assertRaises(ValidationError):
            main.AuctionCreate(
                name="Invalid schedule",
                reference_id="RFQ-TEST-3",
                starts_at="2030-01-01T10:00:00",
                closes_at="2030-01-01T11:00:00Z",
                forced_closes_at="2030-01-01T12:00:00Z",
                service_date=date.today(),
                trigger_minutes=5,
                extension_minutes=5,
                triggers=["bid_received"],
            )

        with self.assertRaises(ValidationError):
            main.AuctionCreate(
                name="Invalid schedule",
                reference_id="RFQ-TEST-4",
                starts_at="2030-01-01T10:00:00Z",
                closes_at="2030-01-01T12:00:00Z",
                forced_closes_at="2030-01-01T11:00:00Z",
                service_date=date.today(),
                trigger_minutes=5,
                extension_minutes=5,
                triggers=["bid_received"],
            )


if __name__ == "__main__":
    unittest.main()
