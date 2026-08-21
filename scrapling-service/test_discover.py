"""Service-local regression tests for Scrapling's BFS URL discovery."""

import unittest
from unittest.mock import patch

import main


class DiscoverLinksTests(unittest.IsolatedAsyncioTestCase):
    async def call_discover(self, fetch, *, max_depth=2, max_pages=10):
        request = main.DiscoverRequest(
            url="https://example.com/",
            max_depth=max_depth,
            max_pages=max_pages,
        )
        with patch.object(main, "_fetch_with_fallback", side_effect=fetch):
            return await main.discover_links(request)

    async def test_discovers_multiple_depths_and_filters_external_urls(self):
        pages = {
            "https://example.com/": (
                '<a href="/about">About</a>'
                '<a href="/products">Products</a>'
                '<a href="https://other.example/out">External</a>'
            ),
            "https://example.com/about": "<p>About</p>",
            "https://example.com/products": (
                '<a href="/products/item1">Item 1</a>'
                '<a href="/products/item2">Item 2</a>'
            ),
            "https://example.com/products/item1": "<p>Item 1</p>",
            "https://example.com/products/item2": "<p>Item 2</p>",
        }

        def fetch(url, _timeout):
            return pages.get(url, ""), 200, url, "text/html"

        response = await self.call_discover(fetch)
        urls = response.urls
        discovered = {item["url"] for item in urls}

        self.assertIn("https://example.com/", discovered)
        self.assertIn("https://example.com/products/item1", discovered)
        self.assertEqual({item["depth"] for item in urls}, {0, 1, 2})
        self.assertFalse(any("other.example" in url for url in discovered))

    async def test_respects_max_depth(self):
        def fetch(url, _timeout):
            if url == "https://example.com/":
                return '<a href="/page1">Page 1</a>', 200, url, "text/html"
            if url == "https://example.com/page1":
                return '<a href="/page2">Page 2</a>', 200, url, "text/html"
            return "<p>Done</p>", 200, url, "text/html"

        depth_one = await self.call_discover(fetch, max_depth=1)
        self.assertTrue(all(item["depth"] <= 1 for item in depth_one.urls))

        depth_two = await self.call_discover(fetch, max_depth=2)
        self.assertIn(2, {item["depth"] for item in depth_two.urls})

    async def test_respects_max_pages(self):
        def fetch(url, _timeout):
            links = "".join(
                f'<a href="/page{index}">Page {index}</a>'
                for index in range(1, 20)
            )
            return links, 200, url, "text/html"

        response = await self.call_discover(fetch, max_pages=5)
        self.assertEqual(len(response.urls), 5)

    async def test_avoids_cycles(self):
        def fetch(url, _timeout):
            if url == "https://example.com/":
                return '<a href="/b">B</a>', 200, url, "text/html"
            if url == "https://example.com/b":
                return (
                    '<a href="/">A</a><a href="/c">C</a>',
                    200,
                    url,
                    "text/html",
                )
            return "<p>Done</p>", 200, url, "text/html"

        response = await self.call_discover(fetch, max_depth=3)
        discovered = [item["url"] for item in response.urls]

        self.assertEqual(len(discovered), len(set(discovered)))
        self.assertEqual(
            set(discovered),
            {"https://example.com/", "https://example.com/b", "https://example.com/c"},
        )


if __name__ == "__main__":
    unittest.main()
