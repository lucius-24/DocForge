import os
import unittest
import xml.etree.ElementTree as ET

from fastapi.responses import FileResponse, RedirectResponse

from webapp.backend import server


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


class SvgBrandAssetTests(unittest.TestCase):
    def test_svg_files_are_safe_standalone_vectors(self):
        for filename in ("logo.svg", "favicon.svg"):
            path = os.path.join(ROOT_DIR, filename)
            tree = ET.parse(path)
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("svg"))
            self.assertIn("viewBox", root.attrib)

            with open(path, encoding="utf-8") as svg_file:
                text = svg_file.read().lower()
            self.assertNotIn("<script", text)
            self.assertNotIn("<image", text)
            self.assertNotRegex(text, r"""(?:href|src)\s*=\s*["']https?://""")
            self.assertNotRegex(text, r"\son[a-z]+\s*=")

    def test_frontend_uses_svg_brand_assets_and_online_title(self):
        path = os.path.join(ROOT_DIR, "webapp", "frontend", "index.html")
        with open(path, encoding="utf-8") as html_file:
            html = html_file.read()
        self.assertIn(
            "<title>DocForge | 专为 AI 时代打造的 Markdown 锻造引擎</title>",
            html,
        )
        self.assertIn('href="/favicon.svg?v=2"', html)
        self.assertIn('href="/logo.svg?v=2"', html)
        self.assertIn('src="/logo.svg"', html)
        self.assertNotIn("/logo.png", html)
        self.assertNotIn("beian.miit.gov.cn", html)
        self.assertNotIn("陕ICP备", html)

    def test_backend_serves_svg_and_redirects_legacy_urls(self):
        logo = server.logo_svg()
        favicon = server.favicon_svg()
        old_logo = server.logo_png()
        old_favicon = server.favicon()

        self.assertIsInstance(logo, FileResponse)
        self.assertEqual(logo.media_type, "image/svg+xml")
        self.assertIsInstance(favicon, FileResponse)
        self.assertEqual(favicon.media_type, "image/svg+xml")
        self.assertIsInstance(old_logo, RedirectResponse)
        self.assertEqual(old_logo.headers["location"], "/logo.svg")
        self.assertIsInstance(old_favicon, RedirectResponse)
        self.assertEqual(old_favicon.headers["location"], "/favicon.svg")


if __name__ == "__main__":
    unittest.main()
