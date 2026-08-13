from playwright.sync_api import sync_playwright


URL = "https://www.provo.gov/AgendaCenter/Planning-Commission-2"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)

    page = browser.new_page()

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    print("TITLE:", page.title())
    print("URL:", page.url)

    browser.close()