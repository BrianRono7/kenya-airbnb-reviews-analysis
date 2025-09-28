from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import re
import time

class AirbnbLocationScraper:
    def __init__(self):
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service)
        self.wait = WebDriverWait(self.driver, 10)
        self.data = []
    
    def extract_location(self, text):
        """Extract location from text like 'Popular homes in Mombasa'"""
        patterns = [r"in ([^,]+)", r"homes ([^,]+)", r"Available ([^,]+)"]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return text.strip()
    
    def scrape_locations(self, url="https://www.airbnb.com"):
        """Scrape location data from Airbnb"""
        self.driver.get(url)
        time.sleep(3)
        
        # Scroll down to load all content
        print("Scrolling to load all locations...")
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        while True:
            # Scroll to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Check if new content loaded
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        print("Finished scrolling, collecting locations...")
        
        # Find location carousels
        carousels = self.driver.find_elements(By.CSS_SELECTOR, 
            'h2, [data-testid="content-scroller"], [aria-label*="homes"]')
        
        print(f"Found {len(carousels)} elements")
        
        for i, element in enumerate(carousels):
            try:
                # Get text from element
                text = element.text
                if not text or len(text) < 5:
                    continue
                
                print(f"Processing: {text[:50]}...")
                
                # Extract location
                location = self.extract_location(text)
                
                # Find nearby links
                try:
                    parent = element.find_element(By.XPATH, "./ancestor::div[1]")
                    links = parent.find_elements(By.CSS_SELECTOR, 'a[href*="/s/"]')
                    
                    if links:
                        for link in links[:3]:  # Limit to first 3 links
                            href = link.get_attribute('href')
                            self.data.append({
                                'location': location,
                                'link': href
                            })
                    else:
                        self.data.append({
                            'location': location,
                            'link': url
                        })
                except:
                    self.data.append({
                        'location': location,
                        'link': url
                    })
                    
            except Exception as e:
                continue
        
        print(f"Extracted {len(self.data)} entries")
    
    def get_dataframe(self):
        """Return data as DataFrame with only location and link columns"""
        df = pd.DataFrame(self.data)
        if not df.empty:
            # Keep only location and link columns, and remove duplicates
            df = df[['location', 'link']].drop_duplicates(subset=['link'], keep='first')
        return df
    
    def save_csv(self, filename='airbnb_locations.csv'):
        """Save to CSV"""
        df = self.get_dataframe()
        if not df.empty:
            df.to_csv(filename, index=False)
            print(f"Saved {len(df)} locations to {filename}")
        else:
            print("No data to save")
    
    def close(self):
        self.driver.quit()

# # Usage
# if __name__ == "__main__":
#     scraper = AirbnbLocationScraper()
#     try:
#         scraper.scrape_locations()
#         df = scraper.get_dataframe()
#         print(f"\nFound {len(df)} locations:")
#         if not df.empty:
#             print(df.head())
#         scraper.save_csv()
#     finally:
#         scraper.close()