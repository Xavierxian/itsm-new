from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from monitoring import services


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "monitoring-tests-cache",
        }
    },
    MONITORING_HOST_SNAPSHOT_CACHE_SECONDS=30,
)
class HostSnapshotCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    @staticmethod
    def _query_payload(value: str = "1"):
        return {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"instance": "10.0.0.1:9100"},
                        "value": [1710000000, value],
                    }
                ]
            },
        }

    def test_fetch_host_snapshot_reuses_cache_for_consecutive_calls(self):
        expected_query_calls = len(services.SNAPSHOT_METRICS)

        with (
            patch("monitoring.services.PrometheusClient.query", return_value=self._query_payload()) as query_mock,
            patch("monitoring.services._enrich_host_metadata", return_value=None),
        ):
            first = services.fetch_host_snapshot()
            second = services.fetch_host_snapshot()

        self.assertTrue(first.get("hosts"))
        self.assertEqual(first, second)
        self.assertEqual(query_mock.call_count, expected_query_calls)

    def test_fetch_host_snapshot_force_refresh_bypasses_cache(self):
        expected_query_calls = len(services.SNAPSHOT_METRICS) * 2

        with (
            patch("monitoring.services.PrometheusClient.query", return_value=self._query_payload()) as query_mock,
            patch("monitoring.services._enrich_host_metadata", return_value=None),
        ):
            services.fetch_host_snapshot()
            services.fetch_host_snapshot(force_refresh=True)

        self.assertEqual(query_mock.call_count, expected_query_calls)
