from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd
import re
from urllib.parse import urljoin, urlparse
import logging

class AirbnbSearchScraper:
    def __init__(self, base_url=None, headless=True, wait_timeout=10):
        """
        Initialize the Airbnb search scraper
        
        Args:
            base_url (str): Starting URL for scraping
            headless (bool): Run browser in headless mode
            wait_timeout (int): Maximum wait time for elements
        """
        self.base_url = base_url
        self.wait_timeout = wait_timeout
        self.all_listings = []
        
        # Setup Chrome options
        chrome_options = webdriver.ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Setup driver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, wait_timeout)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def close_popups(self):
        """Close any popups that might appear"""
        try:
            # Translation popup
            dialog = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="dialog"][aria-label="Translation on"]')
            ))
            close_button = self.driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Close"]')
            close_button.click()
            self.wait.until(EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, 'div[role="dialog"][aria-label="Translation on"]')
            ))
            self.logger.info("Translation popup closed.")
        except TimeoutException:
            self.logger.info("No translation popup found.")
        
        # Add other popup handlers as needed
        try:
            # Cookie banner or other common popups
            cookie_banner = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="main-cookies-banner-container"]')
            accept_button = cookie_banner.find_element(By.CSS_SELECTOR, 'button')
            accept_button.click()
            time.sleep(1)
            self.logger.info("Cookie banner closed.")
        except NoSuchElementException:
            pass

    def extract_listing_data(self, listing_element):
        """
        Extract data from a single listing element
        
        Args:
            listing_element: Selenium WebElement for the listing
            
        Returns:
            dict: Extracted listing data
        """
        listing_data = {}
        
        try:
            # Extract listing ID from data-testid or other attributes
            listing_data['listing_id'] = listing_element.get_attribute('data-testid') or 'N/A'
            
            # Extract title/property type
            try:
                title_element = listing_element.find_element(By.CSS_SELECTOR, '[data-testid="listing-card-title"]')
                listing_data['property_type'] = title_element.text.strip()
            except NoSuchElementException:
                listing_data['property_type'] = 'N/A'
            
            # Extract property name
            try:
                name_element = listing_element.find_element(By.CSS_SELECTOR, '[data-testid="listing-card-name"]')
                listing_data['property_name'] = name_element.text.strip()
            except NoSuchElementException:
                listing_data['property_name'] = 'N/A'
            
            # Extract link to property details
            try:
                link_element = listing_element.find_element(By.CSS_SELECTOR, 'a[href*="/rooms/"]')
                href = link_element.get_attribute('href')
                listing_data['property_url'] = href
                # Extract property ID from URL
                property_id_match = re.search(r'/rooms/(\d+)', href)
                listing_data['property_id'] = property_id_match.group(1) if property_id_match else 'N/A'
            except NoSuchElementException:
                listing_data['property_url'] = 'N/A'
                listing_data['property_id'] = 'N/A'
            
            # Extract bedroom/bed information
            try:
                subtitle_elements = listing_element.find_elements(By.CSS_SELECTOR, '[data-testid="listing-card-subtitle"]')
                bed_info = []
                for subtitle in subtitle_elements:
                    text = subtitle.text.strip()
                    if 'bedroom' in text.lower() or 'bed' in text.lower():
                        bed_info.append(text)
                listing_data['bed_info'] = ' | '.join(bed_info) if bed_info else 'N/A'
            except NoSuchElementException:
                listing_data['bed_info'] = 'N/A'
            
            # Extract dates
            try:
                subtitle_elements = listing_element.find_elements(By.CSS_SELECTOR, '[data-testid="listing-card-subtitle"]')
                for subtitle in subtitle_elements:
                    text = subtitle.text.strip()
                    if '–' in text and ('Oct' in text or 'Nov' in text or 'Dec' in text or 'Jan' in text or 'Feb' in text or 'Mar' in text):
                        listing_data['dates'] = text
                        break
                else:
                    listing_data['dates'] = 'N/A'
            except NoSuchElementException:
                listing_data['dates'] = 'N/A'
            
            # Extract price information
            try:
                price_element = listing_element.find_element(By.CSS_SELECTOR, '[data-testid="price-availability-row"]')
                
                # Look for different price patterns
                price_text = price_element.text.strip()
                
                # Extract main price (KSh amount)
                ksh_match = re.search(r'KSh\s*([\d,]+)', price_text)
                if ksh_match:
                    listing_data['price'] = f"KSh {ksh_match.group(1)}"
                else:
                    listing_data['price'] = 'N/A'
                
                # Check for original price (strikethrough)
                original_price_match = re.search(r'originally KSh\s*([\d,]+)', price_text)
                if original_price_match:
                    listing_data['original_price'] = f"KSh {original_price_match.group(1)}"
                else:
                    listing_data['original_price'] = 'N/A'
                
                # Extract duration (nights)
                duration_match = re.search(r'for (\d+) nights?', price_text)
                listing_data['duration'] = f"{duration_match.group(1)} nights" if duration_match else 'N/A'
                
            except NoSuchElementException:
                listing_data['price'] = 'N/A'
                listing_data['original_price'] = 'N/A'
                listing_data['duration'] = 'N/A'
            
            # Extract rating information
            try:
                rating_element = listing_element.find_element(By.CSS_SELECTOR, 'span[aria-label*="rating"]')
                rating_text = rating_element.get_attribute('aria-label')
                
                # Extract rating and review count
                rating_match = re.search(r'(\d+\.\d+) out of 5.*?(\d+) reviews?', rating_text)
                if rating_match:
                    listing_data['rating'] = rating_match.group(1)
                    listing_data['review_count'] = rating_match.group(2)
                else:
                    listing_data['rating'] = 'N/A'
                    listing_data['review_count'] = 'N/A'
                    
            except NoSuchElementException:
                listing_data['rating'] = 'N/A'
                listing_data['review_count'] = 'N/A'
            
            # Extract special badges (Guest favorite, etc.)
            try:
                badge_elements = listing_element.find_elements(By.CSS_SELECTOR, 'span[class*="badge"], div[class*="badge"]')
                badges = []
                for badge in badge_elements:
                    badge_text = badge.text.strip()
                    if badge_text and badge_text not in ['', 'out of 5 average rating']:
                        badges.append(badge_text)
                listing_data['badges'] = ' | '.join(badges) if badges else 'N/A'
            except NoSuchElementException:
                listing_data['badges'] = 'N/A'
            
        except Exception as e:
            self.logger.error(f"Error extracting listing data: {str(e)}")
            # Return partial data with error info
            listing_data['error'] = str(e)
        
        return listing_data

    def scrape_current_page(self):
        """Scrape all listings from the current page"""
        self.logger.info(f"Scraping current page: {self.driver.current_url}")
        
        # Wait for listings to load
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="card-container"]')
            ))
        except TimeoutException:
            self.logger.warning("No listings found on current page")
            return []
        
        # Find all listing cards
        listing_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="card-container"]')
        self.logger.info(f"Found {len(listing_elements)} listings on current page")
        
        page_listings = []
        for i, listing_element in enumerate(listing_elements):
            try:
                listing_data = self.extract_listing_data(listing_element)
                listing_data['page_number'] = self.get_current_page_number()
                listing_data['scrape_timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
                page_listings.append(listing_data)
                
                if (i + 1) % 10 == 0:
                    self.logger.info(f"Processed {i + 1} listings...")
                    
            except Exception as e:
                self.logger.error(f"Error processing listing {i + 1}: {str(e)}")
                continue
        
        return page_listings

    def get_current_page_number(self):
        """Extract current page number from pagination"""
        try:
            current_page = self.driver.find_element(By.CSS_SELECTOR, 'button[aria-current="page"]')
            return int(current_page.text.strip())
        except (NoSuchElementException, ValueError):
            return 1

    def get_next_page_url(self):
        """Find and return the URL for the next page"""
        try:
            # Look for "Next" button or link
            next_button = self.driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Next"]')
            return next_button.get_attribute('href')
        except NoSuchElementException:
            return None

    def scrape_all_pages(self, max_pages=None, delay_between_pages=2):
        """
        Scrape all pages of search results
        
        Args:
            max_pages (int): Maximum number of pages to scrape (None for all)
            delay_between_pages (int): Delay between page requests
        """
        if not self.base_url:
            raise ValueError("base_url must be set to scrape pages")
        
        self.logger.info(f"Starting scrape of all pages from: {self.base_url}")
        
        # Navigate to starting URL
        self.driver.get(self.base_url)
        time.sleep(3)
        
        # Close any popups
        self.close_popups()
        
        page_count = 0
        
        while True:
            page_count += 1
            self.logger.info(f"Scraping page {page_count}")
            
            # Scrape current page
            page_listings = self.scrape_current_page()
            self.all_listings.extend(page_listings)
            
            self.logger.info(f"Total listings collected so far: {len(self.all_listings)}")
            
            # Check if we've reached max pages
            if max_pages and page_count >= max_pages:
                self.logger.info(f"Reached maximum page limit: {max_pages}")
                break
            
            # Find next page URL
            next_url = self.get_next_page_url()
            if not next_url:
                self.logger.info("No more pages found")
                break
            
            # Navigate to next page
            self.logger.info(f"Navigating to next page: {next_url}")
            self.driver.get(next_url)
            time.sleep(delay_between_pages)
        
        self.logger.info(f"Scraping completed. Total listings: {len(self.all_listings)}")
        return self.all_listings

    def save_to_csv(self, filename='airbnb_search_results.csv'):
        """Save collected listings to CSV file"""
        if not self.all_listings:
            self.logger.warning("No data to save")
            return
        
        df = pd.DataFrame(self.all_listings)
        df.to_csv(filename, index=False)
        self.logger.info(f"Data saved to {filename}")
        return df

    def get_dataframe(self):
        """Return listings as pandas DataFrame"""
        return pd.DataFrame(self.all_listings) if self.all_listings else pd.DataFrame()

    def close(self):
        """Close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# # Example usage
# if __name__ == "__main__":
#     # Example search URL (replace with actual URL)
#     search_url = "https://www.airbnb.com/s/Mombasa/homes?place_id=ChIJM45ffcMMQBgRLEF4BSSBr7A&refinement_paths%5B%5D=%2Fhomes&flexible_trip_lengths%5B%5D=weekend_trip&date_picker_type=flexible_dates&search_type=user_map_move&query=Mombasa&monthly_start_date=2025-10-01&monthly_length=3&monthly_end_date=2026-01-01&search_mode=regular_search&price_filter_input_type=2&price_filter_num_nights=2&channel=EXPLORE&ne_lat=-3.8886556404441626&ne_lng=39.76495215953909&sw_lat=-4.13005453921665&sw_lng=39.64256574625787&zoom=11.789124325677037&zoom_level=11.789124325677037&search_by_map=true"
    
#     # Use context manager to ensure cleanup
#     with AirbnbSearchScraper(base_url=search_url, headless=False) as scraper:
#         try:
#             # Scrape all pages (limit to 5 for testing)
#             all_listings = scraper.scrape_all_pages(max_pages=50)
            
#             # Save to CSV
#             df = scraper.save_to_csv('mombasa_airbnb_listings.csv')
            
#             # Display summary
#             print(f"\nScraping Summary:")
#             print(f"Total listings collected: {len(all_listings)}")
#             print(f"Data columns: {list(df.columns) if df is not None else 'None'}")
            
#             # Show sample data
#             if df is not None and not df.empty:
#                 print(f"\nSample data:")
#                 print(df.head())
                
#         except Exception as e:
#             print(f"Error during scraping: {str(e)}")
#             import traceback
#             traceback.print_exc()