import pandas as pd
import time
import logging
import os
from datetime import datetime
import traceback
from urllib.parse import urljoin, urlparse, parse_qs
import re

# Import your existing scrapers
from AirbnbLocationScraper import AirbnbLocationScraper
from code import AirbnbSearchScraper
from airbnb_scraper import AirbnbReviewScraper

class AirbnbCompleteScraper:
    """
    A comprehensive scraper that combines location discovery, 
    listing extraction, and review collection for Airbnb properties.
    """
    
    def __init__(self, headless=True, max_locations=None, max_listings_per_location=50, max_reviews_per_listing=None):
        """
        Initialize the complete scraper.
        
        Args:
            headless (bool): Run browsers in headless mode
            max_locations (int): Maximum locations to process (None for all)
            max_listings_per_location (int): Maximum listings per location
            max_reviews_per_listing (int): Maximum reviews per listing (None for all)
        """
        self.headless = headless
        self.max_locations = max_locations
        self.max_listings_per_location = max_listings_per_location
        self.max_reviews_per_listing = max_reviews_per_listing
        
        # Data storage
        self.locations_df = pd.DataFrame()
        self.listings_df = pd.DataFrame()
        self.reviews_df = pd.DataFrame()
        self.comprehensive_df = pd.DataFrame()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'airbnb_scraping_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Create output directory
        self.output_dir = f"airbnb_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
    def extract_search_url_from_location_link(self, location_link):
        """
        Convert a location link to a proper search URL if needed.
        
        Args:
            location_link (str): Location link from location scraper
            
        Returns:
            str: Properly formatted search URL
        """
        if '/s/' in location_link:
            # Add search parameters for better results
            if '?' not in location_link:
                location_link += '?'
            else:
                location_link += '&'
            
            # Add flexible dates and search parameters
            search_params = [
                'flexible_trip_lengths[]=weekend_trip',
                'date_picker_type=flexible_dates',
                'search_type=user_map_move',
                'monthly_start_date=2025-10-01',
                'monthly_length=3',
                'monthly_end_date=2026-01-01',
                'search_mode=regular_search',
                'price_filter_input_type=2',
                'price_filter_num_nights=2',
                'channel=EXPLORE'
            ]
            location_link += '&'.join(search_params)
        
        return location_link

    def step1_discover_locations(self):
        """
        Step 1: Discover all available locations from Airbnb homepage.
        
        Returns:
            pd.DataFrame: DataFrame with location data
        """
        self.logger.info("=== STEP 1: Discovering Locations ===")
        
        try:
            scraper = AirbnbLocationScraper()
            scraper.scrape_locations()
            self.locations_df = scraper.get_dataframe()
            
            # Apply location limit if specified
            if self.max_locations and len(self.locations_df) > self.max_locations:
                self.locations_df = self.locations_df.head(self.max_locations)
                self.logger.info(f"Limited to first {self.max_locations} locations")
            
            # Save locations data
            locations_file = os.path.join(self.output_dir, 'step1_locations.csv')
            self.locations_df.to_csv(locations_file, index=False)
            
            self.logger.info(f"Discovered {len(self.locations_df)} locations")
            self.logger.info(f"Locations saved to: {locations_file}")
            
            scraper.close()
            return self.locations_df
            
        except Exception as e:
            self.logger.error(f"Error in step 1 - location discovery: {str(e)}")
            traceback.print_exc()
            return pd.DataFrame()

    def step2_extract_listings(self):
        """
        Step 2: Extract all listings for each discovered location.
        
        Returns:
            pd.DataFrame: DataFrame with listing data
        """
        self.logger.info("=== STEP 2: Extracting Listings for All Locations ===")
        
        if self.locations_df.empty:
            self.logger.error("No locations found. Run step1_discover_locations() first.")
            return pd.DataFrame()
        
        all_listings = []
        
        for idx, location_row in self.locations_df.iterrows():
            location_name = location_row['location']
            location_link = location_row['link']
            
            self.logger.info(f"\n--- Processing Location {idx+1}/{len(self.locations_df)}: {location_name} ---")
            
            try:
                # Convert location link to proper search URL
                search_url = self.extract_search_url_from_location_link(location_link)
                self.logger.info(f"Search URL: {search_url}")
                
                # Create search scraper for this location
                with AirbnbSearchScraper(base_url=search_url, headless=self.headless) as search_scraper:
                    # Scrape listings for this location
                    location_listings = search_scraper.scrape_all_pages(max_pages=self.max_listings_per_location)
                    
                    # Add location metadata to each listing
                    for listing in location_listings:
                        listing['source_location'] = location_name
                        listing['source_location_link'] = location_link
                        listing['location_index'] = idx
                    
                    all_listings.extend(location_listings)
                    
                    self.logger.info(f"Collected {len(location_listings)} listings for {location_name}")
                    self.logger.info(f"Total listings so far: {len(all_listings)}")
                
                # Small delay between locations
                time.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Error processing location {location_name}: {str(e)}")
                continue
        
        # Create listings DataFrame
        self.listings_df = pd.DataFrame(all_listings)
        
        # Save listings data
        if not self.listings_df.empty:
            listings_file = os.path.join(self.output_dir, 'step2_listings.csv')
            self.listings_df.to_csv(listings_file, index=False)
            self.logger.info(f"Total listings collected: {len(self.listings_df)}")
            self.logger.info(f"Listings saved to: {listings_file}")
        
        return self.listings_df

    def step3_extract_reviews(self):
        """
        Step 3: Extract reviews for each listing.
        
        Returns:
            pd.DataFrame: DataFrame with review data
        """
        self.logger.info("=== STEP 3: Extracting Reviews for All Listings ===")
        
        if self.listings_df.empty:
            self.logger.error("No listings found. Run step2_extract_listings() first.")
            return pd.DataFrame()
        
        all_reviews = []
        successful_reviews = 0
        failed_reviews = 0
        
        # Filter listings that have valid URLs
        valid_listings = self.listings_df[
            (self.listings_df['property_url'] != 'N/A') & 
            (self.listings_df['property_url'].notna())
        ].copy()
        
        self.logger.info(f"Processing reviews for {len(valid_listings)} valid listings")
        
        for idx, listing_row in valid_listings.iterrows():
            property_url = listing_row['property_url']
            property_id = listing_row.get('property_id', 'Unknown')
            location_name = listing_row.get('source_location', 'Unknown')
            
            self.logger.info(f"\n--- Processing Listing {idx+1}/{len(valid_listings)}: {property_id} in {location_name} ---")
            
            try:
                with AirbnbReviewScraper(headless=self.headless, wait_timeout=20) as review_scraper:
                    # Extract reviews for this property
                    reviews_df = review_scraper.scrape_reviews(
                        property_url, 
                        max_scroll_cycles=self.max_reviews_per_listing or 20
                    )
                    
                    if not reviews_df.empty:
                        # Add listing metadata to each review
                        reviews_df['source_property_id'] = property_id
                        reviews_df['source_property_url'] = property_url
                        reviews_df['source_location'] = location_name
                        reviews_df['listing_index'] = idx
                        
                        # Convert to dict records and add to all_reviews
                        reviews_list = reviews_df.to_dict('records')
                        all_reviews.extend(reviews_list)
                        
                        successful_reviews += 1
                        self.logger.info(f"Collected {len(reviews_df)} reviews for property {property_id}")
                    else:
                        self.logger.warning(f"No reviews found for property {property_id}")
                        failed_reviews += 1
                
                self.logger.info(f"Progress: {successful_reviews} successful, {failed_reviews} failed")
                
                # Small delay between properties
                time.sleep(1)
                
            except Exception as e:
                failed_reviews += 1
                self.logger.error(f"Error processing reviews for property {property_id}: {str(e)}")
                continue
        
        # Create reviews DataFrame
        self.reviews_df = pd.DataFrame(all_reviews)
        
        # Save reviews data
        if not self.reviews_df.empty:
            reviews_file = os.path.join(self.output_dir, 'step3_reviews.csv')
            self.reviews_df.to_csv(reviews_file, index=False)
            self.logger.info(f"Total reviews collected: {len(self.reviews_df)}")
            self.logger.info(f"Reviews saved to: {reviews_file}")
        
        self.logger.info(f"Review extraction summary: {successful_reviews} successful, {failed_reviews} failed")
        return self.reviews_df

    def step4_create_comprehensive_dataframe(self):
        """
        Step 4: Create a comprehensive DataFrame combining all data.
        
        Returns:
            pd.DataFrame: Comprehensive DataFrame with all data
        """
        self.logger.info("=== STEP 4: Creating Comprehensive DataFrame ===")
        
        # Create comprehensive data structure
        comprehensive_data = []
        
        # Process each location
        for _, location_row in self.locations_df.iterrows():
            location_name = location_row['location']
            location_link = location_row['link']
            
            # Get listings for this location
            location_listings = self.listings_df[
                self.listings_df['source_location'] == location_name
            ]
            
            if location_listings.empty:
                # Add location without listings
                comprehensive_data.append({
                    # Location data
                    'location_name': location_name,
                    'location_link': location_link,
                    'total_listings': 0,
                    'total_reviews': 0,
                    # Listing data (empty)
                    'property_id': None,
                    'property_name': None,
                    'property_type': None,
                    'property_url': None,
                    'price': None,
                    'rating': None,
                    'review_count': None,
                    # Review data (empty)
                    'avg_review_rating': None,
                    'total_property_reviews': 0,
                    'latest_review_date': None
                })
                continue
            
            # Process each listing in this location
            for _, listing_row in location_listings.iterrows():
                property_id = listing_row.get('property_id')
                
                # Get reviews for this listing
                listing_reviews = self.reviews_df[
                    self.reviews_df['source_property_id'] == property_id
                ] if not self.reviews_df.empty else pd.DataFrame()
                
                # Calculate review statistics
                if not listing_reviews.empty:
                    try:
                        # Convert rating to numeric, handling various formats
                        numeric_ratings = []
                        for rating in listing_reviews['rating']:
                            if pd.notna(rating) and rating != 'N/A':
                                # Extract numeric rating
                                rating_match = re.search(r'(\d+(?:\.\d+)?)', str(rating))
                                if rating_match:
                                    numeric_ratings.append(float(rating_match.group(1)))
                        
                        avg_rating = sum(numeric_ratings) / len(numeric_ratings) if numeric_ratings else None
                        
                        # Get latest review date
                        valid_dates = listing_reviews['review_date'][
                            (listing_reviews['review_date'] != 'N/A') & 
                            (listing_reviews['review_date'].notna())
                        ]
                        latest_date = valid_dates.iloc[0] if not valid_dates.empty else None
                        
                    except Exception as e:
                        avg_rating = None
                        latest_date = None
                        self.logger.warning(f"Error calculating review stats for {property_id}: {e}")
                else:
                    avg_rating = None
                    latest_date = None
                
                # Create comprehensive record
                comprehensive_record = {
                    # Location data
                    'location_name': location_name,
                    'location_link': location_link,
                    'total_listings': len(location_listings),
                    
                    # Listing data
                    'property_id': listing_row.get('property_id'),
                    'property_name': listing_row.get('property_name'),
                    'property_type': listing_row.get('property_type'),
                    'property_url': listing_row.get('property_url'),
                    'bed_info': listing_row.get('bed_info'),
                    'price': listing_row.get('price'),
                    'original_price': listing_row.get('original_price'),
                    'duration': listing_row.get('duration'),
                    'listing_rating': listing_row.get('rating'),
                    'listing_review_count': listing_row.get('review_count'),
                    'badges': listing_row.get('badges'),
                    'dates': listing_row.get('dates'),
                    
                    # Review data
                    'total_property_reviews': len(listing_reviews),
                    'avg_review_rating': avg_rating,
                    'latest_review_date': latest_date,
                    
                    # Metadata
                    'scrape_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                comprehensive_data.append(comprehensive_record)
        
        # Create comprehensive DataFrame
        self.comprehensive_df = pd.DataFrame(comprehensive_data)
        
        # Save comprehensive data
        if not self.comprehensive_df.empty:
            comprehensive_file = os.path.join(self.output_dir, 'step4_comprehensive_data.csv')
            self.comprehensive_df.to_csv(comprehensive_file, index=False)
            
            self.logger.info(f"Comprehensive dataset created with {len(self.comprehensive_df)} records")
            self.logger.info(f"Comprehensive data saved to: {comprehensive_file}")
            
            # Print summary statistics
            self.print_summary_statistics()
        
        return self.comprehensive_df

    def print_summary_statistics(self):
        """Print summary statistics of the scraped data."""
        print("\n" + "="*60)
        print("AIRBNB SCRAPING SUMMARY STATISTICS")
        print("="*60)
        
        print(f"📍 Total Locations Discovered: {len(self.locations_df)}")
        print(f"🏠 Total Listings Found: {len(self.listings_df)}")
        print(f"💬 Total Reviews Collected: {len(self.reviews_df)}")
        print(f"📊 Comprehensive Records: {len(self.comprehensive_df)}")
        
        if not self.comprehensive_df.empty:
            # Location statistics
            print(f"\n📍 LOCATION BREAKDOWN:")
            location_stats = self.comprehensive_df.groupby('location_name').agg({
                'property_id': 'count',
                'total_property_reviews': 'sum'
            }).rename(columns={'property_id': 'listings_count'})
            print(location_stats.head(10).to_string())
            
            # Price statistics
            print(f"\n💰 PRICE STATISTICS:")
            valid_prices = self.comprehensive_df[self.comprehensive_df['price'] != 'N/A']['price']
            if not valid_prices.empty:
                print(f"Properties with pricing: {len(valid_prices)}")
            
            # Review statistics
            print(f"\n⭐ REVIEW STATISTICS:")
            valid_ratings = self.comprehensive_df[self.comprehensive_df['avg_review_rating'].notna()]
            if not valid_ratings.empty:
                avg_rating = valid_ratings['avg_review_rating'].mean()
                print(f"Average rating across all properties: {avg_rating:.2f}")
                print(f"Properties with reviews: {len(valid_ratings)}")
        
        print("="*60)

    def run_complete_scraping(self, save_intermediate=True):
        """
        Run the complete scraping process: locations → listings → reviews → comprehensive dataset.
        
        Args:
            save_intermediate (bool): Save intermediate results at each step
            
        Returns:
            dict: Dictionary containing all DataFrames
        """
        start_time = time.time()
        self.logger.info("🚀 STARTING COMPLETE AIRBNB SCRAPING PROCESS")
        self.logger.info(f"Output directory: {self.output_dir}")
        
        try:
            # Step 1: Discover locations
            self.step1_discover_locations()
            
            # Step 2: Extract listings
            self.step2_extract_listings()
            
            # Step 3: Extract reviews
            self.step3_extract_reviews()
            
            # Step 4: Create comprehensive dataset
            self.step4_create_comprehensive_dataframe()
            
            # Calculate total time
            total_time = time.time() - start_time
            self.logger.info(f"✅ COMPLETE SCRAPING FINISHED in {total_time/60:.2f} minutes")
            
            return {
                'locations': self.locations_df,
                'listings': self.listings_df,
                'reviews': self.reviews_df,
                'comprehensive': self.comprehensive_df,
                'output_directory': self.output_dir
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error during complete scraping: {str(e)}")
            traceback.print_exc()
            return None

    def load_existing_data(self, data_directory):
        """
        Load existing data from a previous scraping session.
        
        Args:
            data_directory (str): Path to directory containing CSV files
        """
        try:
            locations_file = os.path.join(data_directory, 'step1_locations.csv')
            if os.path.exists(locations_file):
                self.locations_df = pd.read_csv(locations_file)
                self.logger.info(f"Loaded {len(self.locations_df)} locations")
            
            listings_file = os.path.join(data_directory, 'step2_listings.csv')
            if os.path.exists(listings_file):
                self.listings_df = pd.read_csv(listings_file)
                self.logger.info(f"Loaded {len(self.listings_df)} listings")
            
            reviews_file = os.path.join(data_directory, 'step3_reviews.csv')
            if os.path.exists(reviews_file):
                self.reviews_df = pd.read_csv(reviews_file)
                self.logger.info(f"Loaded {len(self.reviews_df)} reviews")
            
            comprehensive_file = os.path.join(data_directory, 'step4_comprehensive_data.csv')
            if os.path.exists(comprehensive_file):
                self.comprehensive_df = pd.read_csv(comprehensive_file)
                self.logger.info(f"Loaded {len(self.comprehensive_df)} comprehensive records")
                
        except Exception as e:
            self.logger.error(f"Error loading existing data: {str(e)}")


# Example usage and main execution
if __name__ == "__main__":
    print("🏠 AIRBNB COMPLETE DATA SCRAPER")
    print("="*50)
    
    # Configuration
    HEADLESS = False  # Set to True for production
    MAX_LOCATIONS = 5  # Limit locations for testing (set to None for all)
    MAX_LISTINGS_PER_LOCATION = 10  # Limit listings per location for testing
    MAX_REVIEWS_PER_LISTING = 5  # Limit reviews per listing for testing (set to None for all)
    
    # Create scraper instance
    complete_scraper = AirbnbCompleteScraper(
        headless=HEADLESS,
        max_locations=MAX_LOCATIONS,
        max_listings_per_location=MAX_LISTINGS_PER_LOCATION,
        max_reviews_per_listing=MAX_REVIEWS_PER_LISTING
    )
    
    try:
        # Option 1: Run complete scraping process
        results = complete_scraper.run_complete_scraping()
        
        if results:
            print(f"\n✅ Scraping completed successfully!")
            print(f"📁 Results saved in: {results['output_directory']}")
            
            # Display sample data
            if not results['comprehensive'].empty:
                print(f"\n📊 Sample of comprehensive data:")
                print(results['comprehensive'].head())
        else:
            print("❌ Scraping failed. Check logs for details.")
        
        # Option 2: Run individual steps (uncomment to use)
        # print("\n🔄 Running individual steps...")
        # complete_scraper.step1_discover_locations()
        # complete_scraper.step2_extract_listings() 
        # complete_scraper.step3_extract_reviews()
        # complete_scraper.step4_create_comprehensive_dataframe()
        
        # Option 3: Load existing data and create comprehensive dataset
        # print("\n📂 Loading existing data...")
        # complete_scraper.load_existing_data('path/to/existing/data')
        # complete_scraper.step4_create_comprehensive_dataframe()
        
    except KeyboardInterrupt:
        print("\n⏹️  Scraping interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        traceback.print_exc()
    
    print(f"\n🏁 Process completed. Check output directory for results.")