import re
import time
import os
import csv
import json
from datetime import datetime
from pathlib import Path
import traceback
import urllib.parse
import urllib.request
import urllib.error
from html import unescape
# from naukri_credentials import EMAIL, PASSWORD
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
)
from webdriver_manager.chrome import ChromeDriverManager
HEADLESS_MODE = False

EMAIL = "dheeraj25062003@gmail.com"
PASSWORD = "***REMOVED***"
COOKIE_FILE = "naukri_cookies.json"

MAX_JOBS_TO_APPLY = 10
MAX_JOBS_TO_CHECK = 100   # total jobs to open across all pages, applied or skipped
MAX_SCROLLS_TO_LOAD_JOBS = 10
MAX_PAGES = 3       # how many result pages to walk through before giving up
SEARCH_KEYWORD = "data engineer"
FRESHNESS_DAYS = 7    # Naukri's "jobAge" filter: 1, 3, 7, 15, 30
EXPERIENCE_YEARS = 2    # Naukri's "experience" filter, in years (0-30)

CHAT_API_URL = os.getenv("CHAT_API_URL", "http://127.0.0.1:8000/chat_naukari")
SCORE_API_URL = os.getenv("SCORE_API_URL", "http://127.0.0.1:8000/score")
MAX_FORM_QUESTIONS = 15
AFTER_ANSWER_WAIT_SECONDS = 45  # wait for next question, always under 1 minute

SCORE_FILTER_ENABLED = True # Turn this on to score resume vs JD and apply only when score >= MIN_MATCH_SCORE.
MIN_MATCH_SCORE = 55 # Minimum score to apply to a job

EXCLUDED_COMPANIES = ['infosys','mfilterit'] # Companies to skip. Matched case-insensitively as a substring, so "infosys" also skips "Infosys Limited". Leave empty to process all.
COMPANY_SITE_JOBS_FILE = "company_site_jobs.csv" # Jobs that pass the score check but only offer "Apply on company site".
LOCATION_FILTER_ENABLED = False # True: tick the LOCATIONS below in the sidebar. False: search all locations.

LOCATIONS = {
    "noida":         ["noida"],
    "greater noida": ["greater noida"],
    "delhi":         ["delhi / ncr", "delhi", "new delhi"],
    "gurugram":      ["gurugram", "gurgaon", "gurugram/gurgaon", "gurgaon/gurugram"],
}


# =========================================================
# Driver setup
# =========================================================
def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    return driver


# =========================================================
# Cookies
# =========================================================
def save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=4)
        print("Cookies saved")
    except Exception:
        print("Could not save cookies")
        traceback.print_exc()


def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
        for cookie in cookies:
            try:
                cookie.pop("sameSite", None)
                driver.add_cookie(cookie)
            except Exception as e:
                print("Cookie error:", e)
        print("Cookies loaded")
        return True
    except Exception:
        print("Could not load cookies")
        traceback.print_exc()
        return False


# =========================================================
# Login
# =========================================================
def login(driver):
    driver.get("https://www.naukri.com")
    time.sleep(3)

    if os.path.exists(COOKIE_FILE):
        print("Trying saved cookies...")
        load_cookies(driver)
        driver.refresh()
        time.sleep(5)

        if "nlogin" not in driver.current_url:
            print("Login successful using cookies")
            return

    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 20)

    try:
        email = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
        email.send_keys(EMAIL)

        password = driver.find_element(By.ID, "passwordField")
        password.send_keys(PASSWORD)

        login_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Login')]")
        login_btn.click()

        time.sleep(8)
        print("Login successful")
        save_cookies(driver)

    except Exception:
        print("Login failed")
        traceback.print_exc()


# =========================================================
# Build search URL (keyword + experience + freshness).
# Locations are chosen through the sidebar UI, because the URL
# only reliably carries ONE city (that is why only Noida stuck).
# =========================================================
def build_search_url(page=1):
    """
    Naukri encodes the page number in the path:
      /data-engineer-jobs      -> page 1
      /data-engineer-jobs-2    -> page 2
    """
    params = {
        "k": SEARCH_KEYWORD,
        "jobAge": str(FRESHNESS_DAYS),
        "experience": str(EXPERIENCE_YEARS),
    }
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    slug = SEARCH_KEYWORD.strip().lower().replace(" ", "-")
    path = f"{slug}-jobs" if page == 1 else f"{slug}-jobs-{page}"
    return f"https://www.naukri.com/{path}?{query_string}"


# =========================================================
# Location filter (sidebar checkboxes, selects ALL configured cities)
# =========================================================
LOCATION_SECTION_XPATH = (
    "//div[contains(@class,'styles_filterContainer')]"
    "[.//div[contains(@class,'styles_filterHeading')]"
    "//span[normalize-space()='Location' or normalize-space()='Locations']]"
)


def _clean_label(text):
    """'Delhi / NCR (1234)' -> ['delhi', 'ncr'] parts plus the full cleaned string."""
    text = (text or "").lower()
    text = re.sub(r"\(.*?\)", "", text)       # drop counts like (120)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _label_matches(label_text, aliases):
    cleaned = _clean_label(label_text)
    if not cleaned:
        return False
    parts = [p.strip() for p in cleaned.split("/")]
    for alias in aliases:
        if cleaned == alias or alias in parts:
            return True
    return False


def _get_location_section(driver):
    try:
        return driver.find_element(By.XPATH, LOCATION_SECTION_XPATH)
    except NoSuchElementException:
        return None


def _expand_section_if_collapsed(driver, section):
    try:
        arrow = section.find_element(
            By.CSS_SELECTOR, "[class*='filterHeading'] i[data-opened]"
        )
        if arrow.get_attribute("data-opened") == "false":
            heading = section.find_element(By.CSS_SELECTOR, "[class*='filterHeading']")
            driver.execute_script("arguments[0].click();", heading)
            time.sleep(1)
            print("  Expanded the Location filter panel")
    except NoSuchElementException:
        pass


def _click_view_more(driver, section):
    """Shows the hidden cities (e.g. Greater Noida) if a 'View More' link exists."""
    try:
        candidates = section.find_elements(
            By.XPATH,
            ".//*[self::a or self::span or self::button]"
            "[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),'view more')]",
        )
        for c in candidates:
            if c.is_displayed():
                driver.execute_script("arguments[0].click();", c)
                time.sleep(1)
                print("  Clicked 'View More' in Location filter")
                return True
    except Exception:
        pass
    return False


def _find_location_label(driver, aliases):
    """Returns the matching <label> element or None. Searches the Location section first."""
    section = _get_location_section(driver)
    scope = section if section is not None else driver

    for label in scope.find_elements(By.XPATH, ".//label"):
        try:
            text = label.get_attribute("textContent")
            if _label_matches(text, aliases):
                return label
        except StaleElementReferenceException:
            continue
    return None


def _label_is_checked(driver, label):
    try:
        input_id = label.get_attribute("for")
        if input_id:
            return driver.find_element(By.ID, input_id).is_selected()
        inner = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        return inner.is_selected()
    except Exception:
        return False


def apply_location_filter(driver, locations=LOCATIONS):
    """
    Ticks every configured location in the sidebar, one by one.
    After each click it waits for the results to reload and re-finds
    the elements (the DOM is re-rendered every time).
    """
    wait = WebDriverWait(driver, 15)
    selected, missing = [], []

    try:
        wait.until(EC.presence_of_element_located((By.XPATH, LOCATION_SECTION_XPATH)))
    except TimeoutException:
        print("Could not find the Location filter section")
        driver.save_screenshot("debug_location_filter_not_found.png")
        return False

    section = _get_location_section(driver)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", section)
    time.sleep(0.5)
    _expand_section_if_collapsed(driver, section)

    for name, aliases in locations.items():
        try:
            label = _find_location_label(driver, aliases)

            # Not visible? Try expanding 'View More' then search again
            if label is None:
                section = _get_location_section(driver)
                if section is not None and _click_view_more(driver, section):
                    label = _find_location_label(driver, aliases)

            if label is None:
                print(f"  Location option NOT found: {name}")
                missing.append(name)
                continue

            if _label_is_checked(driver, label):
                print(f"  Location already selected: {name}")
                selected.append(name)
                continue

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", label)
            time.sleep(0.4)
            driver.execute_script("arguments[0].click();", label)
            print(f"  Selected location: {name}")
            selected.append(name)
            time.sleep(4)  # let results reload before the next click

        except StaleElementReferenceException:
            print(f"  Stale element while selecting {name} — retrying once")
            time.sleep(2)
            try:
                label = _find_location_label(driver, aliases)
                if label is not None:
                    driver.execute_script("arguments[0].click();", label)
                    selected.append(name)
                    time.sleep(4)
                else:
                    missing.append(name)
            except Exception:
                missing.append(name)
        except Exception:
            print(f"  Error selecting location {name}")
            traceback.print_exc()
            missing.append(name)

    print(f"  Locations selected: {selected}")
    if missing:
        print(f"  WARNING - locations not found/selected: {missing}")
        driver.save_screenshot("debug_location_missing.png")
    print("  Current URL:", driver.current_url)
    return not missing


def verify_location_filter(driver, locations=LOCATIONS):
    """Returns the list of configured locations that are NOT currently ticked."""
    not_checked = []
    for name, aliases in locations.items():
        try:
            label = _find_location_label(driver, aliases)
            if label is None or not _label_is_checked(driver, label):
                not_checked.append(name)
        except Exception:
            not_checked.append(name)
    return not_checked


# =========================================================
# Freshness filter
# =========================================================
def _freshness_is_set(driver, days):
    """Checks BOTH the button label and the URL param."""
    label_ok = False
    try:
        label = driver.find_element(By.ID, "filter-freshness").text.strip()
        print(f"  Freshness filter reads: '{label}'")
        label_ok = bool(re.search(rf"\b{days}\b", label)) and "select" not in label.lower()
    except NoSuchElementException:
        print("  Could not read freshness label")

    url_ok = f"jobAge={days}" in driver.current_url
    return label_ok or url_ok


def apply_freshness_filter(driver, days=1):
    """
    Clicks the Freshness dropdown and selects 'Last N day(s)'.

      button id="filter-freshness"
      a data-id="filter-freshness-{30|15|7|3|1}"
    """
    wait = WebDriverWait(driver, 15)

    try:
        filter_btn = wait.until(EC.presence_of_element_located((By.ID, "filter-freshness")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filter_btn)
        time.sleep(0.5)

        if _freshness_is_set(driver, days):
            print(f"  Freshness already set to {days} day(s)")
            return True

        for attempt in range(1, 4):
            print(f"  Applying freshness (attempt {attempt})")
            filter_btn = driver.find_element(By.ID, "filter-freshness")

            # Open the dropdown: click, then hover as a fallback
            try:
                filter_btn.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", filter_btn)
            try:
                ActionChains(driver).move_to_element(filter_btn).perform()
            except Exception:
                pass
            time.sleep(1)

            option_selector = f"a[data-id='filter-freshness-{days}']"
            try:
                option = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, option_selector))
                )
                driver.execute_script("arguments[0].click();", option)
                print(f"  Clicked freshness option: Last {days} day(s)")
            except TimeoutException:
                print("  Freshness option not found in dropdown")
                continue

            time.sleep(4)  # let results re-render
            if _freshness_is_set(driver, days):
                print("  Current URL:", driver.current_url)
                return True

        print("  WARNING: freshness filter could not be confirmed")
        driver.save_screenshot("debug_freshness.png")
        print("  Current URL:", driver.current_url)
        return False

    except TimeoutException:
        print("Could not find the freshness filter button")
        driver.save_screenshot("debug_freshness_not_found.png")
        return False
    except Exception:
        print("Unexpected error applying freshness filter")
        traceback.print_exc()
        return False


# =========================================================
# Experience filter (results-page rc-slider, not a dropdown)
# =========================================================
EXPERIENCE_FILTER_SECTION_XPATH = (
    "//div[contains(@class,'styles_filterHeading')]"
    "//span[normalize-space()='Experience']"
    "/ancestor::div[contains(@class,'styles_filterContainer')][1]"
)
EXPERIENCE_MIN_YEARS = 0
EXPERIENCE_MAX_YEARS = 30


def _read_experience_slider_value(filter_section):
    handle = filter_section.find_element(By.CSS_SELECTOR, ".handle")
    label = handle.find_element(By.CSS_SELECTOR, ".inside span").text.strip()
    return handle, label


def _ensure_experience_filter_expanded(driver, filter_section):
    try:
        arrow = filter_section.find_element(
            By.CSS_SELECTOR, "[class*='filterHeading'] i[data-opened]"
        )
        if arrow.get_attribute("data-opened") == "false":
            heading = filter_section.find_element(By.CSS_SELECTOR, "[class*='filterHeading']")
            driver.execute_script("arguments[0].click();", heading)
            time.sleep(1)
            print("  Expanded the Experience filter panel")
    except NoSuchElementException:
        pass


def _move_slider_via_keyboard(driver, handle, steps, key):
    try:
        ActionChains(driver).move_to_element(handle).click().perform()
        time.sleep(0.3)
        driver.execute_script("arguments[0].focus();", handle)
        time.sleep(0.2)

        for _ in range(steps):
            ActionChains(driver).send_keys(key).perform()
            time.sleep(0.15)
        return True
    except Exception:
        print("  Keyboard control of the slider raised an error")
        traceback.print_exc()
        return False


def _move_slider_via_drag(driver, filter_section, handle, current_value, target_value):
    try:
        rail = filter_section.find_element(By.CSS_SELECTOR, ".rc-slider")
        rail_width = rail.size.get("width", 0)
        if not rail_width:
            print("  Could not measure slider rail width — skipping drag fallback")
            return False

        pixels_per_year = rail_width / (EXPERIENCE_MAX_YEARS - EXPERIENCE_MIN_YEARS)
        offset_px = round((target_value - current_value) * pixels_per_year)

        print(f"  Dragging slider handle by {offset_px}px ({rail_width}px rail)")
        ActionChains(driver).click_and_hold(handle).move_by_offset(offset_px, 0).release().perform()
        time.sleep(1)
        return True
    except Exception:
        print("  Drag fallback raised an error")
        traceback.print_exc()
        return False


def verify_experience_filter(driver, years):
    ok = False
    try:
        filter_section = driver.find_element(By.XPATH, EXPERIENCE_FILTER_SECTION_XPATH)
        _, label = _read_experience_slider_value(filter_section)
        print(f"  Experience slider now reads: '{label}'")
        ok = label == str(years)
        if not ok:
            print("  WARNING: experience slider value does not match target")
    except NoSuchElementException:
        print("  Could not read experience slider value back")
    return ok


def apply_experience_filter(driver, years=2):
    wait = WebDriverWait(driver, 15)

    try:
        filter_section = wait.until(
            EC.presence_of_element_located((By.XPATH, EXPERIENCE_FILTER_SECTION_XPATH))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filter_section)
        time.sleep(0.5)

        _ensure_experience_filter_expanded(driver, filter_section)

        filter_section = driver.find_element(By.XPATH, EXPERIENCE_FILTER_SECTION_XPATH)
        handle, current_label = _read_experience_slider_value(filter_section)
        current_value = int(current_label) if current_label.isdigit() else EXPERIENCE_MIN_YEARS
        print(f"  Experience slider currently at {current_value} yr(s), target {years} yr(s)")

        if current_value == years:
            print("  Experience filter already at target value")
            return True

        diff = years - current_value
        key = Keys.ARROW_RIGHT if diff > 0 else Keys.ARROW_LEFT
        steps = abs(diff)

        _move_slider_via_keyboard(driver, handle, steps, key)
        time.sleep(2)

        if verify_experience_filter(driver, years):
            return True

        print("  Slider did not reach target via keyboard — trying drag fallback")
        filter_section = driver.find_element(By.XPATH, EXPERIENCE_FILTER_SECTION_XPATH)
        handle, current_label = _read_experience_slider_value(filter_section)
        current_value = int(current_label) if current_label.isdigit() else EXPERIENCE_MIN_YEARS

        if current_value != years:
            _move_slider_via_drag(driver, filter_section, handle, current_value, years)
            time.sleep(2)

        return verify_experience_filter(driver, years)

    except TimeoutException:
        print("Could not find the Experience slider filter")
        driver.save_screenshot("debug_experience_filter_not_found.png")
        return False
    except NoSuchElementException:
        print("Experience filter markup did not match expected structure")
        driver.save_screenshot("debug_experience_filter_markup.png")
        return False
    except Exception:
        print("Unexpected error applying experience filter")
        traceback.print_exc()
        return False


# =========================================================
# Apply ALL filters in a safe order
# =========================================================
def apply_all_filters(driver):
    """
    Order matters: every filter change re-renders the results and can
    reset an earlier one, so we do location -> experience -> freshness,
    then re-check everything and repair anything that got dropped.
    """
    print("\n--- Applying filters ---")
    if LOCATION_FILTER_ENABLED:
        apply_location_filter(driver)
    else:
        print("  Location filter is OFF — searching all locations")
    apply_experience_filter(driver, years=EXPERIENCE_YEARS)
    apply_freshness_filter(driver, days=FRESHNESS_DAYS)

    # Final verification + one repair pass
    for round_num in range(1, 3):
        problems = []

        if LOCATION_FILTER_ENABLED:
            not_checked = verify_location_filter(driver)
            if not_checked:
                problems.append(("location", not_checked))
        if not verify_experience_filter(driver, EXPERIENCE_YEARS):
            problems.append(("experience", None))
        if not _freshness_is_set(driver, FRESHNESS_DAYS):
            problems.append(("freshness", None))

        if not problems:
            print("--- All filters confirmed ---")
            break

        print(f"--- Repair pass {round_num}: {problems} ---")
        for kind, _ in problems:
            if kind == "location":
                apply_location_filter(driver)
            elif kind == "experience":
                apply_experience_filter(driver, years=EXPERIENCE_YEARS)
        # freshness always re-applied last
        apply_freshness_filter(driver, days=FRESHNESS_DAYS)

    print("Final URL:", driver.current_url)


# =========================================================
# Search + pagination
# =========================================================
def load_all_jobs_on_page(driver):
    """Scroll to the bottom repeatedly so Naukri lazy-loads the full page of jobs."""
    last_count = 0
    for scroll_num in range(MAX_SCROLLS_TO_LOAD_JOBS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        jobs_now = driver.find_elements(By.XPATH, "//a[contains(@class,'title')]")
        print(f"  Scroll {scroll_num + 1}: {len(jobs_now)} jobs visible in DOM")

        if len(jobs_now) == last_count:
            break
        last_count = len(jobs_now)

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)
    return last_count


def open_page(driver, page):
    """Navigate to a results page, apply all filters, then load the jobs."""
    url = build_search_url(page)
    print(f"\n########## PAGE {page} ##########")
    print("Opening:", url)
    driver.get(url)
    time.sleep(5)

    apply_all_filters(driver)
    count = load_all_jobs_on_page(driver)

    if count == 0:
        print(f"Page {page} has no job cards — likely past the last page")
        return False
    return True


def go_to_next_page(driver, next_page):
    """
    Prefer clicking Naukri's 'Next' control so all filter state
    (locations, experience, freshness) carries over.
    Falls back to loading the page URL directly and re-applying filters.
    """
    next_selectors = [
        "//a[contains(@class,'styles_btn-secondary') and .//span[normalize-space()='Next']]",
        "//a[normalize-space()='Next']",
        "//span[normalize-space()='Next']/parent::a",
    ]

    for xpath in next_selectors:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    print(f"\n########## PAGE {next_page} (via Next button) ##########")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(5)

                    count = load_all_jobs_on_page(driver)
                    print("  Current URL:", driver.current_url)
                    if count > 0:
                        return True
                    print("  Next button led to an empty page")
                    return False
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    print("\nNo usable 'Next' button — falling back to direct URL")
    return open_page(driver, next_page)


def get_job_links(driver):
    elements = driver.find_elements(By.XPATH, "//a[contains(@class,'title')]")
    results = []
    for el in elements:
        try:
            href = el.get_attribute("href")
            title = el.text.strip()
            if href:
                results.append((title, href))
        except StaleElementReferenceException:
            continue
    return results


# =========================================================
# Skip-condition checks
# =========================================================
def classify_missing_apply_button(driver):
    """When there is no #apply-button, read the header buttons to see why."""
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "#job_header button")
    except Exception:
        buttons = []
    texts = []
    for btn in buttons:
        try:
            text = (btn.text or "").strip()
            if text:
                texts.append(text)
        except StaleElementReferenceException:
            continue
    print(f"  Header buttons: {texts or '(none)'}")
    lowered = [t.lower() for t in texts]
    if any("company site" in t for t in lowered):
        return "skipped_company_site"
    if any(t.startswith("applied") or "already applied" in t for t in lowered):
        return "skipped_already_applied"
    return "failed"


def is_company_site_apply(apply_buttons):
    for btn in apply_buttons:
        try:
            text = btn.text.strip().lower()
            if "company site" in text or "external" in text:
                return True
        except StaleElementReferenceException:
            continue
    return False


CHAT_CONTAINER_SELECTORS = [
    ".chatbot_DrawerContentWrapper",
    "[class*='DrawerContentWrapper']",
    "[class*='chatbot_Drawer']",
    "[class*='chatDrawer']",
    "[class*='chat-drawer']",
    "[class*='ChatDrawer']",
    "[class*='questionnaire']",
    "[class*='Questionnaire']",
    "[class*='applyChat']",
    "div[class*='chatbot']",
    "div[class*='chat-bot']",
    "div[role='dialog']",
]


def find_chat_container(driver):
    for selector in CHAT_CONTAINER_SELECTORS:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, selector):
                if el.is_displayed():
                    return el
        except StaleElementReferenceException:
            continue
    return None


def detect_screening_questions_popup(driver, wait_seconds=4):
    """Detect a post-apply chatbot/drawer that asks screening questions."""
    time.sleep(wait_seconds)
    container = find_chat_container(driver)
    if container is None:
        return False

    try:
        controls = container.find_elements(
            By.CSS_SELECTOR,
            "input, textarea, select, [contenteditable='true'], [class*='radio'], [class*='chip']",
        )
        for el in controls:
            if el.is_displayed():
                print("  Detected screening questions in chatbot")
                return True
    except StaleElementReferenceException:
        return True

    print("  Detected screening chatbot drawer")
    return True


def close_any_open_popup(driver):
    close_selectors = [
        "button[class*='close']",
        "span[class*='close']",
        "i[class*='close']",
        "button[aria-label='close']",
    ]
    for selector in close_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(1)
                    return
        except Exception:
            continue


# =========================================================
# Fill screening form via backend /chat_naukari
# =========================================================
COMPLETION_PHRASES = (
    "thank you for your response",
    "thanks for your response",
    "thank you for applying",
    "application submitted",
    "applied successfully",
    "you have applied",
    "application sent",
    "successfully applied",
    "we have received your application",
)

INSPECT_QUESTION_JS = r"""
const container = arguments[0];
function vis(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const s = window.getComputedStyle(el);
  return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0;
}
const botMsgs = [...container.querySelectorAll('.botMsg.msg, .botMsg, li.botItem')];
let question = '';
for (let i = botMsgs.length - 1; i >= 0; i--) {
  const t = (botMsgs[i].innerText || '').replace(/\s+/g, ' ').trim();
  if (t) { question = t; break; }
}
const skip = /^(save|send|skip|close|cancel|submit|apply|next|done|type message here)$/i;
const options = [];
const seen = new Set();
function pushOpt(el, htmlEl) {
  const t = (el.innerText || el.value || '').replace(/\s+/g, ' ').trim();
  if (!t || skip.test(t) || t.includes('?') || t.length > 120) return;
  const key = t.toLowerCase();
  if (seen.has(key)) return;
  seen.add(key);
  options.push({text: t, html: (htmlEl || el).outerHTML});
}
container.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(inp => {
  let target = inp.closest('label') || inp;
  if (inp.id) {
    try {
      const lbl = container.querySelector('label[for="' + CSS.escape(inp.id) + '"]');
      if (lbl) target = lbl;
    } catch (e) {}
  }
  if (vis(target) || vis(inp)) pushOpt(target, target);
});
container.querySelectorAll(
  '[role="radio"], [role="option"], [class*="chip"], [class*="Chip"], [class*="RadioLabel"], [class*="radioLabel"], [class*="botItem-option"]'
).forEach(el => { if (vis(el)) pushOpt(el, el); });
container.querySelectorAll('select option').forEach(opt => {
  const t = (opt.textContent || '').trim();
  const v = (opt.value || '').trim();
  if (t && v && v.toLowerCase() !== 'select') pushOpt(opt, opt);
});
const textInput = container.querySelector(
  'div.textArea[contenteditable="true"], [contenteditable="true"], textarea, input[type="text"]'
);
const hasText = !!(textInput && vis(textInput));
let type = 'unknown';
if (options.length) type = 'choice';
else if (hasText) type = 'type';
return {type, question, options, hasText};
"""

CLICK_CHOICE_BY_TEXT_JS = r"""
const wanted = (arguments[0] || '').replace(/\s+/g, ' ').trim().toLowerCase();
if (!wanted) return false;
function vis(el) {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const s = window.getComputedStyle(el);
  return s.display !== 'none' && s.visibility !== 'hidden';
}
const root = arguments[1] || document;
const nodes = root.querySelectorAll(
  'label, button, [role="button"], [role="radio"], [role="option"], [class*="chip"], [class*="Chip"], [class*="option"], [class*="RadioLabel"], [class*="radioLabel"], li, option'
);
let best = null;
for (const el of nodes) {
  if (!vis(el)) continue;
  const t = (el.innerText || el.getAttribute('value') || '').replace(/\s+/g, ' ').trim().toLowerCase();
  if (t !== wanted) continue;
  const area = el.getBoundingClientRect().width * el.getBoundingClientRect().height;
  if (!best || area < best.area) best = {el, area};
}
if (best) { best.el.click(); return true; }
return false;
"""

IS_SAVE_ENABLED_JS = r"""
const wrap = document.querySelector('.send');
const btn = document.querySelector('.sendMsg');
if (!btn) return false;
if (wrap && wrap.classList.contains('disabled')) return false;
return true;
"""

CLICK_SAVE_JS = r"""
const force = arguments[0] === true;
const wrap = document.querySelector('.send');
const btn = document.querySelector('.sendMsg');
if (!btn) return false;
if (!force && wrap && wrap.classList.contains('disabled')) return false;
if (force && wrap) wrap.classList.remove('disabled');
btn.click();
return true;
"""


def _html_to_text(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _clean_api_answer(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:html|HTML)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def is_completion_message(text):
    lowered = (text or "").strip().lower()
    if lowered == "done":
        return True
    return any(phrase in lowered for phrase in COMPLETION_PHRASES)


def ask_form_api(question):
    print("\n========== FORM API REQUEST ==========")
    print(f"URL: {CHAT_API_URL}")
    print(question)
    print("========== END REQUEST ==========\n")

    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        CHAT_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            answer = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"  Form API is not reachable at {CHAT_API_URL}: {exc}")
        print("  Start it with: uv run uvicorn main:app --reload --port 8000")
        return ""
    except Exception:
        print("  Form API request failed")
        traceback.print_exc()
        return ""

    print("\n========== FORM API RESPONSE ==========")
    print(answer)
    print("========== END RESPONSE ==========\n")
    return _clean_api_answer(answer)


def _visible_elements(container, selector):
    found = []
    try:
        for el in container.find_elements(By.CSS_SELECTOR, selector):
            try:
                if el.is_displayed():
                    found.append(el)
            except StaleElementReferenceException:
                continue
    except Exception:
        return []
    return found


def inspect_current_question(driver, container):
    try:
        data = driver.execute_script(INSPECT_QUESTION_JS, container) or {}
    except StaleElementReferenceException:
        return {"type": "unknown", "question": "", "options": [], "hasText": False}
    return {
        "type": data.get("type") or "unknown",
        "question": (data.get("question") or "").strip(),
        "options": data.get("options") or [],
        "hasText": bool(data.get("hasText")),
    }


def click_choice_by_text(driver, text, container=None):
    try:
        return bool(driver.execute_script(CLICK_CHOICE_BY_TEXT_JS, text, container))
    except StaleElementReferenceException:
        time.sleep(0.5)
        try:
            return bool(driver.execute_script(CLICK_CHOICE_BY_TEXT_JS, text, container))
        except Exception:
            return False
    except Exception:
        traceback.print_exc()
        return False


def select_dropdown_by_text(driver, text):
    container = find_chat_container(driver)
    if container is None:
        return False
    for select_el in _visible_elements(container, "select"):
        try:
            Select(select_el).select_by_visible_text(text)
            return True
        except Exception:
            try:
                for option_el in select_el.find_elements(By.TAG_NAME, "option"):
                    if _clean_label(option_el.text) == _clean_label(text):
                        option_el.click()
                        return True
            except StaleElementReferenceException:
                continue
    return False


def find_text_input(container):
    for el in _visible_elements(
        container,
        "div.textArea[contenteditable='true'], .chatbot_inputText[contenteditable='true']",
    ):
        return el
    for el in _visible_elements(container, "[contenteditable='true']"):
        return el
    for el in _visible_elements(container, "textarea"):
        return el
    for el in _visible_elements(container, "input[type='text'], input:not([type]), input[placeholder]"):
        input_type = (el.get_attribute("type") or "text").lower()
        if input_type in ("hidden", "radio", "checkbox", "submit", "button"):
            continue
        return el
    return None


def type_into_field(driver, element, text):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        element.click()
        time.sleep(0.2)
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.BACKSPACE)
        element.send_keys(text)
    except Exception:
        pass
    driver.execute_script(
        """
        const el = arguments[0];
        const value = arguments[1];
        el.focus();
        if (el.isContentEditable) {
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, value);
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true, inputType: 'insertText', data: value
            }));
            el.dispatchEvent(new Event('keyup', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            el.focus();
        } else {
            const proto = el.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            if (desc && desc.set) desc.set.call(el, value);
            else el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }
        """,
        element,
        text,
    )


def wait_for_save_enabled(driver, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.execute_script(IS_SAVE_ENABLED_JS):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def click_save_button(driver, container=None, force=False):
    try:
        if driver.execute_script(CLICK_SAVE_JS, force):
            print("  Clicked Save")
            return True
    except Exception:
        pass

    selectors = [
        ".sendMsg",
        "[class*='sendMsg']",
        "[class*='sendMsgbtn']",
        "[class*='send-msg']",
        "button[type='submit']",
    ]
    for selector in selectors:
        for el in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    print("  Clicked Save")
                    return True
            except StaleElementReferenceException:
                continue

    for el in driver.find_elements(By.XPATH, "//div[normalize-space()='Save'] | //span[normalize-space()='Save'] | //button[normalize-space()='Save']"):
        try:
            if el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
                print("  Clicked Save")
                return True
        except StaleElementReferenceException:
            continue
    print("  Save button not found")
    return False


def application_looks_complete(driver):
    try:
        page = (driver.page_source or "").lower()
        if "applied successfully" in page or "application sent" in page:
            return True
        for btn in driver.find_elements(By.CSS_SELECTOR, "button#apply-button"):
            if "applied" in (btn.text or "").lower():
                return True
    except Exception:
        return False
    return False


def apply_typed_answer(driver, container, answer):
    text_input = find_text_input(container)
    if text_input is None:
        print("  No text box found for typing question")
        return False
    type_into_field(driver, text_input, answer)
    print(f"  Typed answer: {answer}")

    if not wait_for_save_enabled(driver, timeout=5):
        print("  Save still disabled — sending Enter, then forcing Save")
        try:
            text_input.send_keys(Keys.ENTER)
            time.sleep(0.4)
        except Exception:
            pass

    if click_save_button(driver):
        print("  Saved typed response")
        return True
    if click_save_button(driver, force=True):
        print("  Saved typed response (forced)")
        return True
    print("  Could not click Save after typing")
    return False


def apply_choice_answer(driver, container, answer, options):
    option_text = _html_to_text(answer) if re.search(r"<[a-zA-Z][^>]*>", answer or "") else answer
    option_text = (option_text or "").strip()
    wanted = _clean_label(option_text)

    match_text = option_text
    for opt in options:
        opt_html = (opt.get("html") or "").strip()
        opt_text = (opt.get("text") or "").strip()
        if opt_html and answer and (opt_html in answer or answer in opt_html):
            match_text = opt_text
            break
        if wanted and _clean_label(opt_text) == wanted:
            match_text = opt_text
            break

    if select_dropdown_by_text(driver, match_text):
        print(f"  Selected dropdown: {match_text}")
        return True
    if click_choice_by_text(driver, match_text, container):
        print(f"  Selected option: {match_text}")
        return True
    print(f"  Could not click option: {match_text}")
    return False


def wait_for_next_question(driver, previous_question, timeout=AFTER_ANSWER_WAIT_SECONDS):
    print(f"  Waiting after answer (up to {timeout}s)")
    end = time.time() + timeout
    while time.time() < end:
        container = find_chat_container(driver)
        if container is None:
            return "closed"
        info = inspect_current_question(driver, container)
        current = info.get("question") or ""
        if is_completion_message(current):
            return "done"
        if current and current != previous_question:
            print("  Next question appeared")
            return "next"
        time.sleep(0.5)
    return "timeout"


def fill_screening_form(driver, max_questions=MAX_FORM_QUESTIONS):
    answered = 0
    last_question = None
    stagnant = 0

    for _ in range(max_questions):
        time.sleep(1)
        if application_looks_complete(driver):
            print("  Application marked complete")
            return True

        container = find_chat_container(driver)
        if container is None:
            if answered > 0:
                print("  Chat closed after answering — treating as success")
                return True
            print("  Screening chat disappeared before a question was answered")
            return False

        info = inspect_current_question(driver, container)
        q_type = info["type"]
        question = info["question"]
        options = info["options"]

        if is_completion_message(question):
            print("  Form completed")
            return True

        if question == last_question:
            stagnant += 1
            if stagnant >= 2:
                print("  Same question still showing — stopping")
                return answered > 0
        else:
            stagnant = 0
        last_question = question

        print(f"  Detected {q_type} question: {question[:160]}")

        try:
            if q_type == "choice":
                options_html = "\n\n".join(opt.get("html", "") for opt in options)
                payload = (
                    "SELECT QUESTION. Return ONLY the exact HTML of the correct option.\n\n"
                    f"Question: {question}\n\n"
                    f"Options HTML:\n{options_html}"
                )
                answer = ask_form_api(payload)
                if not answer or is_completion_message(answer):
                    return is_completion_message(answer) or False
                if not apply_choice_answer(driver, container, answer, options):
                    return False
                time.sleep(0.4)
                if not click_save_button(driver, container, force=True):
                    print("  Could not submit this answer")
                    return False
            elif q_type == "type":
                payload = (
                    "TYPING QUESTION. Return only the short answer to type. "
                    "One word or a short number/phrase. Do not return HTML.\n\n"
                    f"Question: {question}"
                )
                answer = ask_form_api(payload)
                if not answer or is_completion_message(answer):
                    return is_completion_message(answer) or False
                container = find_chat_container(driver)
                if container is None or not apply_typed_answer(driver, container, answer):
                    return False
            else:
                print("  Could not tell if this is a typing or select question")
                return answered > 0
        except StaleElementReferenceException:
            print("  Chat UI refreshed while answering — retrying")
            time.sleep(1)
            continue

        answered += 1
        status = wait_for_next_question(driver, question, timeout=AFTER_ANSWER_WAIT_SECONDS)
        if status == "done":
            print("  Form completed")
            return True
        if status == "closed":
            print("  Chat closed after answering — treating as success")
            return True
        if status == "timeout":
            print(f"  Next question did not appear within {AFTER_ANSWER_WAIT_SECONDS}s")

    return answered > 0


# =========================================================
# Company exclude list
# =========================================================
def get_company_name(driver):
    selectors = [
        "[class*='jd-header-comp-name'] a",
        "[class*='jd-header-comp-name']",
        "#job_header a[href*='-jobs-careers-']",
    ]
    for selector in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, selector):
                text = (el.text or "").strip()
                if text:
                    return text.splitlines()[0].strip()
        except StaleElementReferenceException:
            continue
    return ""


def is_company_excluded(company):
    name = (company or "").lower()
    if not name:
        return False
    return any(ex.strip().lower() in name for ex in EXCLUDED_COMPANIES if ex.strip())


# =========================================================
# Resume vs JD score
# =========================================================
def get_job_description(driver):
    # The hash suffix in Naukri's class names changes between deploys.
    for selector in ("section.styles_job-desc-container__txpYf", "section[class*='job-desc-container']"):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, selector):
                text = (driver.execute_script("return arguments[0].innerText;", el) or "").strip()
                if text:
                    return text
        except StaleElementReferenceException:
            continue

    selectors = [
        ".dang-inner-html",
        "[class*='dang-inner-html']",
        "[class*='job-desc']",
        "[class*='jobDesc']",
        "#jobDescription",
        "section.job-desc",
    ]
    for selector in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, selector):
                text = (el.text or "").strip()
                if len(text) > 80:
                    return text
        except StaleElementReferenceException:
            continue
    try:
        return (driver.find_element(By.TAG_NAME, "body").text or "")[:8000]
    except Exception:
        return ""


def score_resume_against_jd(title, job_description):
    payload = json.dumps({
        "title": title,
        "job_description": job_description,
    }).encode("utf-8")
    request = urllib.request.Request(
        SCORE_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        print(f"  Score API is not reachable at {SCORE_API_URL}: {exc}")
        return {"score": 0, "verdict": "score api unavailable", "reason": ""}
    except Exception:
        print("  Score API request failed")
        traceback.print_exc()
        return {"score": 0, "verdict": "score api failed", "reason": ""}

    print(f"  Score API response: {data}")
    return {
        "score": int(data.get("score", 0) or 0),
        "verdict": data.get("verdict", "unknown"),
        "reason": data.get("reason", ""),
    }


def should_apply_by_score(driver, title):
    """Returns (ok, score_result). score_result is None when scoring is off."""
    if not SCORE_FILTER_ENABLED:
        print("  Score filter is OFF — applying without JD match")
        return True, None

    jd = get_job_description(driver)
    if not jd:
        print("  Could not read job description — skipping")
        return False, None

    print(f"  Scoring resume against JD ({len(jd)} chars)")
    result = score_resume_against_jd(title, jd)
    score = result["score"]
    verdict = result["verdict"]
    print(f"  Match score: {score}/100 ({verdict})")
    if result["reason"]:
        print(f"  Reason: {result['reason']}")
    if score >= MIN_MATCH_SCORE:
        return True, result
    print(f"  Skipping: score {score} is below {MIN_MATCH_SCORE}")
    return False, result


def save_company_site_job(title, company, href, score_result):
    """Append a matched company-site job to COMPANY_SITE_JOBS_FILE, once per URL."""
    path = Path(COMPANY_SITE_JOBS_FILE)
    is_new_file = not path.exists()
    if not is_new_file:
        with path.open(newline="", encoding="utf-8") as f:
            if any(row.get("url") == href for row in csv.DictReader(f)):
                print(f"  Company-site job already saved in {path}")
                return

    score_result = score_result or {}
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["saved_at", "title", "company", "score", "verdict", "reason", "url"]
        )
        if is_new_file:
            writer.writeheader()
        writer.writerow({
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": title,
            "company": company,
            "score": score_result.get("score", ""),
            "verdict": score_result.get("verdict", ""),
            "reason": score_result.get("reason", ""),
            "url": href,
        })
    print(f"  Saved company-site job to {path}")


# =========================================================
# Apply to a single job
# =========================================================
def apply_to_single_job(driver, title, href, wait_timeout=20):
    """
    Returns one of: "applied", "skipped_company_site", "skipped_questions",
    "skipped_low_score", "skipped_excluded_company", "failed". Jobs with screening questions are filled
    via /chat_naukari. If SCORE_FILTER_ENABLED, applies only when score >= MIN_MATCH_SCORE.
    """
    original_window = driver.current_window_handle

    try:
        driver.execute_script("window.open(arguments[0]);", href)
        time.sleep(1)

        new_window = [h for h in driver.window_handles if h != original_window][-1]
        driver.switch_to.window(new_window)

        wait = WebDriverWait(driver, wait_timeout)
        wait.until(EC.presence_of_element_located((By.ID, "job_header")))
        print("  Job details loaded")
        time.sleep(2)

        company = get_company_name(driver)
        print(f"  Company: {company or '(not found)'}")
        if EXCLUDED_COMPANIES and is_company_excluded(company):
            print("  Skipping: company is in exclude list")
            return "skipped_excluded_company"

        score_ok, score_result = should_apply_by_score(driver, title)
        if not score_ok:
            return "skipped_low_score"

        apply_buttons = driver.find_elements(By.CSS_SELECTOR, "button#apply-button")
        print(f"  Found {len(apply_buttons)} apply button(s)")

        if not apply_buttons:
            reason = classify_missing_apply_button(driver)
            if reason == "skipped_company_site":
                print("  Skipping: Apply redirects to company site")
                save_company_site_job(title, company, href, score_result)
            elif reason == "skipped_already_applied":
                print("  Skipping: already applied to this job")
            else:
                safe_name = "".join(c if c.isalnum() else "_" for c in title)[:50]
                screenshot_path = f"debug_no_apply_{safe_name}.png"
                driver.save_screenshot(screenshot_path)
                print(f"  No apply button found. Screenshot: {screenshot_path}")
            return reason

        if is_company_site_apply(apply_buttons):
            print("  Skipping: Apply redirects to company site")
            save_company_site_job(title, company, href, score_result)
            return "skipped_company_site"

        clicked = False
        for idx, btn in enumerate(apply_buttons):
            try:
                displayed = btn.is_displayed()
                enabled = btn.is_enabled()
                print(f"    [{idx}] displayed={displayed} enabled={enabled} text='{btn.text}'")

                if displayed and enabled:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", btn
                    )
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
            except StaleElementReferenceException:
                continue

        if not clicked:
            safe_name = "".join(c if c.isalnum() else "_" for c in title)[:50]
            screenshot_path = f"debug_{safe_name}.png"
            driver.save_screenshot(screenshot_path)
            print(f"  No clickable Apply button. Screenshot: {screenshot_path}")
            return "failed"

        if detect_screening_questions_popup(driver):
            print("  Screening questions detected — filling via API")
            if fill_screening_form(driver):
                print("  Applied (form filled):", title)
                print("  Waiting 3 seconds after apply")
                time.sleep(3)
                return "applied"
            print("  Could not complete screening form")
            close_any_open_popup(driver)
            return "failed"

        print("  Applied:", title)
        print("  Waiting 3 seconds after apply")
        time.sleep(3)
        return "applied"

    except TimeoutException:
        print("  Timed out waiting for job page to load:", title)
        return "failed"

    except Exception:
        print("  Unexpected error on job:", title)
        traceback.print_exc()
        return "failed"

    finally:
        try:
            if driver.current_window_handle != original_window:
                driver.close()
            driver.switch_to.window(original_window)
        except Exception:
            print("  Warning: could not cleanly close job tab")


# =========================================================
# Main apply loop (walks across pages)
# =========================================================
def apply_jobs(driver):
    attempted = set()
    counts = {
        "applied": 0,
        "skipped_company_site": 0,
        "skipped_questions": 0,
        "skipped_low_score": 0,
        "skipped_excluded_company": 0,
        "skipped_already_applied": 0,
        "failed": 0,
    }

    attempts = 0
    max_attempts = MAX_JOBS_TO_CHECK
    page = 1
    pages_visited = 1

    while counts["applied"] < MAX_JOBS_TO_APPLY and attempts < max_attempts:
        job_links = get_job_links(driver)
        remaining = [(t, h) for (t, h) in job_links if h not in attempted]

        if not remaining:
            if pages_visited >= MAX_PAGES:
                print(f"\nReached MAX_PAGES ({MAX_PAGES}). Stopping.")
                break

            page += 1
            pages_visited += 1
            print(f"\nPage exhausted — moving to page {page}")

            if not go_to_next_page(driver, page):
                print("Could not load another page. Stopping.")
                break

            job_links = get_job_links(driver)
            remaining = [(t, h) for (t, h) in job_links if h not in attempted]

            if not remaining:
                print("New page had no unseen jobs. Stopping.")
                break

        title, href = remaining[0]
        attempted.add(href)
        attempts += 1

        print(f"\n[{attempts}] (page {page}) Opening: {title}")
        print(f"  Job URL: {href}")
        result = apply_to_single_job(driver, title, href)
        counts[result] += 1

        time.sleep(2)

    print("\n===== SUMMARY =====")
    print(f"Applied:                {counts['applied']}")
    print(f"Skipped (company site): {counts['skipped_company_site']}")
    print(f"Skipped (low score):    {counts['skipped_low_score']}")
    print(f"Skipped (excluded co.): {counts['skipped_excluded_company']}")
    print(f"Skipped (already appl): {counts['skipped_already_applied']}")
    print(f"Skipped (questions):    {counts['skipped_questions']}")
    print(f"Failed:                 {counts['failed']}")
    print(f"Total attempts:         {attempts}")
    print(f"Pages visited:          {pages_visited}")


# =========================================================
# Main
# =========================================================
if __name__ == "__main__":
    driver = create_driver()

    try:
        login(driver)
        open_page(driver, 1)
        apply_jobs(driver)

    except Exception:
        print("Fatal error in main flow:")
        traceback.print_exc()

    finally:
        time.sleep(5)
        driver.quit()