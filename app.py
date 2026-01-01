from __future__ import annotations

import csv
import io
import json
import os
import platform
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, send_file


app = Flask(__name__, template_folder=str(Path("templates")))
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# Server-side downloads directory
SERVER_DOWNLOADS_DIR = Path("server_downloads")
SERVER_DOWNLOADS_DIR.mkdir(exist_ok=True)

# File metadata storage (in-memory, could be replaced with database)
file_metadata: dict[str, dict] = {}

# Active process tracking for cancellation
active_processes: dict[str, dict] = {}


def get_server_downloads_dir() -> Path:
    """Get the server-side downloads directory."""
    SERVER_DOWNLOADS_DIR.mkdir(exist_ok=True)
    return SERVER_DOWNLOADS_DIR


def register_downloaded_file(filepath: Path, original_name: str, course_name: str = "", test_name: str = "") -> str:
    """Register a downloaded file and return its unique identifier."""
    file_id = f"{int(time.time())}_{filepath.name}"
    file_metadata[file_id] = {
        "filename": filepath.name,
        "original_name": original_name,
        "course_name": course_name,
        "test_name": test_name,
        "timestamp": datetime.now().isoformat(),
        "size": filepath.stat().st_size if filepath.exists() else 0,
    }
    return file_id


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


async def download_performance_participation_report(
    page, download_dir: Path, sanitized_filename: str | None,
    course_query: str, test_query: str
):
    """Download Performance and Participation Report - existing flow"""
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

        # Select Excel option and download
        await select_excel_and_download(page, download_dir, sanitized_filename, course_query, test_query)
        
        # Close dialogs after download
        await close_download_dialogs(page)
    except Exception as exc:  # noqa: BLE001
        raise Exception(f"Error in Performance and Participation Report flow: {exc}")


async def download_test_level_analysis_report(
    page, download_dir: Path, sanitized_filename: str | None,
    course_query: str, test_query: str, campus: str = "", batch: str = ""
):
    """Download Test Level Analysis Report - login is same, rest of flow to be implemented"""
    try:
        # Login flow is same as Performance and Participation Report (already completed)
        # After login, wait for page to be ready
        await page.wait_for_load_state("networkidle", timeout=60000)
        await page.wait_for_timeout(10000)  # Wait 10 seconds after login for page to fully load
        
        # Wait for the dashboard/report section to be visible
        try:
            await page.wait_for_selector("app-dashboard", state="visible", timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        
        # Step 1: Click on "Report Type" dropdown - using aria-label attribute
        report_type_dropdown_clicked = False
        
        # Wait for form-fields container first
        try:
            await page.wait_for_selector("div.form-fields", state="visible", timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        
        # Primary: Find and click the label with aria-label="Report Type"
        try:
            report_type_label = page.locator('label[aria-label="Report Type"]')
            await report_type_label.wait_for(state="visible", timeout=30000)
            await report_type_label.click()
            report_type_dropdown_clicked = True
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        
        # Fallback 1: Try clicking the dropdown by id
        if not report_type_dropdown_clicked:
            try:
                dropdown = page.locator('p-dropdown#reportdropdown')
                await dropdown.wait_for(state="visible", timeout=10000)
                await dropdown.click()
                report_type_dropdown_clicked = True
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        
        # Fallback 2: Click the label inside the dropdown
        if not report_type_dropdown_clicked:
            try:
                dropdown_label = page.locator('p-dropdown#reportdropdown label.ui-dropdown-label')
                await dropdown_label.wait_for(state="visible", timeout=10000)
                await dropdown_label.click()
                report_type_dropdown_clicked = True
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        
        # Fallback 3: Click the dropdown trigger
        if not report_type_dropdown_clicked:
            try:
                dropdown_trigger = page.locator('p-dropdown#reportdropdown .ui-dropdown-trigger')
                await dropdown_trigger.wait_for(state="visible", timeout=10000)
                await dropdown_trigger.click()
                report_type_dropdown_clicked = True
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        
        if not report_type_dropdown_clicked:
            raise Exception("Could not find or click Report Type dropdown")
        
        # Step 2: Select "Test Level Analysis" from the dropdown - EXACT same method as Performance report
        test_analysis_selected = False
        
        # Wait for dropdown panel to appear
        await page.wait_for_timeout(2000)
        
        # Primary: Try to find "Test Level Analysis" option - same pattern as Performance report
        try:
            test_analysis_option = page.locator('li.ui-dropdown-item').filter(has_text=re.compile("Test Level Analysis", re.IGNORECASE)).first
            await test_analysis_option.wait_for(state="visible", timeout=10000)
            await test_analysis_option.click()
            test_analysis_selected = True
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        
        # Fallback 1: Try finding by text "Test Level"
        if not test_analysis_selected:
            try:
                test_analysis_option = page.locator('li.ui-dropdown-item').filter(has_text=re.compile("Test Level", re.IGNORECASE)).first
                await test_analysis_option.wait_for(state="visible", timeout=10000)
                await test_analysis_option.click()
                test_analysis_selected = True
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        
        # Fallback 2: Try finding any option with "Analysis" in text
        if not test_analysis_selected:
            try:
                analysis_option = page.locator('li.ui-dropdown-item').filter(has_text=re.compile("Analysis", re.IGNORECASE)).first
                await analysis_option.wait_for(state="visible", timeout=10000)
                await analysis_option.click()
                test_analysis_selected = True
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        
        # Fallback 3: Get all options and check text content - same pattern as Performance report
        if not test_analysis_selected:
            try:
                all_options = page.locator('li.ui-dropdown-item')
                option_count = await all_options.count()
                for i in range(option_count):
                    option = all_options.nth(i)
                    option_text = await option.text_content()
                    if option_text:
                        text_lower = option_text.lower().strip()
                        if ("test level analysis" in text_lower or 
                            "testlevel analysis" in text_lower or
                            ("test" in text_lower and "level" in text_lower and "analysis" in text_lower)):
                            await option.click()
                            test_analysis_selected = True
                            await page.wait_for_timeout(2000)
                            break
            except Exception:
                pass
        
        if not test_analysis_selected:
            raise Exception("Could not find or select 'Test Level Analysis' from dropdown")
        
        # Wait for the form fields to appear after selecting report type
        await page.wait_for_load_state("networkidle", timeout=10000)
        await page.wait_for_timeout(2000)
        
        # TODO: Next steps to be implemented:
        # Step 3: Select Campus (dropdown/input field)
        # Step 4: Select Batch (dropdown/input field)
        # Step 5: Select Course name
        # Step 6: Select Test name
        # Step 7: Generate/download the report
        
        return True
    except Exception as exc:  # noqa: BLE001
        raise Exception(f"Error in Test Level Analysis Report flow: {exc}")


async def close_download_dialogs(page):
    """Close download dialogs after file is downloaded"""
    await page.wait_for_timeout(10000)  # Wait 10 seconds after download completes
    
    async def click_close_button():
        close_clicked = False
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
        
        return close_clicked
    
    # Click close button twice to close both dialogs
    try:
        first_click = await click_close_button()
        await page.wait_for_timeout(2000)
        second_click = await click_close_button()
    except Exception:
        pass


async def select_excel_and_download(
    page, download_dir: Path, sanitized_filename: str | None,
    course_query: str, test_query: str
):
    """Common function to select Excel format and download the file"""
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

    download_button = page.locator("button.download-button").first
    await download_button.wait_for(state="visible", timeout=5000)
    try:
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value
        suggested_name = download.suggested_filename
        extension = Path(suggested_name).suffix or ".xlsx"
        # Create unique filename with timestamp
        timestamp = int(time.time())
        if sanitized_filename:
            unique_filename = f"{timestamp}_{sanitized_filename}{extension}"
            # Use sanitized filename (based on user's choice) as the download name
            download_filename = f"{sanitized_filename}{extension}"
        else:
            base_name = Path(suggested_name).stem
            unique_filename = f"{timestamp}_{base_name}{extension}"
            download_filename = suggested_name
        target_path = download_dir / unique_filename
        await download.save_as(str(target_path))
        
        # Register the file with the correct filename based on user's choice
        register_downloaded_file(
            target_path,
            download_filename,  # Use the filename based on user's choice
            course_query or "",
            test_query or ""
        )
    except Exception:
        await download_button.click()


async def open_and_login_with_playwright(
    url: str,
    username: str,
    password: str,
    course_query: str | None = None,
    module_query: str | None = None,
    test_query: str | None = None,
    filename_choice: str = "test",
    report_type: str = "performance",
    keep_open_ms: int = 300000,
    process_id: str | None = None,
    campus: str = "",
    batch: str = "",
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
            
            # Store browser reference for cancellation
            if process_id and process_id in active_processes:
                active_processes[process_id]['browser'] = browser
            
            download_dir = get_server_downloads_dir()
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

                # Route based on report type - Test Level Analysis has different flow after login
                if report_type == "test_analysis":
                    # For Test Level Analysis, skip course/module/test navigation
                    # Go directly to Test Level Analysis flow after login
                    sanitized_filename = None
                    import re as _re
                    if filename_choice == "course" and (course_query or "").strip():
                        sanitized_filename = (
                            _re.sub(r"[^A-Za-z0-9._-]+", "_", course_query.strip()).strip("_") or "report"
                        )
                    elif filename_choice == "test" and (test_query or "").strip():
                        sanitized_filename = (
                            _re.sub(r"[^A-Za-z0-9._-]+", "_", test_query.strip()).strip("_") or "report"
                        )
                    
                    # Proceed to Test Level Analysis flow after login
                    await download_test_level_analysis_report(
                        page, download_dir, sanitized_filename,
                        course_query or "", test_query or "", campus, batch
                    )
                else:
                    # Performance and Participation Report flow (unchanged)
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
                            # Performance and Participation Report flow (existing)
                            await download_performance_participation_report(
                                page, download_dir, sanitized_filename,
                                course_query or "", test_query or ""
                            )
                            
                            # Click the close button after download completes
                            await page.wait_for_timeout(10000)  # Wait 10 seconds after download completes
                            
                            # Function to click the close button
                            async def click_close_button():
                                close_clicked = False
                                
                                # Strategy 1: Directly click the span.pi.pi-times element
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
                                
                                # Strategy 2: Use JavaScript
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
                                
                                return close_clicked
                            
                            # Click close button twice to close both dialogs
                            first_click = await click_close_button()
                            await page.wait_for_timeout(2000)
                            second_click = await click_close_button()
                        except Exception:
                            pass

                # Wait with periodic cancellation checks
                wait_interval = 5000  # Check every 5 seconds
                total_waited = 0
                while total_waited < keep_open_ms:
                    # Check if cancelled
                    if process_id and process_id in active_processes:
                        if active_processes[process_id].get('cancelled'):
                            # Close browser if cancelled
                            try:
                                await browser.close()
                            except Exception:
                                pass
                            return False, "Report generation was cancelled by user"
                    
                    await page.wait_for_timeout(min(wait_interval, keep_open_ms - total_waited))
                    total_waited += wait_interval

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
                    # Create unique filename with timestamp
                    timestamp = int(time.time())
                    if sanitized_filename:
                        unique_filename = f"{timestamp}_{sanitized_filename}{extension}"
                        # Use sanitized filename (based on user's choice) as the download name
                        download_filename = f"{sanitized_filename}{extension}"
                    else:
                        base_name = Path(suggested_name).stem
                        unique_filename = f"{timestamp}_{base_name}{extension}"
                        download_filename = suggested_name
                    target_path = download_dir / unique_filename
                    await download.save_as(str(target_path))
                    
                    # Register the file with the correct filename based on user's choice
                    register_downloaded_file(
                        target_path,
                        download_filename,  # Use the filename based on user's choice
                        course_query or "",
                        test_query or ""
                    )
                    
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


@app.get("/")
def index():
    return render_template("index.html", status=None)


@app.get("/api/downloads")
def list_downloads():
    """API endpoint to list all available downloaded files."""
    files = []
    for file_id, metadata in file_metadata.items():
        file_path = SERVER_DOWNLOADS_DIR / metadata["filename"]
        if file_path.exists():
            files.append({
                "id": file_id,
                "filename": metadata["original_name"],
                "course_name": metadata.get("course_name", ""),
                "test_name": metadata.get("test_name", ""),
                "timestamp": metadata["timestamp"],
                "size": metadata["size"],
            })
    # Sort by timestamp, newest first
    files.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"files": files})


@app.post("/api/cancel-generation")
def cancel_generation():
    """Cancel the current report generation process and close browser"""
    try:
        import asyncio
        
        # Mark all active processes as cancelled and close browsers
        cancelled_count = 0
        browsers_closed = 0
        
        for process_id, process_info in list(active_processes.items()):
            try:
                process_info['cancelled'] = True
                
                # Close browser if it exists
                browser = process_info.get('browser')
                if browser:
                    try:
                        # Close browser asynchronously
                        async def close_browser():
                            try:
                                await browser.close()
                            except Exception:
                                pass
                        
                        # Try to close the browser
                        try:
                            # Check if there's a running event loop
                            try:
                                loop = asyncio.get_running_loop()
                                # If loop is running, schedule the close
                                asyncio.create_task(close_browser())
                                browsers_closed += 1
                            except RuntimeError:
                                # No running loop, create a new one
                                asyncio.run(close_browser())
                                browsers_closed += 1
                        except Exception:
                            pass
                    except Exception:
                        pass
                
                cancelled_count += 1
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "message": f"Cancelled {cancelled_count} process(es) and closed browser(s)"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error cancelling generation: {str(e)}"
        }), 500


@app.post("/api/downloads/<file_id>/remove")
def remove_download(file_id: str):
    """Remove a file from the notification list after successful download."""
    if file_id in file_metadata:
        file_metadata.pop(file_id, None)
        return jsonify({"success": True, "message": "File removed from list"})
    return jsonify({"success": False, "message": "File not found"}), 404


@app.get("/download/<file_id>")
def download_file(file_id: str):
    """Download a file by its ID. File remains on server until explicitly removed."""
    if file_id not in file_metadata:
        return jsonify({"error": "File not found"}), 404
    
    metadata = file_metadata[file_id]
    file_path = SERVER_DOWNLOADS_DIR / metadata["filename"]
    
    if not file_path.exists():
        # Remove from metadata if file doesn't exist
        file_metadata.pop(file_id, None)
        return jsonify({"error": "File no longer exists on server"}), 404
    
    # Don't remove from metadata here - let the frontend handle it after successful download
    # This ensures the file can be re-downloaded if needed
    
    # Ensure proper headers for cross-platform download to Downloads folder
    # Encode filename properly for cross-platform compatibility
    import urllib.parse
    encoded_filename = urllib.parse.quote(metadata["original_name"])
    
    response = send_file(
        file_path,
        as_attachment=True,
        download_name=metadata["original_name"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # Set Content-Disposition header to ensure browser saves to Downloads folder
    # Use both quoted and unquoted versions for maximum compatibility
    response.headers['Content-Disposition'] = (
        f'attachment; filename="{metadata["original_name"]}"; '
        f'filename*=UTF-8\'\'{encoded_filename}'
    )
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    
    return response


@app.post("/open")
def open_url():
    raw_url = request.form.get("url", "")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    report_type = request.form.get("report_type", "performance").strip()
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

    # Validate fields based on report type
    if report_type == "test_analysis":
        # Test Level Analysis Report fields
        campus = (request.form.get("campus") or "").strip()
        batch = (request.form.get("batch") or "").strip()
        course_query = (request.form.get("course") or "").strip()
        test_query = (request.form.get("test") or "").strip()
        module_query = ""  # Not needed for test analysis
        
        missing_fields = []
        if not campus:
            missing_fields.append("Campus")
        if not batch:
            missing_fields.append("Batch")
        if not course_query:
            missing_fields.append("Course name")
        if not test_query:
            missing_fields.append("Test name")
    else:
        # Performance and Participation Report fields
        course_query = (request.form.get("course") or "").strip()
        module_query = (request.form.get("module") or "").strip()
        test_query = (request.form.get("test") or "").strip()
        campus = ""
        batch = ""
        
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

        process_id = str(uuid.uuid4())
        
        def _runner():
            try:
                # Check if cancelled before starting
                if process_id in active_processes and active_processes[process_id].get('cancelled'):
                    return
                
                asyncio.run(
                    open_and_login_with_playwright(
                        url,
                        username,
                        password,
                        course_query,
                        module_query,
                        test_query,
                        filename_choice=filename_choice,
                        report_type=report_type,
                        keep_open_ms=300000,
                        process_id=process_id,
                        campus=campus if report_type == "test_analysis" else "",
                        batch=batch if report_type == "test_analysis" else "",
                    )
                )
            except Exception:
                pass
            finally:
                # Remove from active processes when done
                active_processes.pop(process_id, None)

        thread = threading.Thread(target=_runner, daemon=True)
        active_processes[process_id] = {
            'thread': thread,
            'cancelled': False,
            'started_at': time.time()
        }
        thread.start()
        ok, msg = True, "Launching Chrome and attempting auto-login in the background."
    else:
        ok, msg = open_in_chrome(url)

    kind = "success" if ok else "error"
    flash(msg, category=kind)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)


