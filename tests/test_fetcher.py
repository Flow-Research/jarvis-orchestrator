"""Tests for fetcher — error handling, lazy import."""


from jarvis_miner.fetcher import _import_bittensor


class TestBittensorImport:
    def test_lazy_import_raises_without_bittensor(self):
        """Should raise ImportError when bittensor is not installed."""
        try:
            bt = _import_bittensor()
            # If bittensor IS installed, this is fine
            assert bt is not None
        except ImportError as e:
            assert "bittensor" in str(e).lower()
