"""Tests for bailey. Run: python -m unittest discover tests -v"""
import unittest
from unittest.mock import patch

from bailey._http import AuthError, ConflictError, NotFoundError, _extract_message
from bailey.confluence import Confluence, _TextExtractor
from bailey.jira import Jira


class TestConfluenceConstruction(unittest.TestCase):
    def test_cloud_url_gets_wiki_suffix(self):
        c = Confluence("https://acme.atlassian.net", bearer="t")
        self.assertEqual(c.api, "https://acme.atlassian.net/wiki/rest/api")

    def test_cloud_url_with_wiki_untouched(self):
        c = Confluence("https://acme.atlassian.net/wiki/", bearer="t")
        self.assertEqual(c.api, "https://acme.atlassian.net/wiki/rest/api")

    def test_datacenter_url_untouched(self):
        c = Confluence("https://confluence.corp.example.com", bearer="t")
        self.assertEqual(c.api, "https://confluence.corp.example.com/rest/api")

    def test_from_env_cloud_uses_basic(self):
        env = {"BAILEY_CONFLUENCE_URL": "https://acme.atlassian.net",
               "BAILEY_CONFLUENCE_TOKEN": "tok",
               "BAILEY_CONFLUENCE_EMAIL": "me@example.com"}
        c = Confluence.from_env(env)
        self.assertEqual(c._auth["basic"], ("me@example.com", "tok"))
        self.assertIsNone(c._auth["bearer"])

    def test_from_env_datacenter_uses_bearer(self):
        env = {"BAILEY_CONFLUENCE_URL": "https://confluence.corp.example.com",
               "BAILEY_CONFLUENCE_TOKEN": "pat"}
        c = Confluence.from_env(env)
        self.assertEqual(c._auth["bearer"], "pat")

    def test_missing_env_raises_auth_error(self):
        with self.assertRaises(AuthError):
            Confluence.from_env({})


class TestOptimisticConcurrency(unittest.TestCase):
    def setUp(self):
        self.client = Confluence("https://acme.atlassian.net", bearer="t")
        self.live_page = {
            "id": "123", "title": "Runbook",
            "version": {"number": 7},
            "body": {"storage": {"value": "<p>old</p>"}},
        }

    @patch("bailey.confluence._http.request")
    def test_version_conflict_raises_exit5(self, mock_req):
        mock_req.return_value = self.live_page
        with self.assertRaises(ConflictError) as ctx:
            self.client.update_page("123", storage_body="<p>new</p>",
                                    expect_version=5)
        self.assertEqual(ctx.exception.exit_code, 5)

    @patch("bailey.confluence._http.request")
    def test_matching_version_bumps_and_puts(self, mock_req):
        sent = {}

        def side_effect(method, url, **kw):
            if method == "GET":
                return self.live_page
            sent["method"], sent["url"] = method, url
            sent["payload"] = kw.get("json_body")
            return {"id": "123", "version": {"number": 8}}

        mock_req.side_effect = side_effect
        self.client.update_page("123", storage_body="<p>new</p>",
                                expect_version=7, message="agent edit")
        self.assertEqual(sent["method"], "PUT")
        self.assertEqual(sent["payload"]["version"]["number"], 8)
        self.assertEqual(sent["payload"]["version"]["message"], "agent edit")
        self.assertEqual(
            sent["payload"]["body"]["storage"]["value"], "<p>new</p>")

    @patch("bailey.confluence._http.request")
    def test_dry_run_never_puts(self, mock_req):
        mock_req.return_value = self.live_page
        result = self.client.update_page("123", storage_body="<p>new</p>",
                                         dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["live_version"], 7)
        # only the GET happened
        self.assertEqual(mock_req.call_count, 1)


class TestTextExtraction(unittest.TestCase):
    def test_storage_to_text(self):
        ex = _TextExtractor()
        ex.feed("<h1>Title</h1><p>Line one</p><ul><li>a</li><li>b</li></ul>")
        self.assertEqual(ex.text(), "Title\nLine one\na\nb")


class TestJira(unittest.TestCase):
    def test_from_env_cloud_basic(self):
        env = {"BAILEY_JIRA_URL": "https://acme.atlassian.net",
               "BAILEY_JIRA_TOKEN": "tok", "BAILEY_JIRA_EMAIL": "me@x.com"}
        j = Jira.from_env(env)
        self.assertEqual(j.api, "https://acme.atlassian.net/rest/api/2")
        self.assertEqual(j._auth["basic"], ("me@x.com", "tok"))

    @patch("bailey.jira._http.request")
    def test_comment_dry_run_makes_no_request(self, mock_req):
        j = Jira("https://acme.atlassian.net", bearer="t")
        result = j.add_comment("OPS-1", "hello", dry_run=True)
        self.assertTrue(result["dry_run"])
        mock_req.assert_not_called()


class TestErrorParsing(unittest.TestCase):
    def test_extracts_message_key(self):
        self.assertEqual(_extract_message('{"message": "no permission"}'),
                         "no permission")

    def test_extracts_jira_error_messages(self):
        self.assertEqual(
            _extract_message('{"errorMessages": ["bad jql", "field x"]}'),
            "bad jql; field x")

    def test_garbage_body_is_safe(self):
        self.assertEqual(_extract_message("<html>nope</html>"), "")


if __name__ == "__main__":
    unittest.main()


class TestSslContext(unittest.TestCase):
    def test_default_context_without_env(self):
        import bailey._http as h
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("BAILEY_CA_BUNDLE", None)
            ctx = h._ssl_context()
        import ssl
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_missing_ca_bundle_raises_clean_auth_error(self):
        import bailey._http as h
        with patch.dict("os.environ", {"BAILEY_CA_BUNDLE": "/nope/missing.pem"}):
            with self.assertRaises(AuthError):
                h._ssl_context()
