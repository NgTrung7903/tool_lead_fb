"""Shared browser ownership and conservative authentication checks."""
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
import json
import sys
from playwright.sync_api import sync_playwright
from urllib.parse import urlsplit
from services.storage import ExclusiveOperation
from services.storage import atomic_json


def profile_operation(profile_dir: Path):
    return ExclusiveOperation(profile_dir.parent / (profile_dir.name + '.lock'))


def authenticated(page, context) -> bool:
    parts = urlsplit(page.url)
    if parts.hostname not in ('www.facebook.com', 'facebook.com', 'm.facebook.com'):
        return False
    if any(word in parts.path.lower() for word in ('login', 'checkpoint', 'recover', 'two_step', 'auth_platform', 'consent')):
        return False
    cookies = context.cookies('https://www.facebook.com/')
    has_user = any(c['name'] == 'c_user' and c.get('value') for c in cookies)
    marker = page.locator('[role="feed"], [aria-label="Your profile"], [aria-label="Trang cá nhân của bạn"], [role="navigation"]')
    return bool(has_user and marker.count() and marker.first.is_visible()
                and not page.locator('input[name="email"], input[name="pass"]').count())


def launch_context(playwright, profile_dir: Path, headless: bool):
    profile_dir.mkdir(parents=True, exist_ok=True)
    preferences_path = profile_dir / 'Default' / 'Preferences'
    preferences = json.loads(preferences_path.read_text(encoding='utf-8')) if preferences_path.exists() else {}
    preferences['credentials_enable_service'] = False
    preferences.setdefault('profile', {})['password_manager_enabled'] = False
    atomic_json(preferences_path, preferences)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir), headless=headless,
        **({'executable_path':playwright.chromium.executable_path} if getattr(sys, 'frozen', False) else {}),
        viewport={'width': 1280, 'height': 900},
        args=['--disable-save-password-bubble', '--disable-features=PasswordManagerOnboarding'],
    )


@contextmanager
def isolated_posting_context(storage_state, headless):
    """One worker owns its Playwright runtime and a temporary browser session.

    Reuse the authenticated account without opening its disk profile twice.
    Cookies/local storage are copied in memory and discarded on close.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            **({'executable_path': playwright.chromium.executable_path} if getattr(sys, 'frozen', False) else {}),
            args=['--disable-save-password-bubble', '--disable-features=PasswordManagerOnboarding'],
        )
        try:
            context = browser.new_context(storage_state=deepcopy(storage_state),
                                          viewport={'width': 1280, 'height': 900})
            try:
                yield context
            finally:
                context.close()
        finally:
            browser.close()
