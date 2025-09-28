from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd
from selenium.common.exceptions import TimeoutException


class AirbnbReviewScraper:
    """
    A class to scrape reviews from Airbnb property pages.
    """
    
    def __init__(self, headless=False, wait_timeout=15):
        """
        Initialize the scraper with Chrome driver.
        
        Args:
            headless (bool): Whether to run browser in headless mode
            wait_timeout (int): Default timeout for WebDriverWait operations
        """
        self.wait_timeout = wait_timeout
        self.driver = None
        self.wait = None
        
        # Set up Chrome options
        chrome_options = webdriver.ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Initialize driver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, self.wait_timeout)
    
    def _close_translation_popup(self):
        """
        Check for and close the translation popup if it exists.
        """
        try:
            dialog = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[role="dialog"][aria-label="Translation on"]')
                )
            )
            close_button = self.driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Close"]')
            close_button.click()
            
            self.wait.until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, 'div[role="dialog"][aria-label="Translation on"]')
                )
            )
            print("Translation popup closed.")
            
        except TimeoutException:
            print("No translation popup found.")
    
    def _click_reviews_button(self):
        """
        Find and click the 'Show all reviews' button.
        """
        button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, '[data-testid="pdp-show-all-reviews-button"]')
            )
        )
        button.click()
    
    def _scroll_reviews_modal(self, max_wait_cycles=20):
        """
        Scroll through the reviews modal to load all reviews.
        
        Args:
            max_wait_cycles (int): Maximum number of scroll cycles to prevent infinite loop
            
        Returns:
            int: Final count of loaded reviews
        """
        scrollable_div = self.wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "[data-testid='pdp-reviews-modal-scrollable-panel']")
            )
        )
        
        # Focus modal
        self.driver.execute_script("arguments[0].focus();", scrollable_div)
        actions = ActionChains(self.driver)
        actions.move_to_element(scrollable_div).perform()
        time.sleep(1)
        
        review_selector = "[data-review-id]"
        prev_count = 0
        stable_count = 0
        
        while stable_count < 3 and max_wait_cycles > 0:
            # Scroll with multiple PAGE_DOWNs per cycle
            for _ in range(5):
                actions.move_to_element(scrollable_div).click().send_keys(Keys.PAGE_DOWN).perform()
                time.sleep(0.3)
            
            time.sleep(2)  # Wait for lazy load
            
            new_count = len(self.driver.find_elements(By.CSS_SELECTOR, review_selector))
            print(f"Currently loaded {new_count} reviews...")
            
            if new_count == prev_count:
                stable_count += 1
            else:
                stable_count = 0
                prev_count = new_count
            
            max_wait_cycles -= 1
        
        print(f"Finished scrolling. Final review count: {prev_count}")
        return prev_count
    
    def _extract_review_data(self, review_element):
        """
        Extract data from a single review element.
        
        Args:
            review_element: Selenium WebElement for a review
            
        Returns:
            dict: Dictionary containing review data
        """
        try:
            # Extract review ID
            review_id = review_element.get_attribute("data-review-id")
            
            # Extract reviewer name
            name_element = review_element.find_element(By.CSS_SELECTOR, "h2.hpipapi")
            reviewer_name = name_element.text
            
            # Extract reviewer location
            location_element = review_element.find_element(By.CSS_SELECTOR, ".s15w4qkt")
            reviewer_location = location_element.text
            
            # Extract rating (number of stars)
            rating_text = review_element.find_element(By.CSS_SELECTOR, ".c5dn5hn span.a8jt5op").text
            rating = rating_text.split(",")[0].replace("Rating", "").strip()
            
            # Extract date and stay duration
            date_elements = review_element.find_elements(By.CSS_SELECTOR, ".rdyyd4g")
            review_date = date_elements[0].text if date_elements else "Date not available"
            stay_duration = date_elements[1].text if len(date_elements) > 1 else "Duration not available"
            
            # Extract review text
            review_text_element = review_element.find_element(By.CSS_SELECTOR, ".l1h825yc")
            review_text = review_text_element.text
            
            return {
                'review_id': review_id,
                'reviewer_name': reviewer_name,
                'reviewer_location': reviewer_location,
                'rating': rating,
                'review_date': review_date,
                'stay_duration': stay_duration,
                'review_text': review_text
            }
            
        except Exception as e:
            print(f"Error extracting review: {e}")
            return None
    
    def scrape_reviews(self, url, output_filename=None, max_scroll_cycles=20):
        """
        Scrape all reviews from an Airbnb property page.
        
        Args:
            url (str): The URL of the Airbnb property page
            output_filename (str, optional): Filename to save CSV output
            max_scroll_cycles (int): Maximum scroll cycles for loading reviews
            
        Returns:
            pandas.DataFrame: DataFrame containing all scraped reviews
        """
        try:
            # Navigate to the URL
            print(f"Loading page: {url}")
            self.driver.get(url)
            
            # Close translation popup if present
            self._close_translation_popup()
            
            # Click reviews button
            self._click_reviews_button()
            
            # Scroll through reviews modal
            final_count = self._scroll_reviews_modal(max_scroll_cycles)
            
            # Extract all review data
            reviews_data = []
            review_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-review-id]")
            
            print(f"Extracting data from {len(review_elements)} reviews...")
            for review_element in review_elements:
                review_data = self._extract_review_data(review_element)
                if review_data:
                    reviews_data.append(review_data)
            
            # Convert to DataFrame
            df = pd.DataFrame(reviews_data)
            print(f"Successfully extracted {len(reviews_data)} reviews")
            
            # Save to CSV if filename provided
            if output_filename:
                df.to_csv(output_filename, index=False)
                print(f"Reviews saved to {output_filename}")
            
            return df
            
        except Exception as e:
            print(f"Error during scraping: {e}")
            return pd.DataFrame()  # Return empty DataFrame on error
    
    def close(self):
        """
        Close the browser and clean up resources.
        """
        if self.driver:
            self.driver.quit()
            print("Browser closed.")
    
    def __enter__(self):
        """
        Context manager entry.
        """
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit - automatically close browser.
        """
        self.close()


# # Example usage
# if __name__ == "__main__":
#     # Example URLs
#     url1 = "https://www.airbnb.com/rooms/1452875126811623938?check_in=2025-10-10&check_out=2025-10-12"
    
#     # Method 1: Using context manager (recommended)
#     with AirbnbReviewScraper(headless=False) as scraper:
#         df = scraper.scrape_reviews(url1, output_filename="property1_reviews.csv")
#         print(df.head())
#     finally:
#         scraper.close()