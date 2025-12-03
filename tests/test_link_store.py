from __future__ import annotations

from src.storage.link_store import LinkStore


def test_link_store_dedup_and_requeue(tmp_path) -> None:
    db_path = tmp_path / "links.db"
    store = LinkStore(db_path)
    try:
        # Insert two unique URLs.
        added = store.add_links(
            [
                "https://1000.menu/cooking/1",
                "https://1000.menu/cooking/2",
                "https://1000.menu/cooking/1",
            ]
        )
        assert added >= 2

        leased = store.lease_batch(limit=5, lease_seconds=0)
        assert set(leased) == {
            "https://1000.menu/cooking/1",
            "https://1000.menu/cooking/2",
        }

        store.ack_success("https://1000.menu/cooking/1")
        assert store.already_parsed("https://1000.menu/cooking/1")

        store.ack_fail("https://1000.menu/cooking/2", "boom", max_attempts=2)
        leased_again = store.lease_batch(limit=1, lease_seconds=0)
        assert leased_again == ["https://1000.menu/cooking/2"]

        store.ack_fail("https://1000.menu/cooking/2", "boom", max_attempts=2)
        # The URL is now failed; leasing returns nothing.
        assert store.lease_batch(limit=1, lease_seconds=0) == []

        # Adding the failed URL again should resurrect it.
        store.add_links(["https://1000.menu/cooking/2"])
        resurrected = store.lease_batch(limit=1, lease_seconds=0)
        assert resurrected == ["https://1000.menu/cooking/2"]
    finally:
        store.close()

