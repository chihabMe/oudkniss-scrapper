import os
import json
import random
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

file_name = "cars"
# Get environment variables if available
START_FROM_ENV, PAGES_FROM_ENV = os.getenv("START", None), os.getenv("PAGES", None)
START, PAGES = 1, 2
if START_FROM_ENV and PAGES_FROM_ENV:
    START = int(START_FROM_ENV)
    PAGES = int(PAGES_FROM_ENV)

# --- Helper Function to Extract Text Safely ---
async def get_field(page, selector, name):
    try:
        element = await page.wait_for_selector(selector, timeout=500)
        if element:
            return await element.inner_text()
        return "N/A"
    except PlaywrightTimeoutError:
        return "N/A"
    except Exception as e:
        print(f"⚠️ Error getting {name}: {e}")
        return "N/A"

async def get_multiple_texts(page, selector, name):
    try:
        elements = await page.query_selector_all(selector)
        return [await element.inner_text() for element in elements]
    except Exception as e:
        print(f"⚠️ Error getting multiple {name}: {e}")
        return []

# --- Popup Handling ---
async def close_popup_if_exists(page):
    try:
        popup_button = await page.wait_for_selector(
            "div > div.v-overlay__content > div > header > div > button", 
            timeout=2000
        )
        if popup_button:
            await popup_button.click()
            print("✅ Popup closed successfully.")
    except PlaywrightTimeoutError:
        pass  # No popup found, continue silently
    except Exception as e:
        print(f"⚠️ Error closing popup: {e}")

# --- Scrolling Logic ---
async def infinite_scroll_until_no_data(page, sleep_time=0.5, step=500, smooth_delay=0.05, max_tries=2):
    print("📜 Started scrolling...")
    tries, scroll_position = 0, 0
    last_height = await page.evaluate("document.body.scrollHeight")

    while tries < max_tries:
        while scroll_position < last_height:
            await page.evaluate(f"window.scrollTo(0, {scroll_position})")
            scroll_position += step
            await asyncio.sleep(smooth_delay)

        await asyncio.sleep(sleep_time)
        new_height = await page.evaluate("document.body.scrollHeight")
        tries = tries + 1 if new_height == last_height else 0
        last_height = new_height

    print("✅ Finished scrolling.")

# --- Scrape Details Page with Retry Logic ---
async def scrap_details_with_retry(page, link, max_retries=2, ctx=None):
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔍 Attempt {attempt}/{max_retries} to scrape {link}")
            return await scrap_details(page, link, ctx)
        except Exception as e:
            print(f"⚠️ Error on attempt {attempt}/{max_retries} for {link}: {str(e)}")
            if attempt < max_retries:
                wait_time = 1 * attempt  # Linear backoff
                print(f"⏳ Waiting {wait_time} seconds before retrying...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed for {link}")
                return {}

# --- Scrape Details Page ---
async def scrap_details(pag, link, ctx=None):
    if ctx is None:
        return 
    print("Starting scrapping ", link)
    try:
        page = await ctx.new_page()
        await page.goto(link)
        
        # Wait for the main content to load with reduced timeout
        try:
            await page.wait_for_selector("div.v-container.v-locale--is-ltr", timeout=4000)
        except PlaywrightTimeoutError:
            print(f"⚠️ Timed out waiting for page to load: {link}")
        
        await close_popup_if_exists(page)

        # Extract all key-value pairs from the specification div
        spec_data = {}
        rows = await page.query_selector_all("div.v-container.v-locale--is-ltr > div.v-row.v-row--dense")
        
        for row in rows:
            try:
                # Get the label (key)
                key_elem = await row.query_selector("div.spec-name")
                key = await key_elem.inner_text() if key_elem else "Unknown"
                key = key.strip()
                
                # Get the value
                value_elem = await row.query_selector("div.v-col-sm-9.v-col-7")
                
                # Check if it's a checkbox item
                checkbox = await value_elem.query_selector("i.mdi-checkbox-marked-outline")
                if checkbox:
                    value = True
                else:
                    # Not a checkbox, get text or chips
                    chips = await value_elem.query_selector_all("span.v-chip")
                    if chips:
                        value = [await chip.inner_text() for chip in chips]
                        value = [v.strip() for v in value]
                    else:
                        value = await value_elem.inner_text()
                        value = value.strip()
                
                key = key.lower().replace(" ", "_")
                spec_data[key] = value
            except Exception as e:
                print(f"⚠️ Error extracting row data: {e}")
        
        # Get other details
        details = {
            "state": await get_field(page, "#announcementUserInfo > div.v-list.v-theme--light.v-list--density-default.v-list--one-line > div:nth-child(1) > div.v-list-item__content > div > div", "state"),
            "street": await get_field(page, "#announcementUserInfo > div.v-list.v-theme--light.v-list--density-default.v-list--one-line > div:nth-child(2) > div.v-list-item__content > div", "street"),
            "description": await get_field(page, "#sidebar-layout > div.__content > div.mt-4 > div:nth-child(3) > div.v-container.v-locale--is-ltr > div > div", "Description"),
            "price": await get_field(page, "#sidebar-layout > div.__content > header > div", "Price"),
            "title": await get_field(page, "#sidebar-layout > div.__content > header > h1", "Title"),
            "phone": await get_field(page, "#announcementUserInfo > div.v-list > div.o-show-user-phones > div > div.v-list-item__content > span > a", "Phone"),
            "operation_type": await get_field(page, "#sidebar-layout > div.__content > div.o-show-categories > ul > li:nth-child(3) > a", "Operation type"),
            "realestate_type": await get_field(page, "#sidebar-layout > div.__content > div.o-show-categories > ul > li:nth-child(5) > a", "Realestate type")
        }
        
        # Add these details to our data dictionary
        spec_data.update(details)
        
        # Get social links
        social_links = []
        try:
            social_links_obs = await page.query_selector_all(
                "#announcementUserInfo > div.v-list > div.o-show-user-phones > div:nth-child(1) > div.v-list-item__content > div > div"
            )
            for s in social_links_obs:
                try:
                    link_element = await s.query_selector("a")
                    href = await link_element.get_attribute("href")
                    social_name = await link_element.inner_text()
                    social_links.append({"link": href, "name": social_name})
                except Exception:
                    pass
        except Exception:
            pass
        
        # Count images
        number_of_images = 0 
        try:
            images = await page.query_selector_all("#sidebar-layout > div.__content > div.theater-box.mt-2 > div.ok-swiper.--desktop > div > div > div")
            number_of_images = len(images)
        except Exception:
            pass
            
        # Add remaining details
        spec_data["link"] = link
        spec_data["socials"] = social_links
        spec_data['number_of_images'] = number_of_images
        
        print(f"✅ Successfully scraped details from {link}")
        
        await page.close()
        # Reduced wait time between requests
        #await asyncio.sleep(random.uniform(0.2, 1))
        return spec_data

    except Exception as e:
        print(f"❌ Failed to scrape details for {link}: {e}")
        if 'page' in locals():
            await page.close()
        raise

# --- Main Scraping Function ---
async def main():
    results = []
    host = "https://www.ouedkniss.com"

    async with async_playwright() as p:
        # Launch the browser (use headless=False to see the browser)
        browser = await p.chromium.launch(headless=False)
        
        # Create a context with custom user-agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        # Stealth mode equivalent
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        # Process each listing page one by one
        for page_num in range(START, START + PAGES):
            page_results = []
            url = f"{host}/automobiles-voitures/{page_num}?priceUnit=MILLION&priceRangeMin=50"
            print(f"\n🔍 Processing listing page {page_num} of {START + PAGES - 1}: {url}")
            
            # Create a new page for each listing page
            page = await context.new_page()
            
            try:
                await page.goto(url)
                try:
                    await page.wait_for_selector(".search-page > div:nth-child(4) > div.search.mt-3", timeout=4000)
                except PlaywrightTimeoutError:
                    print(f"⚠️ Timed out waiting for page {page_num} to load. Continuing anyway...")
                
                await close_popup_if_exists(page)
                await infinite_scroll_until_no_data(page)

                # Get all links from this listing page
                elements = await page.query_selector_all(".search-page > div:nth-child(4) > div.search.mt-3 > div > div.v-lazy > div > div")
                print(f"📋 Found {len(elements)} ads on page {page_num}")
                
                links = []
                for e in elements:
                    try:
                        link_element = await e.query_selector("a")
                        link = await link_element.get_attribute("href")
                        if link is None or "/store/" in link:
                            continue
                        full_link = f"{host}{link}"
                        links.append(full_link)
                        print(f"🔗 Found link: {full_link}")
                    except Exception as e:
                        print(f"⚠️ Error extracting link: {e}")
                
                # Close the listing page as we don't need it anymore
                await page.close()
                
                # Process each detail page from this listing page
                for i, link in enumerate(links):
                    print(f"\n📄 Processing detail {i+1}/{len(links)} from page {page_num}")
                    try:
                        # Add a random delay between requests
                        wait_time = random.uniform(0.5, 1.5)
                        print(f"⏳ Waiting {wait_time:.1f} seconds before next request...")
                        await asyncio.sleep(wait_time)
                        
                        data = await scrap_details_with_retry(None, link, 2, context)
                        if data:
                            data["page"]=f"{page_num}_{i}"
                            page_results.append(data)
                            
                            # Save intermediate results after each detail page
                            if (i + 1) % 5 == 0 or i == len(links) - 1:
                                print(f"💾 Saving intermediate results ({len(page_results)} items from this page)...")
                                with open(f"{file_name}_page_{page_num}_intermediate.json", "w", encoding="utf-8") as f:
                                    json.dump(page_results, f, ensure_ascii=False, indent=4)
                                
                    except Exception as e:
                        print(f"❌ Failed to process {link}: {str(e)}")
                
                # Add this page's results to the main results
                results.extend(page_results)
                
                # Save after each listing page is fully processed
                print(f"💾 Saving results after page {page_num} ({len(results)} total items)...")
                with open(f"{file_name}_final.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                
            except Exception as e:
                print(f"⚠️ Failed to process listing page {url}: {e}")
                if 'page' in locals():
                    await page.close()

        print("\n✅ Scraping completed!")
        print(f"📊 Total items scraped: {len(results)}")
        print(f"💾 All data saved to {file_name}_final.json")

        # Close the browser
        await browser.close()

# --- Run the main function ---
if __name__ == "__main__":
    asyncio.run(main())
