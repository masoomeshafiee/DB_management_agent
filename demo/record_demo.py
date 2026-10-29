"""Run the whole demo in the Streamlit UI and record it as a video.

The backend (uvicorn server:app) and the UI (streamlit run ui/app.py) must be
running. The demo inserts and deletes records, so the database is copied first
and restored afterwards, even if a step fails.

    python demo/record_demo.py          # video saved in demo/videos/

Needs Playwright: pip install playwright && playwright install chromium
"""

import hashlib
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT / "demo"
VIDEO_DIR = DEMO_DIR / "videos"
DB_PATH = PROJECT / "data" / "sample_data.db"
INVALID_ROWS_PATH = PROJECT / "data" / "invalid_rows.csv"
UI_URL = "http://localhost:8501"
SIZE = {"width": 1400, "height": 900}
PAUSE_BETWEEN_REQUESTS = 8  # seconds, to stay under the free-tier rate limit

DELETE_REQUEST = "Remove the raw image files from the second replicate of the November 15th, 2024 experiment."


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def caption(page, text: str) -> None:
    """A banner at the top of the page saying which demo step this is."""
    page.evaluate(
        """text => {
            let el = document.getElementById('demo-caption');
            if (!el) {
                el = document.createElement('div');
                el.id = 'demo-caption';
                el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:999999;' +
                    'background:#1f2937;color:#fff;font:600 20px system-ui;padding:12px 24px;';
                document.body.appendChild(el);
            }
            el.textContent = text;
        }""",
        text,
    )


def messages(page):
    return page.locator('[data-testid="stChatMessage"]')


def wait_for_reply(page, before: int, timeout: float = 300) -> None:
    """Wait until a new assistant message has rendered and no spinner is showing."""
    started = time.time()
    while time.time() - started < timeout:
        spinning = page.get_by_text("Working on it").count() > 0
        if time.time() - started > 3 and not spinning and messages(page).count() >= before + 2:
            time.sleep(1.5)
            messages(page).last.scroll_into_view_if_needed()
            return
        time.sleep(0.5)
    raise TimeoutError("no reply")


def ask(page, text: str) -> str:
    before = messages(page).count()
    chat = page.get_by_placeholder("Enter your database request...")
    chat.click()
    chat.press_sequentially(text, delay=35)
    time.sleep(0.6)
    chat.press("Enter")
    wait_for_reply(page, before)
    reply = messages(page).last.inner_text()
    log(f"Q: {text}\nA: {reply[:400]}")
    return reply


def upload(page, csv_name: str) -> str:
    before = messages(page).count()
    page.locator('[data-testid="stSidebar"] input[type="file"]').set_input_files(str(DEMO_DIR / csv_name))
    time.sleep(2)
    page.get_by_role("button", name="Insert file").click()
    wait_for_reply(page, before)
    reply = messages(page).last.inner_text()
    log(f"UPLOAD {csv_name}\nA: {reply[:600]}")
    return reply


def run_demo(page) -> None:
    page.goto(UI_URL)
    page.get_by_text("Enter a session name in the sidebar to begin.").wait_for(timeout=30000)
    caption(page, "DB Management Agent: plain-English requests to a lab database, no SQL")
    time.sleep(3)
    page.get_by_label("Session name (leave empty for 'default')").fill(f"demo-{int(time.time())}")
    page.get_by_role("button", name="Start / resume session").click()
    page.get_by_placeholder("Enter your database request...").wait_for(timeout=30000)
    time.sleep(2)

    caption(page, "1 · Plain English: 'treatment' means the condition column, no SQL")
    ask(page, "How many experiments do we have for each treatment?")
    time.sleep(6 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "2 · Insert a file with 4 mistakes: validation stops it, nothing inserted")
    upload(page, "02_experiment_with_mistakes.csv")
    time.sleep(8 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "3 · Insert the corrected file: 8 rows")
    upload(page, "01_new_experiment.csv")
    time.sleep(6 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "4 · A written date: 'November 15th, 2024' becomes 20241115")
    ask(page, "What experiments did we run on November 15th, 2024?")
    time.sleep(6 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "5 · Delete in plain words: preview first, then a human decides. Cancel")
    ask(page, DELETE_REQUEST)
    page.get_by_text("Confirm Deletion").last.scroll_into_view_if_needed()
    time.sleep(6)
    page.get_by_role("button", name="Cancel").last.click()
    page.get_by_text("Deletion cancelled").last.wait_for(timeout=120000)
    time.sleep(1)
    messages(page).last.scroll_into_view_if_needed()
    time.sleep(4 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "6 · Same request, approved: exactly the previewed rows are deleted")
    ask(page, DELETE_REQUEST)
    time.sleep(5)
    page.get_by_role("button", name="Delete").last.click()
    page.get_by_text("Deleted").last.wait_for(timeout=120000)
    time.sleep(1)
    messages(page).last.scroll_into_view_if_needed()
    log("DELETE result: " + messages(page).last.inner_text()[:300])
    time.sleep(5 + PAUSE_BETWEEN_REQUESTS)

    caption(page, "7 · A request with no filters is blocked in code")
    ask(page, "Just wipe the whole database.")
    time.sleep(6)

    caption(page, "Done · every answer shows its Gemini calls, tokens and estimated cost")
    page.locator('[data-testid="stSidebar"]').scroll_into_view_if_needed()
    time.sleep(4)


def main() -> None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix="demo_backup_"))
    shutil.copy2(DB_PATH, backup_dir / DB_PATH.name)
    if INVALID_ROWS_PATH.exists():
        shutil.copy2(INVALID_ROWS_PATH, backup_dir / INVALID_ROWS_PATH.name)
    before = checksum(DB_PATH)

    with tempfile.TemporaryDirectory() as raw_video_dir:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport=SIZE, record_video_dir=raw_video_dir, record_video_size=SIZE)
                page = context.new_page()
                try:
                    run_demo(page)
                finally:
                    # Closing the context writes the video, also after a failed step.
                    video = page.video
                    context.close()
                    browser.close()
                    target = VIDEO_DIR / f"demo_{datetime.now():%Y-%m-%d_%H%M}.webm"
                    shutil.move(video.path(), target)
                    log(f"VIDEO {target}")
        finally:
            shutil.copy2(backup_dir / DB_PATH.name, DB_PATH)
            if (backup_dir / INVALID_ROWS_PATH.name).exists():
                shutil.copy2(backup_dir / INVALID_ROWS_PATH.name, INVALID_ROWS_PATH)
            restored = checksum(DB_PATH) == before
            log(f"database restored: {'ok' if restored else 'CHECKSUM MISMATCH, backup in ' + str(backup_dir)}")
            if restored:
                shutil.rmtree(backup_dir)


if __name__ == "__main__":
    main()
