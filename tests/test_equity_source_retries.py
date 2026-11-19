import json
import urllib.error
import unittest
from unittest.mock import Mock

from equity_lab import source, universe


class _Reply:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"chart":{"result":[]}}'


def rate_limited(url):
    return urllib.error.HTTPError(url, 429, "rate limited", None, None)


class YahooRetryTests(unittest.TestCase):
    def test_rotates_hosts_and_escalates_between_retry_rounds(self):
        calls = []
        def getter(request, timeout):
            calls.append(request.full_url)
            if len(calls) <= 2:
                raise rate_limited(request.full_url)
            return _Reply()
        sleeper = Mock()
        result = source.request(universe.NASDAQ[0], getter=getter, sleeper=sleeper)
        self.assertEqual(result, {"chart": {"result": []}})
        self.assertIn("query1.finance.yahoo.com", calls[0])
        self.assertIn("query2.finance.yahoo.com", calls[1])
        self.assertIn("query1.finance.yahoo.com", calls[2])
        sleeper.assert_called_once_with(0.5)

    def test_exhausted_retries_report_source_unavailable(self):
        calls = []
        def getter(request, timeout):
            calls.append(request.full_url)
            raise rate_limited(request.full_url)
        sleeper = Mock()
        with self.assertRaisesRegex(RuntimeError, "SOURCE_UNAVAILABLE"):
            source.request(universe.NASDAQ[0], getter=getter, sleeper=sleeper)
        self.assertEqual(len(calls), 6)
        self.assertEqual([x.args[0] for x in sleeper.call_args_list], [0.5, 1.5])

    def test_non_retryable_http_error_fails_immediately(self):
        calls = []
        def getter(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 404, "not found", None, None)
        sleeper = Mock()
        with self.assertRaises(urllib.error.HTTPError):
            source.request(universe.NASDAQ[0], getter=getter, sleeper=sleeper)
        self.assertEqual(len(calls), 1)
        sleeper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
