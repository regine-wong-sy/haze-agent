import unittest

from reliability import TTLCache, CircuitBreaker


class TTLCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.cache = TTLCache(ttl=10, max_stale=100, clock=lambda: self.now)

    def test_missing_key(self):
        self.assertIsNone(self.cache.get_fresh("a"))
        self.assertIsNone(self.cache.get_stale("a"))

    def test_fresh_then_stale_then_gone(self):
        self.cache.put("a", 1)
        self.now = 10
        self.assertEqual(self.cache.get_fresh("a"), 1)
        self.now = 11
        self.assertIsNone(self.cache.get_fresh("a"))
        self.assertEqual(self.cache.get_stale("a"), 1)
        self.now = 101
        self.assertIsNone(self.cache.get_stale("a"))

    def test_put_again_refreshes(self):
        self.cache.put("a", 1)
        self.now = 50
        self.cache.put("a", 2)
        self.assertEqual(self.cache.get_fresh("a"), 2)

    def test_falsy_values_are_still_cached(self):
        self.cache.put("a", 0)
        self.assertEqual(self.cache.get_fresh("a"), 0)


class CircuitBreakerTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.breaker = CircuitBreaker(failures=2, cooldown=60, clock=lambda: self.now)

    def test_starts_closed(self):
        self.assertTrue(self.breaker.allow())
        self.assertEqual(self.breaker.state, "closed")

    def test_opens_after_the_failure_limit(self):
        self.breaker.failure()
        self.assertTrue(self.breaker.allow())
        self.breaker.failure()
        self.assertFalse(self.breaker.allow())
        self.assertEqual(self.breaker.state, "open")

    def test_a_success_resets_the_count(self):
        self.breaker.failure()
        self.breaker.success()
        self.breaker.failure()
        self.assertTrue(self.breaker.allow())

    def test_lets_a_test_call_through_after_the_cooldown(self):
        self.breaker.failure()
        self.breaker.failure()
        self.now = 59
        self.assertFalse(self.breaker.allow())
        self.now = 60
        self.assertTrue(self.breaker.allow())

    def test_failed_test_call_reopens_for_another_cooldown(self):
        self.breaker.failure()
        self.breaker.failure()
        self.now = 60
        self.breaker.failure()
        self.assertFalse(self.breaker.allow())
        self.now = 119
        self.assertFalse(self.breaker.allow())
        self.now = 120
        self.assertTrue(self.breaker.allow())

    def test_successful_test_call_closes_it(self):
        self.breaker.failure()
        self.breaker.failure()
        self.now = 60
        self.breaker.success()
        self.assertEqual(self.breaker.state, "closed")
        self.breaker.failure()
        self.assertTrue(self.breaker.allow())


if __name__ == "__main__":
    unittest.main()
