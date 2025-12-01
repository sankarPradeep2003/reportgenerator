from __future__ import annotations

import csv
import io
import logging
import os
import platform
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, jsonify

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__, template_folder=str(Path("templates")))
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# Store downloaded files with unique IDs (for Render deployment)
DOWNLOADED_FILES: dict[str, dict] = {}

# Store recent file IDs for notification system (last 50 files to support batch processing)
RECENT_FILE_IDS: list[dict] = []

# Check and install Playwright browsers if needed (for Render)
def ensure_playwright_browsers():
    """Check if Playwright browsers are installed, install if missing"""
    if not os.environ.get("RENDER"):
        return True
    
    try:
        # Check if browser executable exists by trying to get the path via subprocess
        # This avoids using sync API in async context
        import subprocess
        result = subprocess.run(
            ["python", "-c", "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path); p.stop()"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            browser_path = result.stdout.strip()
            if browser_path and Path(browser_path).exists():
                logger.info(f"Playwright browsers found at: {browser_path}")
                return True
        
        # Browsers not found, install them
        logger.info("Playwright browsers not found. Attempting to install...")
        install_result = subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if install_result.returncode == 0:
            logger.info("Playwright browsers installed successfully")
            # Also install system dependencies
            deps_result = subprocess.run(
                ["python", "-m", "playwright", "install-deps", "chromium"],
                capture_output=True,
                text=True,
                timeout=300
            )
            if deps_result.returncode == 0:
                logger.info("Playwright system dependencies installed")
            return True
        else:
            logger.error(f"Failed to install browsers: {install_result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Browser installation timed out")
        return False
    except Exception as e:
        logger.error(f"Error ensuring Playwright browsers: {e}")
        # Try direct installation as fallback
        try:
            logger.info("Attempting direct browser installation...")
            import subprocess
            result = subprocess.run(
                ["python", "-m", "playwright", "install", "--with-deps", "chromium"],
                capture_output=True,
                text=True,
                timeout=600
            )
            if result.returncode == 0:
                logger.info("Playwright browsers installed via fallback method")
                return True
        except Exception as fallback_error:
            logger.error(f"Fallback installation also failed: {fallback_error}")
        return False

# Check on startup (but don't block if it fails)
if os.environ.get("RENDER"):
    logger.info("Checking Playwright browser installation...")
    try:
        ensure_playwright_browsers()
    except Exception as e:
        logger.warning(f"Could not verify/install browsers on startup: {e}. Will try at runtime.")


def get_downloads_dir() -> Path:
    """Get the user's Downloads directory in a cross-platform way."""
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        # On Windows, check common Downloads locations
        downloads = home / "Downloads"
        if downloads.exists():
            return downloads
        # Fallback to user profile Downloads
        return Path(os.path.expanduser("~/Downloads"))
    elif system == "Darwin":  # macOS
        return home / "Downloads"
    else:  # Linux or other Unix-like
        return home / "Downloads"


def find_chrome_exe() -> Optional[Path]:
    """Find Chrome executable on Windows or macOS."""
    system = platform.system()
    candidates = []
    
    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
    elif system == "Darwin":  # macOS
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:  # Linux or other Unix-like
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
        ]
    
    for p in candidates:
        if p.is_file():
            return p
    return None


def open_in_chrome(url: str) -> tuple[bool, str]:
    chrome = find_chrome_exe()
    if not chrome:
        return False, "Google Chrome not found. Please install Chrome or provide the path."

    try:
        # Launch Chrome without blocking the server
        subprocess.Popen([str(chrome), url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"Opened in Chrome: {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed to launch Chrome: {exc}"


def normalize_url(raw: str) -> Optional[str]:
    text = raw.strip()
    if not text:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    # Simple sanity check
    if "." not in text:
        return None
    return text


async def open_and_login_with_playwright(
    url: str,
    username: str,
    password: str,
    course_query: str | None = None,
    module_query: str | None = None,
    test_query: str | None = None,
    filename_choice: str = "test",
    keep_open_ms: int = 300000,
) -> tuple[bool, str]:
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright not installed: {exc}"

    try:
        # On Render, ensure browsers are installed before trying to use them
        if os.environ.get("RENDER"):
            logger.info("Ensuring Playwright browsers are installed...")
            ensure_playwright_browsers()
        
        async with async_playwright() as p:
            # Prefer the user's installed Google Chrome; fallback to bundled Chromium
            browser = None
            # Use headless mode on Render (no display available)
            headless_mode = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
            
            # Launch browser with proper configuration for Render
            try:
                # Try to launch with system chromium first
                browser = await p.chromium.launch(headless=headless_mode)
            except Exception as e1:
                logger.warning(f"Failed to launch chromium: {e1}")
                # If on Render and launch failed, try installing browsers again
                if os.environ.get("RENDER"):
                    logger.info("Browser launch failed, attempting to install browsers...")
                    ensure_playwright_browsers()
                    # Try again after installation
                    try:
                        browser = await p.chromium.launch(headless=headless_mode)
                    except Exception as e1_retry:
                        logger.error(f"Still failed after installation attempt: {e1_retry}")
                        raise e1_retry
                else:
                    try:
                        # Try with channel="chrome" if available
                        browser = await p.chromium.launch(channel="chrome", headless=headless_mode)
                    except Exception as e2:
                        logger.error(f"Failed to launch chrome channel: {e2}")
                        # Last resort: try with minimal args for Render
                        browser = await p.chromium.launch(
                            headless=headless_mode,
                            args=['--no-sandbox', '--disable-setuid-sandbox']
                        )
            # On Render, use /tmp for downloads instead of user Downloads folder
            if os.environ.get("RENDER"):
                download_dir = Path("/tmp/downloads")
            else:
                download_dir = get_downloads_dir()
            try:
                download_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            
            # Navigate and wait for redirects to complete
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            
            # Wait for the Angular form fields to be available (using your exact selectors)
            email_selector = 'input[id="emailAddress"]'
            password_selector = 'input[id="password"]'
            
            try:
                # Wait for email field to be visible and ready
                await page.wait_for_selector(email_selector, state="visible", timeout=30000)
                await page.fill(email_selector, username)
                
                # Wait for password field to be visible and ready
                await page.wait_for_selector(password_selector, state="visible", timeout=10000)
                await page.fill(password_selector, password)
                
                # Try to find and click the Login button using your markup
                clicked = False
                try:
                    await page.get_by_role("button", name="Login").click()
                    clicked = True
                except Exception:
                    pass

                if not clicked:
                    try:
                        await page.locator("button[label='Login']").click()
                        clicked = True
                    except Exception:
                        pass

                if not clicked:
                    try:
                        await page.locator("button.form__button:has-text('Login')").click()
                        clicked = True
                    except Exception:
                        pass

                if not clicked:
                    try:
                        await page.click("button[type='submit']")
                        clicked = True
                    except Exception:
                        # If still not found, press Enter in password field
                        await page.press(password_selector, "Enter")
                
                # Wait for navigation and then attempt to select the Courses tool
                try:
                    await page.wait_for_load_state("networkidle", timeout=60000)
                    # Additional wait for Angular to render the menu items
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Wait for the left-menu container and then click the Courses option
                course_clicked = False
                
                # First, wait for the left-menu container to be visible
                try:
                    await page.wait_for_selector("div.left-menu", state="visible", timeout=30000)
                    await page.wait_for_timeout(1000)  # Additional wait for menu items to render
                except Exception:
                    pass

                # Primary: Wait for and click Courses within the left-menu using ptooltip attribute
                try:
                    course_locator = page.locator("div.left-menu li[ptooltip='Courses']")
                    await course_locator.wait_for(state="visible", timeout=30000)
                    await course_locator.first.click()
                    course_clicked = True
                except Exception:
                    pass

                # Fallback 1: Click via class and icon within left-menu
                if not course_clicked:
                    try:
                        course_locator = page.locator("div.left-menu li.each-tool:has(span.icon-learning)")
                        await course_locator.wait_for(state="visible", timeout=10000)
                        # Filter to only the one with ptooltip="Courses"
                        course_locator = page.locator("div.left-menu li.each-tool[ptooltip='Courses']")
                        await course_locator.first.click()
                        course_clicked = True
                    except Exception:
                        pass

                # Fallback 2: Click the span inside the li within left-menu
                if not course_clicked:
                    try:
                        course_locator = page.locator("div.left-menu li[ptooltip='Courses'] span.icon-learning")
                        await course_locator.wait_for(state="visible", timeout=10000)
                        await course_locator.first.click()
                        course_clicked = True
                    except Exception:
                        pass

                # Fallback 3: Try clicking by text content within left-menu
                if not course_clicked:
                    try:
                        course_locator = page.locator("div.left-menu").get_by_role("listitem").filter(has_text="Courses")
                        await course_locator.first.click()
                        course_clicked = True
                    except Exception:
                        pass

                # If a course query was provided, focus search and type it
                if course_clicked and (course_query or "").strip():
                    search_sel = "input[placeholder='Enter course name to search']"
                    try:
                        await page.wait_for_selector(search_sel, state="visible", timeout=20000)
                        await page.click(search_sel)
                        await page.fill(search_sel, course_query.strip())
                        # Submit with Enter to trigger search
                        await page.press(search_sel, "Enter")
                        
                        # Wait for search results to appear and click on the course row
                        try:
                            # Wait for the results table to appear
                            await page.wait_for_selector("tbody.ui-datatable-data", state="visible", timeout=10000)
                            await page.wait_for_timeout(2000)  # Additional wait for table to fully render
                            
                            # Try to click the row containing the course name (partial match)
                            course_row_clicked = False
                            try:
                                # Look for a row containing the course name text
                                course_row = page.locator("tbody.ui-datatable-data tr").filter(has_text=course_query.strip())
                                await course_row.first.wait_for(state="visible", timeout=10000)
                                await course_row.first.click()
                                course_row_clicked = True
                            except Exception:
                                pass
                            
                            # Fallback: Click the first result row if specific match failed
                            if not course_row_clicked:
                                try:
                                    await page.locator("tbody.ui-datatable-data tr.ui-datatable-even").first.click()
                                    course_row_clicked = True
                                except Exception:
                                    pass
                            
                            # Fallback: Click anywhere on the first row
                            if not course_row_clicked:
                                try:
                                    await page.locator("tbody.ui-datatable-data tr").first.click()
                                    course_row_clicked = True
                                except Exception:
                                    pass
                            
                            # After clicking the course row, wait for navigation to course page
                            if course_row_clicked:
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        pass

                # If a module was supplied, click the matching module in the sidebar
                if (module_query or "").strip():
                    target_module = " ".join(module_query.strip().split())
                    try:
                        sidebar = page.locator("div.ui-g-3.sidedivpre")
                        module_entries = sidebar.locator("span.modulelist")

                        import re as _re_mod

                        pattern_module = _re_mod.compile(_re_mod.escape(target_module), flags=_re_mod.IGNORECASE)
                        matching_module = module_entries.filter(has_text=pattern_module)
                        await matching_module.first.click()
                        await page.wait_for_timeout(10000)
                    except Exception:
                        pass

                # If a specific test should be interacted with, search the preview page
                test_clicked = False
                sanitized_filename = None
                
                # Determine which name to use for the filename based on user choice
                import re as _re  # local import to keep scope limited
                if filename_choice == "course" and (course_query or "").strip():
                    sanitized_filename = (
                        _re.sub(r"[^A-Za-z0-9._-]+", "_", course_query.strip()).strip("_") or "report"
                    )
                elif filename_choice == "test" and (test_query or "").strip():
                    sanitized_filename = (
                        _re.sub(r"[^A-Za-z0-9._-]+", "_", test_query.strip()).strip("_") or "report"
                    )
                
                if (test_query or "").strip():
                    target_test = " ".join(test_query.strip().split())
                    try:
                        main_container = page.locator("div.ui-g-9.maindivpre")
                        await main_container.wait_for(state="visible", timeout=5000)
                        test_cards = main_container.locator("div.ui-g-12.moduletest")

                        pattern = _re.compile(_re.escape(target_test), flags=_re.IGNORECASE)
                        matching_card = test_cards.filter(has_text=pattern)

                        await matching_card.first.wait_for(state="visible", timeout=5000)
                        card = matching_card.first
                        await card.scroll_into_view_if_needed()

                        completed_counter = card.locator(
                            "div.confirmModal.st-count span.meta-data.ui-g-12.ui-g-nopad"
                        )
                        await completed_counter.first.wait_for(state="visible", timeout=5000)
                        await completed_counter.first.click()
                        test_clicked = True
                    except Exception:
                        pass

                if test_clicked:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=2000)
                    except Exception:
                        pass
                    try:
                        checkbox = page.locator(
                            "div.ui-chkbox-box.ui-widget.ui-corner-all.ui-state-default"
                        ).first
                        await checkbox.wait_for(state="visible", timeout=10000)
                        await checkbox.click()

                        select_all = (
                            page.locator("span.text-underline")
                            .filter(has_text="Select all")
                            .first
                        )
                        try:
                            await select_all.wait_for(state="visible", timeout=3000)
                            await select_all.click()
                        except Exception:
                            pass

                        action_label = (
                            page.locator("label.ui-dropdown-label")
                            .filter(has_text="Action")
                            .first
                        )
                        await action_label.wait_for(state="visible", timeout=10000)
                        dropdown_container = action_label.locator(
                            "xpath=ancestor::div[contains(@class, 'ui-dropdown')]"
                        )
                        await dropdown_container.first.click()

                        shareable_option = page.locator(
                            "li.ui-dropdown-item.ui-corner-all[aria-label='Generate Shareable Link']"
                        )
                        await shareable_option.first.wait_for(state="visible", timeout=5000)
                        await shareable_option.first.click()
                        await page.wait_for_timeout(90000)

                        completed_label = page.locator(
                            "span.ui-multiselect-label.ui-corner-all"
                        ).filter(has_text="Completed").first
                        await completed_label.wait_for(state="visible", timeout=5000)
                        await completed_label.click()

                        multiselect_checkbox = page.locator(
                            "div.ui-multiselect-panel div.ui-chkbox-box.ui-widget.ui-corner-all.ui-state-default"
                        ).first
                        await multiselect_checkbox.wait_for(state="visible", timeout=5000)
                        await multiselect_checkbox.click()

                        download_results = (
                            page.locator("span", has_text="Download results").first
                        )
                        await download_results.wait_for(state="visible", timeout=10000)
                        await download_results.scroll_into_view_if_needed()
                        await download_results.click()

                        # Select Excel option instead of CSV
                        excel_option_clicked = False
                        try:
                            # Try to find by label text "Excel (.xlsx)"
                            excel_label = page.locator("label", has_text="Excel (.xlsx)").first
                            await excel_label.wait_for(state="visible", timeout=5000)
                            await excel_label.click()
                            excel_option_clicked = True
                        except Exception:
                            try:
                                # Try to find by input value="excel"
                                excel_input = page.locator('input[type="radio"][name="downloadFileType"][value="excel"]')
                                await excel_input.wait_for(state="visible", timeout=5000)
                                await excel_input.click()
                                excel_option_clicked = True
                            except Exception:
                                try:
                                    # Try to find p-radiobutton with label="Excel (.xlsx)"
                                    excel_radio = page.locator('p-radiobutton[label="Excel (.xlsx)"]').first
                                    await excel_radio.wait_for(state="visible", timeout=5000)
                                    await excel_radio.click()
                                    excel_option_clicked = True
                                except Exception:
                                    # Fallback: find span inside p-radiobutton with Excel label
                                    excel_span = page.locator('p-radiobutton:has(label:has-text("Excel")) span.ui-radiobutton-icon').first
                                    await excel_span.wait_for(state="visible", timeout=5000)
                                    await excel_span.click()
                                    excel_option_clicked = True

                        download_button = page.locator(
                            "button.download-button"
                        ).first
                        await download_button.wait_for(state="visible", timeout=5000)
                        try:
                            async with page.expect_download() as download_info:
                                await download_button.click()
                            download = await download_info.value
                            suggested_name = download.suggested_filename
                            extension = Path(suggested_name).suffix or ".xlsx"
                            if sanitized_filename:
                                target_path = download_dir / f"{sanitized_filename}{extension}"
                            else:
                                target_path = download_dir / suggested_name
                            await download.save_as(str(target_path))
                            
                            # Wait a bit for file to be fully written and retry if needed
                            file_exists = False
                            for retry in range(5):
                                await page.wait_for_timeout(500)
                                if target_path.exists() and target_path.stat().st_size > 0:
                                    file_exists = True
                                    break
                                logger.debug(f"Waiting for file {target_path.name} to exist (retry {retry+1}/5)")
                            
                            # On Render, store file info for download
                            # Check if we're on Render (either by env var or by checking if we're using /tmp/downloads)
                            is_render = os.environ.get("RENDER") or str(download_dir).startswith("/tmp")
                            file_size = target_path.stat().st_size if target_path.exists() else 0
                            logger.info(f"Download completed: path={target_path}, exists={file_exists}, size={file_size}, RENDER={is_render}, download_dir={download_dir}")
                            
                            # Always try to add file if it exists (for Render deployment)
                            if file_exists and file_size > 0:
                                try:
                                    logger.info(f"📦 Storing file in memory: {target_path.name} ({file_size} bytes)")
                                    file_id = secrets.token_urlsafe(16)
                                    with open(target_path, "rb") as f:
                                        file_data = f.read()
                                    
                                    if len(file_data) > 0:
                                        DOWNLOADED_FILES[file_id] = {
                                            "data": file_data,
                                            "filename": target_path.name,
                                            "created": time.time()
                                        }
                                        # Clean up old files (older than 1 hour)
                                        current_time = time.time()
                                        for k in list(DOWNLOADED_FILES.keys()):
                                            if current_time - DOWNLOADED_FILES[k]["created"] > 3600:
                                                del DOWNLOADED_FILES[k]
                                        logger.info(f"💾 File stored in DOWNLOADED_FILES: ID={file_id}, filename={target_path.name}, size={len(file_data)} bytes, total files={len(DOWNLOADED_FILES)}")
                                        
                                        # Add to recent files for notification
                                        RECENT_FILE_IDS.insert(0, {
                                            "file_id": file_id,
                                            "filename": target_path.name,
                                            "created": time.time()
                                        })
                                        # Keep only last 50 files (to support batch processing)
                                        if len(RECENT_FILE_IDS) > 50:
                                            RECENT_FILE_IDS.pop()
                                        logger.info(f"🔔 FILE READY FOR NOTIFICATION: {target_path.name} (ID: {file_id[:12]}...) - Added to notification list. Total recent files: {len(RECENT_FILE_IDS)}")
                                        
                                        # Store file_id for later retrieval
                                        if not hasattr(open_and_login_with_playwright, '_last_file_id'):
                                            open_and_login_with_playwright._last_file_id = None
                                        open_and_login_with_playwright._last_file_id = file_id
                                    else:
                                        logger.warning(f"⚠️ File {target_path.name} is empty after reading, not adding to notification")
                                except Exception as e:
                                    logger.error(f"❌ Error storing file {target_path.name} for notification: {e}", exc_info=True)
                            else:
                                logger.warning(f"⚠️ File not added to notification: exists={file_exists}, size={file_size}, path={target_path}, download_dir={download_dir}")
                            
                            # Click the close button after download completes - click twice to close both dialogs
                            await page.wait_for_timeout(10000)  # Wait 10 seconds after download completes
                            
                            # Function to click the close button
                            async def click_close_button():
                                close_clicked = False
                                
                                # Strategy 1: Directly click the span.pi.pi-times element inside ui-dialog-titlebar-close
                                try:
                                    # Target span.pi.pi-times inside the anchor with class ui-dialog-titlebar-close
                                    close_span = page.locator("a.ui-dialog-titlebar-close span.pi.pi-times, a[class*='ui-dialog-titlebar-close'] span.pi.pi-times").first
                                    await close_span.wait_for(state="visible", timeout=10000)
                                    await close_span.scroll_into_view_if_needed()
                                    await page.wait_for_timeout(500)  # Small additional wait to ensure element is ready
                                    # Force click directly on the span element
                                    await close_span.click(force=True)
                                    close_clicked = True
                                except Exception:
                                    # Fallback: try finding any span.pi.pi-times in the dialog titlebar
                                    try:
                                        close_span = page.locator("div.ui-dialog-titlebar span.pi.pi-times").first
                                        await close_span.wait_for(state="visible", timeout=5000)
                                        await close_span.scroll_into_view_if_needed()
                                        await close_span.click(force=True)
                                        close_clicked = True
                                    except Exception:
                                        # Last fallback: any span.pi.pi-times
                                        try:
                                            close_span = page.locator("span.pi.pi-times").first
                                            await close_span.wait_for(state="visible", timeout=5000)
                                            await close_span.scroll_into_view_if_needed()
                                            await close_span.click(force=True)
                                            close_clicked = True
                                        except Exception:
                                            pass
                                
                                # Strategy 2: Use JavaScript to directly click the span.pi.pi-times element
                                if not close_clicked:
                                    try:
                                        result = await page.evaluate("""
                                            () => {
                                                // Find the span.pi.pi-times element inside ui-dialog-titlebar-close anchor
                                                let closeSpan = document.querySelector('a.ui-dialog-titlebar-close span.pi.pi-times') || 
                                                               document.querySelector('a[class*="ui-dialog-titlebar-close"] span.pi.pi-times') ||
                                                               document.querySelector('div.ui-dialog-titlebar span.pi.pi-times') ||
                                                               document.querySelector('span.pi.pi-times');
                                                if (closeSpan) {
                                                    // Scroll it into view first
                                                    closeSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                    // Click the span directly
                                                    closeSpan.click();
                                                    // Also dispatch a click event to ensure it triggers
                                                    const clickEvent = new MouseEvent('click', {
                                                        bubbles: true,
                                                        cancelable: true,
                                                        view: window,
                                                        button: 0
                                                    });
                                                    closeSpan.dispatchEvent(clickEvent);
                                                    return true;
                                                }
                                                return false;
                                            }
                                        """)
                                        close_clicked = result if result else False
                                    except Exception:
                                        pass
                                
                                return close_clicked
                            
                            # Click the close button first time
                            first_click = await click_close_button()
                            
                            # Wait a bit for the dialog to close
                            await page.wait_for_timeout(2000)
                            
                            # Click the close button second time to close the second dialog/window
                            second_click = await click_close_button()
                            
                            close_clicked = first_click or second_click
                        except Exception:
                            await download_button.click()
                    except Exception:
                        pass

                await page.wait_for_timeout(keep_open_ms)

                # Check if file was downloaded (for Render)
                if os.environ.get("RENDER"):
                    # Check if we have a file ID from the download
                    if hasattr(open_and_login_with_playwright, '_last_file_id') and open_and_login_with_playwright._last_file_id:
                        file_id = open_and_login_with_playwright._last_file_id
                        open_and_login_with_playwright._last_file_id = None  # Reset
                        return True, f"File downloaded successfully! <a href='/download/{file_id}' style='color: #047857; text-decoration: underline; font-weight: 600;'>Click here to download</a>"
                    # Fallback: Find the most recent file ID
                    elif DOWNLOADED_FILES:
                        latest_file_id = max(DOWNLOADED_FILES.keys(), 
                                           key=lambda k: DOWNLOADED_FILES[k]["created"])
                        return True, f"File downloaded successfully! <a href='/download/{latest_file_id}' style='color: #047857; text-decoration: underline; font-weight: 600;'>Click here to download</a>"
                
                return True, f"Opened in Chrome, logged in, navigated to Courses, and opened the course. Browser kept open for {(keep_open_ms//6000)} min."
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Playwright error in open_and_login_with_playwright: {exc}", exc_info=True)
                return False, f"Failed to fill login fields: {exc}. Please check if the page loaded correctly."
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Playwright initialization error: {exc}", exc_info=True)
        return False, f"Playwright error: {exc}"


async def process_single_course_in_session(
    page,
    download_dir: Path,
    course_query: str,
    module_query: str,
    test_query: str,
    filename_choice: str = "test",
) -> tuple[bool, str]:
    """Process a single course/module/test within an existing browser session (assumes already on courses page) - uses EXACT same flow as single course"""
    # Increase timeouts for Render (slower environment)
    is_render_env = os.environ.get("RENDER") or str(download_dir).startswith("/tmp")
    base_timeout = 30000 if is_render_env else 20000
    short_timeout = 15000 if is_render_env else 10000
    very_short_timeout = 10000 if is_render_env else 5000
    
    try:
        logger.info(f"📍 Starting process_single_course_in_session for: {course_query} - {test_query}")
        logger.info(f"🔧 Environment check: is_render_env={is_render_env}, download_dir={download_dir}")
        logger.info(f"⏱️ Timeouts: base={base_timeout}ms, short={short_timeout}ms, very_short={very_short_timeout}ms")
        
        # Check if page is still valid
        try:
            page_url = page.url
            logger.info(f"🌐 Current page URL: {page_url}")
        except Exception as page_check_exc:
            logger.error(f"❌ Page is not valid: {page_check_exc}")
            return False, f"Page is not valid: {page_check_exc}"
        
        # Use EXACT same flow from open_and_login_with_playwright starting from course search
        # If a course query was provided, focus search and type it
        if (course_query or "").strip():
            logger.info(f"🔍 Step 1: Searching for course: {course_query}")
            # Wait a bit longer on Render for page to be ready
            if is_render_env:
                logger.info("⏳ Waiting 3s for page to be ready (Render)...")
                await page.wait_for_timeout(3000)
            search_sel = "input[placeholder='Enter course name to search']"
            try:
                logger.info(f"🔍 Step 1.1: Waiting for search input (timeout: {base_timeout}ms)...")
                await page.wait_for_selector(search_sel, state="visible", timeout=base_timeout)
                logger.info("✅ Search input found")
                logger.info(f"🔍 Step 1.2: Clicking and filling search input...")
                await page.click(search_sel)
                await page.fill(search_sel, course_query.strip())
                # Submit with Enter to trigger search
                logger.info(f"🔍 Step 1.3: Submitting search with Enter...")
                await page.press(search_sel, "Enter")
                
                # Wait for search results to appear and click on the course row
                try:
                    logger.info(f"🔍 Step 1.4: Waiting for search results table (timeout: {short_timeout}ms)...")
                    # Wait for the results table to appear
                    await page.wait_for_selector("tbody.ui-datatable-data", state="visible", timeout=short_timeout)
                    logger.info("✅ Search results table found")
                    # Additional wait for table to fully render (longer on Render)
                    wait_time = 5000 if is_render_env else 2000
                    logger.info(f"⏳ Waiting {wait_time}ms for table to render...")
                    await page.wait_for_timeout(wait_time)
                    
                    # Try to click the row containing the course name (partial match)
                    logger.info(f"🔍 Step 1.5: Looking for course row to click...")
                    course_row_clicked = False
                    try:
                        # Look for a row containing the course name text
                        course_row = page.locator("tbody.ui-datatable-data tr").filter(has_text=course_query.strip())
                        logger.info(f"🔍 Step 1.5.1: Waiting for matching course row (timeout: {short_timeout}ms)...")
                        await course_row.first.wait_for(state="visible", timeout=short_timeout)
                        logger.info("✅ Matching course row found, clicking...")
                        await course_row.first.click()
                        course_row_clicked = True
                        logger.info("✅ Course row clicked successfully")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to click matching course row: {e}")
                        pass
                    
                    # Fallback: Click the first result row if specific match failed
                    if not course_row_clicked:
                        logger.info("🔄 Fallback 1: Trying to click first even row...")
                        try:
                            await page.locator("tbody.ui-datatable-data tr.ui-datatable-even").first.click()
                            course_row_clicked = True
                            logger.info("✅ Fallback 1: First even row clicked")
                        except Exception as e:
                            logger.warning(f"⚠️ Fallback 1 failed: {e}")
                            pass
                    
                    # Fallback: Click anywhere on the first row
                    if not course_row_clicked:
                        logger.info("🔄 Fallback 2: Trying to click first row...")
                        try:
                            await page.locator("tbody.ui-datatable-data tr").first.click()
                            course_row_clicked = True
                            logger.info("✅ Fallback 2: First row clicked")
                        except Exception as e:
                            logger.warning(f"⚠️ Fallback 2 failed: {e}")
                            pass
                    
                    # After clicking the course row, wait for navigation to course page
                    if course_row_clicked:
                        logger.info("🔍 Step 1.6: Waiting for navigation to course page...")
                        try:
                            await page.wait_for_load_state("networkidle", timeout=short_timeout)
                            logger.info("✅ Navigation complete")
                            # Additional wait on Render
                            if is_render_env:
                                logger.info("⏳ Additional 3s wait for Render...")
                                await page.wait_for_timeout(3000)
                        except Exception as e:
                            logger.warning(f"⚠️ Navigation wait failed (continuing anyway): {e}")
                            pass
                    else:
                        logger.error("❌ Failed to click any course row")
                except Exception as e:
                    logger.error(f"❌ Error waiting for search results: {e}", exc_info=True)
                    pass
            except Exception as e:
                logger.error(f"❌ Error in course search: {e}", exc_info=True)
                pass

        # If a module was supplied, click the matching module in the sidebar - EXACT same code
        if (module_query or "").strip():
            logger.info(f"🔍 Step 2: Looking for module: {module_query}")
            target_module = " ".join(module_query.strip().split())
            try:
                sidebar = page.locator("div.ui-g-3.sidedivpre")
                module_entries = sidebar.locator("span.modulelist")

                import re as _re_mod

                pattern_module = _re_mod.compile(_re_mod.escape(target_module), flags=_re_mod.IGNORECASE)
                matching_module = module_entries.filter(has_text=pattern_module)
                logger.info("🔍 Step 2.1: Clicking matching module...")
                await matching_module.first.click()
                logger.info("✅ Module clicked")
                # Longer wait on Render
                wait_time = 15000 if is_render_env else 10000
                logger.info(f"⏳ Waiting {wait_time}ms for module to load...")
                await page.wait_for_timeout(wait_time)
            except Exception as e:
                logger.warning(f"⚠️ Error clicking module: {e}")
                pass

        # If a specific test should be interacted with, search the preview page - EXACT same code
        test_clicked = False
        sanitized_filename = None
        
        # Determine which name to use for the filename based on user choice
        import re as _re  # local import to keep scope limited
        if filename_choice == "course" and (course_query or "").strip():
            sanitized_filename = (
                _re.sub(r"[^A-Za-z0-9._-]+", "_", course_query.strip()).strip("_") or "report"
            )
        elif filename_choice == "test" and (test_query or "").strip():
            sanitized_filename = (
                _re.sub(r"[^A-Za-z0-9._-]+", "_", test_query.strip()).strip("_") or "report"
            )
        
        if (test_query or "").strip():
            target_test = " ".join(test_query.strip().split())
            logger.info(f"🔍 Looking for test: {target_test}")
            try:
                main_container = page.locator("div.ui-g-9.maindivpre")
                await main_container.wait_for(state="visible", timeout=short_timeout)
                test_cards = main_container.locator("div.ui-g-12.moduletest")
                
                # Count available test cards for logging
                test_count = await test_cards.count()
                logger.info(f"📋 Found {test_count} test cards")

                pattern = _re.compile(_re.escape(target_test), flags=_re.IGNORECASE)
                matching_card = test_cards.filter(has_text=pattern)
                
                # Check if matching card exists
                matching_count = await matching_card.count()
                logger.info(f"🎯 Found {matching_count} matching test cards for '{target_test}'")

                await matching_card.first.wait_for(state="visible", timeout=short_timeout)
                card = matching_card.first
                await card.scroll_into_view_if_needed()
                # Additional wait on Render
                if is_render_env:
                    await page.wait_for_timeout(2000)

                completed_counter = card.locator(
                    "div.confirmModal.st-count span.meta-data.ui-g-12.ui-g-nopad"
                )
                await completed_counter.first.wait_for(state="visible", timeout=short_timeout)
                await completed_counter.first.click()
                test_clicked = True
                logger.info(f"✅ Test clicked successfully: {target_test}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to click test '{target_test}': {e}")
                # Try fallback: click first test card if exact match fails
                try:
                    logger.info("🔄 Trying fallback: clicking first test card")
                    main_container = page.locator("div.ui-g-9.maindivpre")
                    await main_container.wait_for(state="visible", timeout=short_timeout)
                    test_cards = main_container.locator("div.ui-g-12.moduletest")
                    first_card = test_cards.first
                    await first_card.wait_for(state="visible", timeout=short_timeout)
                    await first_card.scroll_into_view_if_needed()
                    if is_render_env:
                        await page.wait_for_timeout(2000)
                    completed_counter = first_card.locator(
                        "div.confirmModal.st-count span.meta-data.ui-g-12.ui-g-nopad"
                    )
                    await completed_counter.first.wait_for(state="visible", timeout=short_timeout)
                    await completed_counter.first.click()
                    test_clicked = True
                    logger.info("✅ Fallback: First test card clicked successfully")
                except Exception as e2:
                    logger.error(f"❌ Fallback also failed: {e2}")

        if test_clicked:
            try:
                await page.wait_for_load_state("networkidle", timeout=very_short_timeout)
                # Additional wait on Render
                if is_render_env:
                    await page.wait_for_timeout(3000)
            except Exception:
                pass
            
            try:
                checkbox = page.locator(
                    "div.ui-chkbox-box.ui-widget.ui-corner-all.ui-state-default"
                ).first
                await checkbox.wait_for(state="visible", timeout=short_timeout)
                await checkbox.click()
                if is_render_env:
                    await page.wait_for_timeout(1000)

                select_all = (
                    page.locator("span.text-underline")
                    .filter(has_text="Select all")
                    .first
                )
                try:
                    await select_all.wait_for(state="visible", timeout=very_short_timeout)
                    await select_all.click()
                    if is_render_env:
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                action_label = (
                    page.locator("label.ui-dropdown-label")
                    .filter(has_text="Action")
                    .first
                )
                await action_label.wait_for(state="visible", timeout=short_timeout)
                dropdown_container = action_label.locator(
                    "xpath=ancestor::div[contains(@class, 'ui-dropdown')]"
                )
                await dropdown_container.first.click()
                if is_render_env:
                    await page.wait_for_timeout(1000)

                shareable_option = page.locator(
                    "li.ui-dropdown-item.ui-corner-all[aria-label='Generate Shareable Link']"
                )
                await shareable_option.first.wait_for(state="visible", timeout=very_short_timeout)
                await shareable_option.first.click()
                wait_time = 2000 if is_render_env else 1000
                await page.wait_for_timeout(wait_time)

                completed_label = page.locator(
                    "span.ui-multiselect-label.ui-corner-all"
                ).filter(has_text="Completed").first
                await completed_label.wait_for(state="visible", timeout=very_short_timeout)
                await completed_label.click()
                if is_render_env:
                    await page.wait_for_timeout(1000)

                multiselect_checkbox = page.locator(
                    "div.ui-multiselect-panel div.ui-chkbox-box.ui-widget.ui-corner-all.ui-state-default"
                ).first
                await multiselect_checkbox.wait_for(state="visible", timeout=very_short_timeout)
                await multiselect_checkbox.click()
                if is_render_env:
                    await page.wait_for_timeout(1000)

                download_results = (
                    page.locator("span", has_text="Download results").first
                )
                await download_results.wait_for(state="visible", timeout=short_timeout)
                await download_results.scroll_into_view_if_needed()
                await download_results.click()
                if is_render_env:
                    await page.wait_for_timeout(2000)

                # Select Excel option instead of CSV
                excel_option_clicked = False
                try:
                    # Try to find by label text "Excel (.xlsx)"
                    excel_label = page.locator("label", has_text="Excel (.xlsx)").first
                    await excel_label.wait_for(state="visible", timeout=very_short_timeout)
                    await excel_label.click()
                    excel_option_clicked = True
                    if is_render_env:
                        await page.wait_for_timeout(1000)
                except Exception:
                    try:
                        # Try to find by input value="excel"
                        excel_input = page.locator('input[type="radio"][name="downloadFileType"][value="excel"]')
                        await excel_input.wait_for(state="visible", timeout=very_short_timeout)
                        await excel_input.click()
                        excel_option_clicked = True
                        if is_render_env:
                            await page.wait_for_timeout(1000)
                    except Exception:
                        try:
                            # Try to find p-radiobutton with label="Excel (.xlsx)"
                            excel_radio = page.locator('p-radiobutton[label="Excel (.xlsx)"]').first
                            await excel_radio.wait_for(state="visible", timeout=very_short_timeout)
                            await excel_radio.click()
                            excel_option_clicked = True
                            if is_render_env:
                                await page.wait_for_timeout(1000)
                        except Exception:
                            # Fallback: find span inside p-radiobutton with Excel label
                            excel_span = page.locator('p-radiobutton:has(label:has-text("Excel")) span.ui-radiobutton-icon').first
                            await excel_span.wait_for(state="visible", timeout=very_short_timeout)
                            await excel_span.click()
                            excel_option_clicked = True
                            if is_render_env:
                                await page.wait_for_timeout(1000)

                download_button = page.locator(
                    "button.download-button"
                ).first
                logger.info("🔍 Waiting for download button to appear...")
                try:
                    await download_button.wait_for(state="visible", timeout=base_timeout)
                    logger.info("✅ Download button found")
                    if is_render_env:
                        await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.error(f"❌ Download button not found: {e}")
                    # Try alternative selectors
                    try:
                        download_button = page.locator("button:has-text('Download')").first
                        await download_button.wait_for(state="visible", timeout=short_timeout)
                        logger.info("✅ Found download button using alternative selector")
                        if is_render_env:
                            await page.wait_for_timeout(2000)
                    except Exception:
                        return False, f"Download button not found after waiting"
                
                try:
                    logger.info("📥 Starting download...")
                    # Longer timeout on Render
                    download_timeout = 60000 if is_render_env else 30000
                    async with page.expect_download(timeout=download_timeout) as download_info:
                        await download_button.click()
                    download = await download_info.value
                    suggested_name = download.suggested_filename
                    logger.info(f"📥 Download started: {suggested_name}")
                    extension = Path(suggested_name).suffix or ".xlsx"
                    if sanitized_filename:
                        target_path = download_dir / f"{sanitized_filename}{extension}"
                    else:
                        target_path = download_dir / suggested_name
                    await download.save_as(str(target_path))
                    logger.info(f"💾 File saved to: {target_path}")
                    
                    # Wait a bit for file to be fully written and retry if needed
                    file_exists = False
                    logger.info(f"🔍 Starting file detection for {target_path.name} at {target_path}")
                    # More retries and longer waits on Render
                    max_retries = 20 if is_render_env else 10
                    retry_wait = 2000 if is_render_env else 1000
                    for retry in range(max_retries):
                        await page.wait_for_timeout(retry_wait)  # Wait between retries
                        if target_path.exists():
                            file_size = target_path.stat().st_size
                            if file_size > 0:
                                file_exists = True
                                logger.info(f"✅ File found after {retry+1} retries: {target_path.name}, size: {file_size} bytes")
                                break
                            else:
                                logger.debug(f"File exists but is empty (retry {retry+1}/10): {target_path.name}")
                        else:
                            logger.debug(f"File not found yet (retry {retry+1}/10): {target_path}")
                    
                    # On Render, store file info for download (same as in open_and_login_with_playwright)
                    # Check if we're on Render (either by env var or by checking if we're using /tmp/downloads)
                    is_render = os.environ.get("RENDER") or str(download_dir).startswith("/tmp")
                    file_size = target_path.stat().st_size if target_path.exists() else 0
                    logger.info(f"📥 Download completed: path={target_path}, exists={file_exists}, size={file_size}, RENDER={is_render}, download_dir={download_dir}")
                    
                    # Always try to add file if it exists (for Render deployment)
                    if file_exists and file_size > 0:
                        try:
                            logger.info(f"📦 Storing file in memory: {target_path.name} ({file_size} bytes)")
                            file_id = secrets.token_urlsafe(16)
                            with open(target_path, "rb") as f:
                                file_data = f.read()
                            
                            if len(file_data) > 0:
                                DOWNLOADED_FILES[file_id] = {
                                    "data": file_data,
                                    "filename": target_path.name,
                                    "created": time.time()
                                }
                                # Clean up old files (older than 1 hour)
                                current_time = time.time()
                                for k in list(DOWNLOADED_FILES.keys()):
                                    if current_time - DOWNLOADED_FILES[k]["created"] > 3600:
                                        del DOWNLOADED_FILES[k]
                                logger.info(f"💾 File stored in DOWNLOADED_FILES: ID={file_id}, filename={target_path.name}, size={len(file_data)} bytes, total files={len(DOWNLOADED_FILES)}")
                                
                                # Add to recent files for notification
                                RECENT_FILE_IDS.insert(0, {
                                    "file_id": file_id,
                                    "filename": target_path.name,
                                    "created": time.time()
                                })
                                # Keep only last 50 files (to support batch processing)
                                if len(RECENT_FILE_IDS) > 50:
                                    RECENT_FILE_IDS.pop()
                                logger.info(f"🔔 FILE READY FOR NOTIFICATION: {target_path.name} (ID: {file_id[:12]}...) - Added to notification list. Total recent files: {len(RECENT_FILE_IDS)}")
                            else:
                                logger.warning(f"⚠️ File {target_path.name} is empty after reading, not adding to notification")
                        except Exception as e:
                            logger.error(f"❌ Error storing file {target_path.name} for notification: {e}", exc_info=True)
                    else:
                        logger.warning(f"⚠️ File not added to notification: exists={file_exists}, size={file_size}, path={target_path}, download_dir={download_dir}")
                    
                    # Close dialogs after download - EXACT same code
                    await page.wait_for_timeout(10000)  # Wait 10 seconds after download completes
                    
                    close_clicked = False
                    
                    # Strategy 1: Directly click the span.pi.pi-times element inside ui-dialog-titlebar-close
                    try:
                        close_span = page.locator("a.ui-dialog-titlebar-close span.pi.pi-times, a[class*='ui-dialog-titlebar-close'] span.pi.pi-times").first
                        await close_span.wait_for(state="visible", timeout=10000)
                        await close_span.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await close_span.click(force=True)
                        close_clicked = True
                    except Exception:
                        try:
                            close_span = page.locator("div.ui-dialog-titlebar span.pi.pi-times").first
                            await close_span.wait_for(state="visible", timeout=5000)
                            await close_span.scroll_into_view_if_needed()
                            await close_span.click(force=True)
                            close_clicked = True
                        except Exception:
                            try:
                                close_span = page.locator("span.pi.pi-times").first
                                await close_span.wait_for(state="visible", timeout=5000)
                                await close_span.scroll_into_view_if_needed()
                                await close_span.click(force=True)
                                close_clicked = True
                            except Exception:
                                pass
                    
                    # Strategy 2: Use JavaScript to directly click the span.pi.pi-times element
                    if not close_clicked:
                        try:
                            result = await page.evaluate("""
                                () => {
                                    let closeSpan = document.querySelector('a.ui-dialog-titlebar-close span.pi.pi-times') || 
                                                   document.querySelector('a[class*="ui-dialog-titlebar-close"] span.pi.pi-times') ||
                                                   document.querySelector('div.ui-dialog-titlebar span.pi.pi-times') ||
                                                   document.querySelector('span.pi.pi-times');
                                    if (closeSpan) {
                                        closeSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                        closeSpan.click();
                                        const clickEvent = new MouseEvent('click', {
                                            bubbles: true,
                                            cancelable: true,
                                            view: window,
                                            button: 0
                                        });
                                        closeSpan.dispatchEvent(clickEvent);
                                        return true;
                                    }
                                    return false;
                                }
                            """)
                            close_clicked = result if result else False
                        except Exception:
                            pass
                    
                    # Click close button second time
                    await page.wait_for_timeout(2000)
                    
                    try:
                        close_span = page.locator("a.ui-dialog-titlebar-close span.pi.pi-times, a[class*='ui-dialog-titlebar-close'] span.pi.pi-times").first
                        await close_span.wait_for(state="visible", timeout=5000)
                        await close_span.scroll_into_view_if_needed()
                        await close_span.click(force=True)
                    except Exception:
                        try:
                            close_span = page.locator("span.pi.pi-times").first
                            await close_span.wait_for(state="visible", timeout=3000)
                            await close_span.scroll_into_view_if_needed()
                            await close_span.click(force=True)
                        except Exception:
                            pass
                except Exception as download_exc:
                    logger.warning(f"⚠️ Download exception (may have still downloaded): {download_exc}")
                    # Check if file exists even if there was an exception
                    if sanitized_filename:
                        # Try to find the file that might have been downloaded
                        possible_files = list(download_dir.glob(f"{sanitized_filename}*"))
                        if possible_files:
                            target_path = possible_files[0]
                            logger.info(f"📁 Found file despite exception: {target_path}")
                            file_exists = target_path.exists() and target_path.stat().st_size > 0
                            if not file_exists:
                                return False, f"Error during download: {download_exc}"
                            # Continue to file storage code below (don't return)
                        else:
                            logger.error(f"❌ No file found after download exception")
                            return False, f"Error during download: {download_exc}"
                    else:
                        return False, f"Error during download: {download_exc}"
            except Exception as exc:  # noqa: BLE001
                logger.error(f"❌ Error during download process: {exc}", exc_info=True)
                # Even if there's an error, check if file was downloaded
                if sanitized_filename:
                    possible_files = list(download_dir.glob(f"{sanitized_filename}*"))
                    if possible_files:
                        target_path = possible_files[0]
                        logger.info(f"📁 Found file despite error: {target_path}")
                        file_exists = target_path.exists() and target_path.stat().st_size > 0
                        if not file_exists:
                            return False, f"Error during download: {exc}"
                        # Continue to file storage code below (don't return)
                    else:
                        return False, f"Error during download: {exc}"
                else:
                    return False, f"Error during download: {exc}"

            return True, f"Successfully processed {course_query} - {test_query}"
        else:
            logger.error(f"❌ Test was not clicked successfully for: {test_query}")
            return False, "Test was not clicked successfully"
    
    except Exception as exc:  # noqa: BLE001
        return False, f"Error processing course: {exc}"


async def process_multiple_reports(
    url: str,
    username: str,
    password: str,
    csv_rows: list[dict[str, str]],
    filename_choice: str = "test",
    keep_open_ms: int = 5000,
) -> tuple[bool, str]:
    """Process multiple course reports from CSV rows - reuses same browser session"""
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright not installed: {exc}"
    
    results = []
    success_count = 0
    error_count = 0
    
    try:
        # On Render, ensure browsers are installed before trying to use them
        if os.environ.get("RENDER"):
            logger.info("Ensuring Playwright browsers are installed...")
            ensure_playwright_browsers()
        
        async with async_playwright() as p:
            browser = None
            # Use headless mode on Render (no display available)
            headless_mode = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
            
            # Launch browser with proper configuration for Render
            try:
                # Try to launch with system chromium first
                browser = await p.chromium.launch(headless=headless_mode)
            except Exception as e1:
                logger.warning(f"Failed to launch chromium: {e1}")
                # If on Render and launch failed, try installing browsers again
                if os.environ.get("RENDER"):
                    logger.info("Browser launch failed, attempting to install browsers...")
                    ensure_playwright_browsers()
                    # Try again after installation
                    try:
                        browser = await p.chromium.launch(headless=headless_mode)
                    except Exception as e1_retry:
                        logger.error(f"Still failed after installation attempt: {e1_retry}")
                        raise e1_retry
                else:
                    try:
                        # Try with channel="chrome" if available
                        browser = await p.chromium.launch(channel="chrome", headless=headless_mode)
                    except Exception as e2:
                        logger.error(f"Failed to launch chrome channel: {e2}")
                        # Last resort: try with minimal args for Render
                        browser = await p.chromium.launch(
                            headless=headless_mode,
                            args=['--no-sandbox', '--disable-setuid-sandbox']
                        )
            
            # On Render, use /tmp for downloads instead of user Downloads folder
            if os.environ.get("RENDER"):
                download_dir = Path("/tmp/downloads")
            else:
                download_dir = get_downloads_dir()
            try:
                download_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            
            # Login once
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            
            email_selector = 'input[id="emailAddress"]'
            password_selector = 'input[id="password"]'
            
            await page.wait_for_selector(email_selector, state="visible", timeout=30000)
            await page.fill(email_selector, username)
            await page.wait_for_selector(password_selector, state="visible", timeout=10000)
            await page.fill(password_selector, password)
            
            # Click login
            clicked = False
            try:
                await page.get_by_role("button", name="Login").click()
                clicked = True
            except Exception:
                try:
                    await page.locator("button[label='Login']").click()
                    clicked = True
                except Exception:
                    try:
                        await page.locator("button.form__button:has-text('Login')").click()
                        clicked = True
                    except Exception:
                        try:
                            await page.click("button[type='submit']")
                            clicked = True
                        except Exception:
                            await page.press(password_selector, "Enter")
            
            # Wait for navigation after login
            await page.wait_for_load_state("networkidle", timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Navigate to Courses page once
            await page.wait_for_selector("div.left-menu", state="visible", timeout=30000)
            await page.wait_for_timeout(1000)
            
            try:
                course_locator = page.locator("div.left-menu li[ptooltip='Courses']")
                await course_locator.wait_for(state="visible", timeout=30000)
                await course_locator.first.click()
            except Exception:
                try:
                    course_locator = page.locator("div.left-menu li.each-tool[ptooltip='Courses']")
                    await course_locator.first.click()
                except Exception:
                    pass
            
            await page.wait_for_timeout(2000)
            
            # Process each row
            for idx, row in enumerate(csv_rows, 1):
                course_query = row.get("course_name", "").strip()
                module_query = row.get("module_name", "").strip()
                test_query = row.get("test_name", "").strip()
                
                if not course_query or not module_query or not test_query:
                    error_count += 1
                    results.append(f"Row {idx}: Missing required fields")
                    continue
                
                try:
                    logger.info(f"🔄 Processing course {idx}/{len(csv_rows)}: {course_query} - {test_query}")
                    logger.info(f"📞 About to call process_single_course_in_session...")
                    logger.info(f"📋 Parameters: course={course_query}, module={module_query}, test={test_query}, download_dir={download_dir}")
                    try:
                        ok, msg = await process_single_course_in_session(
                            page,
                            download_dir,
                            course_query,
                            module_query,
                            test_query,
                            filename_choice=filename_choice,
                        )
                        logger.info(f"📞 process_single_course_in_session returned: ok={ok}, msg={msg[:100] if msg else 'None'}")
                    except Exception as func_exc:
                        logger.error(f"❌ Exception INSIDE process_single_course_in_session: {func_exc}", exc_info=True)
                        ok, msg = False, f"Exception in process_single_course_in_session: {func_exc}"
                    
                    if ok:
                        success_count += 1
                        results.append(f"Row {idx}: Success - {course_query} - {test_query}")
                        logger.info(f"✅ Course {idx} completed successfully. Current RECENT_FILE_IDS count: {len(RECENT_FILE_IDS)}, DOWNLOADED_FILES count: {len(DOWNLOADED_FILES)}")
                        
                        # Go back to Courses page for next iteration
                        is_render_env = os.environ.get("RENDER") or str(download_dir).startswith("/tmp")
                        wait_before_nav = 5000 if is_render_env else 2000
                        await page.wait_for_timeout(wait_before_nav)
                        try:
                            course_locator = page.locator("div.left-menu li[ptooltip='Courses']")
                            nav_timeout = 30000 if is_render_env else 10000
                            await course_locator.wait_for(state="visible", timeout=nav_timeout)
                            await course_locator.first.click()
                            wait_after_nav = 5000 if is_render_env else 2000
                            await page.wait_for_timeout(wait_after_nav)
                            # Wait for page to load after navigation
                            try:
                                await page.wait_for_load_state("networkidle", timeout=nav_timeout)
                            except Exception:
                                pass
                        except Exception as nav_exc:
                            logger.warning(f"⚠️ Navigation back to Courses failed: {nav_exc}")
                            pass
                    else:
                        error_count += 1
                        results.append(f"Row {idx}: Failed - {msg}")
                        logger.warning(f"❌ Course {idx} failed: {msg}")
                    
                    await page.wait_for_timeout(1000)
                    
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    results.append(f"Row {idx}: Error - {exc}")
                    logger.error(f"❌ Exception processing course {idx}: {exc}", exc_info=True)
            
            # Close browser after all rows are processed
            await browser.close()
            
            # Log final state
            logger.info(f"🏁 Batch processing completed. Final state: RECENT_FILE_IDS={len(RECENT_FILE_IDS)}, DOWNLOADED_FILES={len(DOWNLOADED_FILES)}")
            if len(RECENT_FILE_IDS) > 0:
                logger.info(f"📋 Files in notification list: {[f['filename'] for f in RECENT_FILE_IDS[:5]]}")
    
    except Exception as exc:  # noqa: BLE001
        error_count += len(csv_rows) - success_count
        results.append(f"Critical error: {exc}")
        logger.error(f"❌ Critical error in batch processing: {exc}", exc_info=True)
    
    summary = f"Processed {len(csv_rows)} rows: {success_count} successful, {error_count} failed"
    logger.info(f"📊 Batch processing summary: {summary}")
    return success_count > 0, summary + "\n" + "\n".join(results)


@app.get("/")
def index():
    return render_template("index.html", status=None)

@app.get("/api/recent-files")
def get_recent_files():
    """Get recent file downloads for notification system"""
    # Return all files (no time filter - files are already limited to last 50)
    current_time = time.time()
    recent = []
    
    logger.info(f"API called: RECENT_FILE_IDS has {len(RECENT_FILE_IDS)} files, DOWNLOADED_FILES has {len(DOWNLOADED_FILES)} files")
    
    # Process all files in RECENT_FILE_IDS
    for idx, f in enumerate(RECENT_FILE_IDS):
        try:
            # Validate file structure
            if not isinstance(f, dict):
                logger.error(f"File at index {idx} is not a dict: {type(f)}")
                continue
                
            file_id = f.get("file_id")
            filename = f.get("filename", "unknown")
            created = f.get("created", 0)
            
            if not file_id:
                logger.error(f"File at index {idx} missing file_id: {f}")
                continue
            
            time_diff = current_time - created
            recent.append({
                "file_id": file_id,
                "filename": filename,
                "time_ago": int(time_diff)
            })
            age_minutes = int(time_diff) // 60
            logger.info(f"Added file {idx+1}: {filename} (ID: {file_id[:8]}...) - {age_minutes} minutes old")
        except Exception as e:
            logger.error(f"Error processing file at index {idx} in RECENT_FILE_IDS: {e}, file data: {f}", exc_info=True)
    
    logger.info(f"API response: Returning {len(recent)} files from {len(RECENT_FILE_IDS)} total recent files")
    
    return jsonify({"files": recent})


@app.get("/download-sample-csv")
def download_sample_csv():
    """Generate and download a sample CSV file for batch processing"""
    # Create sample CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header row
    writer.writerow(["course_name", "module_name", "test_name"])
    
    # Write sample data rows
    writer.writerow(["Intro to Safety", "Week 1", "2025_NEC_MBA_Practice Test 1"])
    writer.writerow(["Advanced Safety", "Week 2", "2025_NEC_MBA_Practice Test 2"])
    writer.writerow(["Safety Management", "Week 3", "2025_NEC_MBA_Practice Test 3"])
    
    # Create BytesIO object for file download
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8-sig'))  # Use utf-8-sig for Excel compatibility
    mem.seek(0)
    
    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name='sample_course_report.csv'
    )


@app.get("/download/<file_id>")
def download_file(file_id: str):
    """Download a file that was generated by Playwright automation"""
    if file_id not in DOWNLOADED_FILES:
        flash("File not found or has expired. Please run the automation again.", category="error")
        return redirect(url_for("index"))
    
    file_info = DOWNLOADED_FILES[file_id]
    file_data = file_info["data"]
    filename = file_info["filename"]
    
    # Determine MIME type based on extension
    if filename.endswith('.xlsx'):
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif filename.endswith('.csv'):
        mimetype = 'text/csv'
    else:
        mimetype = 'application/octet-stream'
    
    return send_file(
        io.BytesIO(file_data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )


@app.post("/open")
def open_url():
    raw_url = request.form.get("url", "")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    mode = request.form.get("mode", "single").strip()
    filename_choice = request.form.get("filename_choice", "test").strip()

    # Validate common fields
    missing_fields: list[str] = []
    if not raw_url.strip():
        missing_fields.append("URL")
    if not username:
        missing_fields.append("User ID")
    if not password.strip():
        missing_fields.append("Password")

    url = normalize_url(raw_url)
    if not url:
        flash("Please enter a valid URL.", category="error")
        return redirect(url_for("index"))

    if missing_fields:
        field_list = ", ".join(missing_fields)
        flash(f"Please provide the following required fields: {field_list}.", category="error")
        return redirect(url_for("index"))

    # Handle single mode or batch mode
    if mode == "batch":
        # Handle CSV batch processing
        if "csv_file" not in request.files:
            flash("Please upload a CSV file for batch processing.", category="error")
            return redirect(url_for("index"))
        
        csv_file = request.files["csv_file"]
        if csv_file.filename == "":
            flash("Please select a CSV file to upload.", category="error")
            return redirect(url_for("index"))
        
        if not csv_file.filename.lower().endswith('.csv'):
            flash("Please upload a valid CSV file.", category="error")
            return redirect(url_for("index"))
        
        # Parse CSV file
        try:
            csv_data = csv_file.read().decode('utf-8-sig')  # Handle BOM
            csv_reader = csv.DictReader(io.StringIO(csv_data))
            
            # Validate headers
            required_headers = {"course_name", "module_name", "test_name"}
            if not required_headers.issubset(set(csv_reader.fieldnames or [])):
                flash("CSV file must contain columns: course_name, module_name, test_name", category="error")
                return redirect(url_for("index"))
            
            # Read all rows
            csv_rows = []
            for row in csv_reader:
                if any(row.get(key, "").strip() for key in required_headers):
                    csv_rows.append(row)
            
            if not csv_rows:
                flash("CSV file is empty or contains no valid data rows.", category="error")
                return redirect(url_for("index"))
            
            # Process multiple reports in background
            import threading, asyncio

            def _batch_runner():
                try:
                    asyncio.run(
                        process_multiple_reports(
                            url,
                            username,
                            password,
                            csv_rows,
                            filename_choice=filename_choice,
                            keep_open_ms=5000,
                        )
                    )
                except Exception:
                    pass

            threading.Thread(target=_batch_runner, daemon=True).start()
            ok, msg = True, f"Started processing {len(csv_rows)} course reports in the background. This may take a while."
            
        except Exception as exc:  # noqa: BLE001
            flash(f"Error reading CSV file: {exc}", category="error")
            return redirect(url_for("index"))
    
    else:
        # Handle single course processing
        course_query = (request.form.get("course") or "").strip()
        module_query = (request.form.get("module") or "").strip()
        test_query = (request.form.get("test") or "").strip()

        missing_fields = []
        if not course_query:
            missing_fields.append("Course name")
        if not module_query:
            missing_fields.append("Module name")
        if not test_query:
            missing_fields.append("Test name")

        if missing_fields:
            field_list = ", ".join(missing_fields)
            flash(f"Please provide the following required fields: {field_list}.", category="error")
            return redirect(url_for("index"))

        # If credentials given, run Playwright automation in background
        if username and password:
            import threading, asyncio

            def _runner():
                try:
                    result = asyncio.run(
                        open_and_login_with_playwright(
                            url,
                            username,
                            password,
                            course_query,
                            module_query,
                            test_query,
                            filename_choice=filename_choice,
                            keep_open_ms=300000,
                        )
                    )
                    ok, msg = result
                    logger.info(f"Playwright automation completed: {msg}")
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Error in background thread: {exc}", exc_info=True)

            threading.Thread(target=_runner, daemon=True).start()
            if os.environ.get("RENDER"):
                ok, msg = True, "Processing started in background. This may take a few minutes. Check back in a moment or check the logs."
            else:
                ok, msg = True, "Launching Chrome and attempting auto-login in the background."
        else:
            ok, msg = open_in_chrome(url)

    kind = "success" if ok else "error"
    flash(msg, category=kind)
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host=host, port=port, debug=debug)


