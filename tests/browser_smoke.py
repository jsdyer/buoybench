"""Exercise the built starter at a project subpath in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    screenshots = ROOT / "browser-checks"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT / "dist", Path(temporary) / "example-tool")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temporary))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/example-tool/")
                page.get_by_role("heading", name="Halibut Bank", exact=True).wait_for()
                assert page.locator("#metrics .metric-card").count() == 4
                page.locator("#station").select_option("4400258")
                assert page.locator("#station-name").inner_text() == "Halifax Harbour"
                page.locator("#metric").select_option("waterC")
                assert page.locator("#chart svg").count() == 1
                assert "forecast" in page.locator("#forecast-text").inner_text().lower() or page.locator("#forecast-text h3").count() == 1
                with page.expect_download() as download:
                    page.locator("#save").click()
                assert download.value.suggested_filename == "buoybench-receipt.json"
                page.locator("#station").select_option("4600146")
                page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            print("Browser checks passed: buoy comparison, metric selection, receipt download and mobile layout")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
