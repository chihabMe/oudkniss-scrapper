from seleniumwire import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import random

# --- Chrome Setup ---
chrome_options = Options()
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


service = ChromeService(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

# --- Scrolling Logic ---
def infinite_scroll_until_no_data(sleep_time=1, step=300, smooth_delay=0.1, max_tries=3):
    print("📜 Started scrolling...")
    tries, scroll_position = 0, 0
    last_height = driver.execute_script("return document.body.scrollHeight")

    while tries < max_tries:
        while scroll_position < last_height:
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            scroll_position += step
            time.sleep(smooth_delay)

        time.sleep(sleep_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        tries = tries + 1 if new_height == last_height else 0
        last_height = new_height

    print("✅ Finished scrolling.")

# --- Popup Handling ---
def close_popup_if_exists():
    try:
        # Wait for popup to appear before attempting to close
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div > div.v-overlay__content > div > header > div > button"))
        )
        btn = driver.find_element(By.CSS_SELECTOR, "div > div.v-overlay__content > div > header > div > button")
        btn.click()
        print("✅ Popup closed successfully.")
    except TimeoutException:
        print("ℹ️ No popup found or it didn't appear within the timeout.")
    except NoSuchElementException:
        print("ℹ️ Popup not found or already closed.")
    except Exception as e:
        print(f"⚠️ Error closing popup: {e}")

# --- Helper Function to Extract Text Safely ---
def get_field(selector, name):
    try:
        element = WebDriverWait(driver, 0.5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return element.text
    except TimeoutException:
        print(f"⚠️ Timeout while waiting for {name}.")
        return "N/A"
    except NoSuchElementException:
        print(f"❌ {name} element not found.")
        return "N/A"
    except Exception as e:
        print(f"⚠️ Error getting {name}: {e}")
        return "N/A"

def get_multiple_texts(selector, name):
    try:
        WebDriverWait(driver, 0.5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return [el.text for el in driver.find_elements(By.CSS_SELECTOR, selector)]
    except TimeoutException:
        print(f"⚠️ Timeout while waiting for {name}.")
        return []
    except Exception as e:
        print(f"⚠️ Error getting multiple {name}: {e}")
        return []

# --- Scrape Details Page with Retry Logic ---
def scrap_details_with_retry(link, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔍 Attempt {attempt}/{max_retries} to scrape {link}")
            return scrap_details(link)
        except WebDriverException as e:
            print(f"⚠️ WebDriver error on attempt {attempt}/{max_retries} for {link}: {str(e)}")
            if attempt < max_retries:
                wait_time = 2 * attempt  # Exponential backoff
                print(f"⏳ Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed for {link}")
                return {}
        except Exception as e:
            print(f"❌ Unexpected error on attempt {attempt}/{max_retries} for {link}: {str(e)}")
            if attempt < max_retries:
                wait_time = 2 * attempt
                print(f"⏳ Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed for {link}")
                return {}

# --- Scrape Details Page ---
def scrap_details(link):
    try:
        driver.get(link)
        
        # Wait for the main content to load
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.v-container.v-locale--is-ltr"))
            )
            print("Done wating")
        except TimeoutException:
            print(f"⚠️ Timed out waiting for page to load: {link}")
        
        close_popup_if_exists()

        # Extract all key-value pairs from the specification div
        spec_data = {}
        rows = driver.find_elements(By.CSS_SELECTOR, "div.v-container.v-locale--is-ltr > div.v-row.v-row--dense")
        
        for row in rows:
            try:
                # Get the label (key)
                key_elem = row.find_element(By.CSS_SELECTOR, "div.spec-name")
                key = key_elem.text.strip() if key_elem else "Unknown"
                
                # Get the value
                value_elem = row.find_element(By.CSS_SELECTOR, "div.v-col-sm-9.v-col-7")
                
                # Check if it's a checkbox item
                checkbox = None
                try:
                    checkbox = value_elem.find_element(By.CSS_SELECTOR, "i.mdi-checkbox-marked-outline")
                    value = True
                except NoSuchElementException:
                    # Not a checkbox, get text or chips
                    chips = value_elem.find_elements(By.CSS_SELECTOR, "span.v-chip")
                    if chips:
                        value = [chip.text.strip() for chip in chips]
                    else:
                        value = value_elem.text.strip()
                
                key = key.lower().replace(" ","_")
                spec_data[key] = value
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"⚠️ Error extracting row data: {e}")
        
        # Get other details
        description = get_field("#sidebar-layout > div.__content > div.mt-4 > div:nth-child(3) > div.v-container.v-locale--is-ltr > div > div", "Description")
        price= get_field("#sidebar-layout > div.__content > header > div > span:nth-child(2) > span","Price")
        title = get_field("#sidebar-layout > div.__content > header > h1","Title")
        location = get_field("#announcementUserInfo > div.v-list > div.v-list-item > div.v-list-item__content > div > div", "Location")
        phone = get_field("#announcementUserInfo > div.v-list > div.o-show-user-phones > div:nth-child(2) > div.v-list-item__content > span > a", "Phone")
        operation_type = get_field("#sidebar-layout > div.__content > div.o-show-categories > ul > li:nth-child(3) > a","Operation type")
        realestate_type = get_field("#sidebar-layout > div.__content > div.o-show-categories > ul > li:nth-child(5) > a","Realestate type")
        social_links = []
        try:
            social_links_obs = driver.find_elements(By.CSS_SELECTOR,
                "#announcementUserInfo > div.v-list > div.o-show-user-phones > div:nth-child(1) > div.v-list-item__content > div > div")
            for s in social_links_obs:
                try:
                    href = s.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                    social_name = s.find_element(By.CSS_SELECTOR, "a").text
                    social_links.append({"link":href,"name":social_name})
                except NoSuchElementException:
                    print("❌ Social link anchor not found.")
                except Exception as e:
                    print(f"⚠️ Error getting social link href: {e}")
        except TimeoutException:
            print("⚠️ Timeout waiting for social links.")
        except Exception as e:
            print(f"⚠️ Error getting social links container: {e}")

        
        number_of_images = 0 
        try:
            number_of_images = len(driver.find_elements(By.CSS_SELECTOR,"#sidebar-layout > div.__content > div.theater-box.mt-2 > div.ok-swiper.--desktop > div > div > div"))
        except:
            print("no image found")
        # Add these additional details to our data dictionary
        spec_data["description"] = description
        spec_data["location"] = location
        spec_data["phone"] = phone
        spec_data["link"] = link
        spec_data["socials"] = social_links
        spec_data["price"]=price
        spec_data["title"]=title
        spec_data['number_of_images'] = number_of_images
        spec_data['realestate_type'] = realestate_type
        spec_data["operation_type"] = operation_type
        
        
        print(f"✅ Successfully scraped details from {link}")
        print(spec_data)
        time.sleep(50)
        return spec_data

    except Exception as e:
        print(f"❌ Failed to scrape details for {link}: {e}")
        raise

# --- Main Loop ---
START, PAGES = 1, 200
results = []
all_links = []

# First, collect all links from listing pages
for p in range(START, START + PAGES):
    url = f"https://www.ouedkniss.com/immobilier-vente-appartement/{p}"
    print(f"\n🔍 Scraping page {p} of {START + PAGES - 1}: {url}")
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".search-page > div:nth-child(4) > div.search.mt-3"))
            )
        except TimeoutException:
            print(f"⚠️ Timed out waiting for page {p} to load. Continuing anyway...")
        
        close_popup_if_exists()
        infinite_scroll_until_no_data()

        elements = driver.find_elements(By.CSS_SELECTOR, ".search-page > div:nth-child(4) > div.search.mt-3 > div > div.v-lazy > div > div")
        print(f"📋 Found {len(elements)} ads on page {p}")

        for e in elements:
            try:
                link = e.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                if link is None or "/store/" in link:
                    continue
                all_links.append(link)
                print(f"🔗 Added link to queue: {link}")
            except NoSuchElementException:
                print("❌ Could not extract link.")
            except Exception as e:
                print(f"⚠️ Unexpected error for ad: {e}")

    except Exception as e:
        print(f"⚠️ Failed to process page {url}: {e}")

print(f"\n📊 Total links collected: {len(all_links)}")

# Then, visit each detail page
for i, link in enumerate(all_links):
    print(f"\n🔍 Processing link {i+1}/{len(all_links)}")
    try:
        # Add a random delay between requests to avoid detection
        wait_time = random.uniform(2, 5)
        print(f"⏳ Waiting {wait_time:.1f} seconds before next request...")
        time.sleep(wait_time)
        
        data = scrap_details_with_retry(link)
        if data:
            results.append(data)
            
            # Save intermediate results periodically (every 5 items)
            if (i + 1) % 5 == 0 or i == len(all_links) - 1:
                print(f"💾 Saving intermediate results ({len(results)} items so far)...")
                with open(f"realestate_intermediate_{i+1}.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                    
    except Exception as e:
        print(f"❌ Failed to process {link}: {str(e)}")

# --- Save final results to JSON ---
with open("realestate_final.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print("\n✅ Scraping completed!")
print(f"📊 Total items scraped: {len(results)}")
print(f"💾 All data saved to realestate_final.json")

# --- Graceful Exit ---
time.sleep(3)
driver.quit()
