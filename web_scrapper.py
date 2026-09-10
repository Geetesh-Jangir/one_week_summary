from playwright.sync_api import sync_playwright


def scrape_page(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()

        print(f"Opening: {url}")

        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Wait for JavaScript-rendered content
        page.wait_for_timeout(3000)

        # Get the fully rendered HTML
        html = page.content()

        print(f"Page loaded successfully.")
        print(f"HTML size: {len(html)} characters")

        browser.close()

        return html


if __name__ == "__main__":
    print("===== WEB SCRAPER DEMO =====")
    url = input("Enter link: ").strip()

    if not url:
        print("No URL provided.")
    else:
        html = scrape_page(url)

        print("\n===== SCRAPED HTML =====\n")
        print(html)
