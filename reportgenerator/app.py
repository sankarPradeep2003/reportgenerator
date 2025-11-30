from __future__ import annotations

import csv
import io
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, redirect, url_for, flash, send_file


app = Flask(__name__, template_folder=str(Path("templates")))
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")


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
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright not installed: {exc}"

    try:
        async with async_playwright() as p:
            # Prefer the user's installed Google Chrome; fallback to bundled Chromium
            browser = None
            try:
                browser = await p.chromium.launch(channel="chrome", headless=False)
            except Exception:
                browser = await p.chromium.launch(headless=False)
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

                return True, f"Opened in Chrome, logged in, navigated to Courses, and opened the course. Browser kept open for {(keep_open_ms//6000)} min."
            except Exception as exc:  # noqa: BLE001
                return False, f"Failed to fill login fields: {exc}. Please check if the page loaded correctly."
    except Exception as exc:  # noqa: BLE001
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
    try:
        # Use EXACT same flow from open_and_login_with_playwright starting from course search
        # If a course query was provided, focus search and type it
        if (course_query or "").strip():
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

        # If a module was supplied, click the matching module in the sidebar - EXACT same code
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
                except Exception:
                    await download_button.click()
            except Exception as exc:  # noqa: BLE001
                return False, f"Error during download: {exc}"

            return True, f"Successfully processed {course_query} - {test_query}"
        else:
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
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright not installed: {exc}"
    
    results = []
    success_count = 0
    error_count = 0
    
    try:
        async with async_playwright() as p:
            browser = None
            try:
                browser = await p.chromium.launch(channel="chrome", headless=False)
            except Exception:
                browser = await p.chromium.launch(headless=False)
            
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
                    ok, msg = await process_single_course_in_session(
                        page,
                        download_dir,
                        course_query,
                        module_query,
                        test_query,
                        filename_choice=filename_choice,
                    )
                    
                    if ok:
                        success_count += 1
                        results.append(f"Row {idx}: Success - {course_query} - {test_query}")
                        
                        # Go back to Courses page for next iteration
                        await page.wait_for_timeout(2000)
                        try:
                            course_locator = page.locator("div.left-menu li[ptooltip='Courses']")
                            await course_locator.wait_for(state="visible", timeout=10000)
                            await course_locator.first.click()
                            await page.wait_for_timeout(2000)
                        except Exception:
                            pass
                    else:
                        error_count += 1
                        results.append(f"Row {idx}: Failed - {msg}")
                    
                    await page.wait_for_timeout(1000)
                    
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    results.append(f"Row {idx}: Error - {exc}")
            
            # Close browser after all rows are processed
            await browser.close()
    
    except Exception as exc:  # noqa: BLE001
        error_count += len(csv_rows) - success_count
        results.append(f"Critical error: {exc}")
    
    summary = f"Processed {len(csv_rows)} rows: {success_count} successful, {error_count} failed"
    return success_count > 0, summary + "\n" + "\n".join(results)


@app.get("/")
def index():
    return render_template("index.html", status=None)


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
                    asyncio.run(
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
                except Exception:
                    pass

            threading.Thread(target=_runner, daemon=True).start()
            ok, msg = True, "Launching Chrome and attempting auto-login in the background."
        else:
            ok, msg = open_in_chrome(url)

    kind = "success" if ok else "error"
    flash(msg, category=kind)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)


