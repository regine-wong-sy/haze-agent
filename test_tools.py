import os
os.environ["USE_EMBEDDINGS"] = "0"  #skip loading the embedding model, these tests don't need it

import time
import unittest
from unittest.mock import patch

import tools

#what data.gov.sg returns, cut down to the part get_psi_direct reads
DATA_GOV_REPLY = {"data": {"items": [{"readings": {"psi_twenty_four_hourly": {
    "north": 73, "south": 66, "west": 78, "east": 73, "central": 78}}}]}}


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


def fake_get(haze_response=None, haze_error=None, gov_response=None, gov_error=None):
    """Stand-in for requests.get: answers Haze-API and data.gov.sg separately."""
    def get(url, **kwargs):
        if url == tools.HAZE_API:
            if haze_error:
                raise haze_error
            return haze_response
        if url == tools.DATA_GOV_PSI:
            if gov_error:
                raise gov_error
            return gov_response
        raise AssertionError(f"unexpected url {url}")
    return get


class PsiLevelTest(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(tools.psi_level(50), "Good")
        self.assertEqual(tools.psi_level(51), "Moderate")
        self.assertEqual(tools.psi_level(100), "Moderate")
        self.assertEqual(tools.psi_level(101), "Unhealthy")
        self.assertEqual(tools.psi_level(200), "Unhealthy")
        self.assertEqual(tools.psi_level(201), "Very Unhealthy")
        self.assertEqual(tools.psi_level(300), "Very Unhealthy")
        self.assertEqual(tools.psi_level(301), "Hazardous")


class GetPsiTest(unittest.TestCase):
    def setUp(self):
        #the cache and breaker are module-level, so every test starts from a clean slate
        tools.reset_psi_state()
        self.now = [0.0]
        tools.psi_cache.clock = lambda: self.now[0]
        patcher = patch.object(tools, "GOV_RETRY_DELAY", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, tools.psi_cache, "clock", time.monotonic)

    def test_uses_haze_api_when_it_works(self):
        haze = {"region": "east", "psi": 80, "level": "Moderate"}
        get = fake_get(haze_response=FakeResponse(200, haze),
                       gov_error=AssertionError("fallback should not be called"))
        with patch("tools.requests.get", get):
            self.assertEqual(tools.get_psi("bedok"), haze)

    def test_falls_back_when_haze_api_is_unreachable(self):
        get = fake_get(haze_error=ConnectionError("down"), gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            result = tools.get_psi("east")
        self.assertEqual(result, {"region": "east", "psi": 73, "level": "Moderate"})

    def test_falls_back_when_haze_api_returns_an_error_status(self):
        get = fake_get(haze_response=FakeResponse(500, {"error": "boom"}),
                       gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            self.assertEqual(tools.get_psi("west")["psi"], 78)

    def test_area_name_maps_to_its_region_in_the_fallback(self):
        get = fake_get(haze_error=ConnectionError("down"), gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            self.assertEqual(tools.get_psi("Bedok")["region"], "east")
            self.assertEqual(tools.get_psi("jurong")["region"], "west")
            self.assertEqual(tools.get_psi("punggol")["region"], "north")

    def test_unknown_region_gives_an_error_not_a_crash(self):
        get = fake_get(haze_error=ConnectionError("down"), gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            result = tools.get_psi("narnia")
        self.assertIn("error", result)
        self.assertNotIn("psi", result)

    def test_error_names_both_sources_when_both_fail(self):
        get = fake_get(haze_error=ConnectionError("haze down"), gov_error=TimeoutError("gov down"))
        with patch("tools.requests.get", get):
            result = tools.get_psi("east")
        self.assertIn("haze down", result["error"])
        self.assertIn("gov down", result["error"])

    def test_fallback_result_has_the_same_keys_as_haze_api(self):
        #an extra key (e.g. "source") once made the model leak its reasoning into the answer
        get = fake_get(haze_error=ConnectionError("down"), gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            self.assertEqual(set(tools.get_psi("east")), {"region", "psi", "level"})

    def test_second_call_is_served_from_cache(self):
        calls = []
        haze = {"region": "east", "psi": 80, "level": "Moderate"}
        def get(url, **kwargs):
            calls.append(url)
            return FakeResponse(200, haze)
        with patch("tools.requests.get", get):
            tools.get_psi("east")
            self.now[0] += tools.PSI_CACHE_TTL - 1
            self.assertEqual(tools.get_psi(" East "), haze)  #same region, different spelling
        self.assertEqual(len(calls), 1)

    def test_cache_expires_after_the_ttl(self):
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            return FakeResponse(200, {"region": "east", "psi": 80, "level": "Moderate"})
        with patch("tools.requests.get", get):
            tools.get_psi("east")
            self.now[0] += tools.PSI_CACHE_TTL + 1
            tools.get_psi("east")
        self.assertEqual(len(calls), 2)

    def test_errors_are_not_cached(self):
        get = fake_get(haze_error=ConnectionError("down"), gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            self.assertIn("error", tools.get_psi("narnia"))
        self.assertIsNone(tools.psi_cache.get_stale("narnia"))

    def test_old_reading_is_used_only_when_both_sources_are_down(self):
        haze = {"region": "east", "psi": 80, "level": "Moderate"}
        with patch("tools.requests.get", fake_get(haze_response=FakeResponse(200, haze))):
            tools.get_psi("east")
        self.now[0] += tools.PSI_CACHE_TTL + 1  #too old to be fresh, not too old to be a last resort
        down = fake_get(haze_error=ConnectionError("down"), gov_error=TimeoutError("down"))
        with patch("tools.requests.get", down):
            self.assertEqual(tools.get_psi("east"), haze)

    def test_reading_older_than_max_stale_is_not_used(self):
        haze = {"region": "east", "psi": 80, "level": "Moderate"}
        with patch("tools.requests.get", fake_get(haze_response=FakeResponse(200, haze))):
            tools.get_psi("east")
        self.now[0] += tools.PSI_MAX_STALE + 1
        down = fake_get(haze_error=ConnectionError("down"), gov_error=TimeoutError("down"))
        with patch("tools.requests.get", down):
            self.assertIn("error", tools.get_psi("east"))

    def test_haze_api_is_skipped_after_repeated_failures(self):
        haze_calls = []
        def get(url, **kwargs):
            if url == tools.HAZE_API:
                haze_calls.append(url)
                raise ConnectionError("down")
            return FakeResponse(200, DATA_GOV_REPLY)
        with patch("tools.requests.get", get):
            for region in ["north", "south", "east", "west"]:  #different regions so the cache can't answer
                self.assertIn("psi", tools.get_psi(region))
        self.assertEqual(len(haze_calls), 2)

    def test_haze_api_is_tried_again_after_the_cooldown(self):
        haze_calls = []
        def get(url, **kwargs):
            if url == tools.HAZE_API:
                haze_calls.append(url)
                raise ConnectionError("down")
            return FakeResponse(200, DATA_GOV_REPLY)
        clock = [0.0]
        with patch.object(tools.haze_breaker, "clock", lambda: clock[0]), patch("tools.requests.get", get):
            for region in ["north", "south", "east"]:
                tools.get_psi(region)
            self.assertEqual(len(haze_calls), 2)
            clock[0] += tools.haze_breaker.cooldown
            tools.get_psi("west")
        self.assertEqual(len(haze_calls), 3)

    def test_unknown_area_reply_does_not_trip_the_breaker(self):
        #a 404 means Haze-API is up but doesn't know the area
        get = fake_get(haze_response=FakeResponse(404, {"error": "unknown area"}),
                       gov_response=FakeResponse(200, DATA_GOV_REPLY))
        with patch("tools.requests.get", get):
            for region in ["a", "b", "c"]:
                tools.get_psi(region)
        self.assertEqual(tools.haze_breaker.state, "closed")

    def test_data_gov_is_retried_once(self):
        attempts = []
        def get(url, **kwargs):
            if url == tools.HAZE_API:
                raise ConnectionError("down")
            attempts.append(url)
            if len(attempts) == 1:
                raise TimeoutError("slow")
            return FakeResponse(200, DATA_GOV_REPLY)
        with patch("tools.requests.get", get):
            self.assertEqual(tools.get_psi("east")["psi"], 73)
        self.assertEqual(len(attempts), 2)

    def test_data_gov_gives_up_after_the_retries(self):
        attempts = []
        def get(url, **kwargs):
            if url == tools.HAZE_API:
                raise ConnectionError("down")
            attempts.append(url)
            raise TimeoutError("slow")
        with patch("tools.requests.get", get):
            self.assertIn("error", tools.get_psi("east"))
        self.assertEqual(len(attempts), tools.GOV_RETRIES)


if __name__ == "__main__":
    unittest.main()


class FakeRules:
    """Stand-in for the Chroma collection: applies the filter's PSI band and group like Chroma would."""
    CHUNKS = [
        ({"min_psi": 101, "max_psi": 200, "source": "NEA", "group": "healthy"}, "healthy advice"),
        ({"min_psi": 101, "max_psi": 200, "source": "NEA", "group": "sensitive"}, "children advice"),
        ({"min_psi": 101, "max_psi": 200, "source": "NEA", "group": "chronic"}, "heart advice"),
        ({"min_psi": 51, "max_psi": 100, "source": "NEA", "group": "healthy"}, "moderate advice"),
        ({"min_psi": 0, "max_psi": 999, "source": "NEA", "group": "all"}, "general advice"),
        ({"min_psi": 0, "max_psi": 999, "source": "MOM", "group": "worker"}, "employer advice"),
    ]

    def get(self, where):
        clauses = where["$and"]
        psi_lo = clauses[0]["min_psi"]["$lte"]
        psi_hi = clauses[1]["max_psi"]["$gte"]
        groups = clauses[2]["group"]["$in"]
        hits = [(m, t) for m, t in self.CHUNKS
                if m["min_psi"] <= psi_lo and m["max_psi"] >= psi_hi and m["group"] in groups]
        return {"documents": [t for _, t in hits], "metadatas": [m for m, _ in hits]}


class SearchAdvisoriesTest(unittest.TestCase):
    def search(self, psi, group):
        with patch("tools.get_rules", lambda: FakeRules()):
            return tools.search_advisories("question", psi, group)

    def texts(self, psi, group):
        return [a["text"] for a in self.search(psi, group)]

    def test_returns_only_the_asked_group_plus_general(self):
        self.assertEqual(self.texts(150, "sensitive"), ["children advice", "general advice"])
        self.assertEqual(self.texts(150, "chronic"), ["heart advice", "general advice"])

    def test_never_mixes_other_groups(self):
        own = {"healthy": "healthy advice", "sensitive": "children advice", "chronic": "heart advice"}
        for group, own_text in own.items():
            others = set(own.values()) - {own_text}
            self.assertFalse(others & set(self.texts(150, group)), group)

    def test_worker_gets_mom_not_health_groups(self):
        self.assertEqual(self.texts(150, "worker"), ["general advice", "employer advice"])

    def test_psi_band_still_applies(self):
        self.assertEqual(self.texts(75, "healthy"), ["moderate advice", "general advice"])

    def test_unknown_group_is_an_error(self):
        self.assertIn("error", self.search(150, "teenagers"))
        self.assertIn("error", self.search(150, ""))


class AdvisoryFilterTest(unittest.TestCase):
    def test_filter_has_band_and_group(self):
        self.assertEqual(tools.advisory_filter(150, "chronic"), {"$and": [
            {"min_psi": {"$lte": 150}}, {"max_psi": {"$gte": 150}},
            {"group": {"$in": ["chronic", "all"]}}]})
