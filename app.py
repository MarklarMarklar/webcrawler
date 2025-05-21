import sys
import os
import time

# Insert the current directory at the beginning of the path
# to make sure our custom modules are found first
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and apply patches for Python 3.13 compatibility
from twisted_patch import apply_twisted_patches
apply_twisted_patches()

from flask import Flask, render_template, request, jsonify
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy import Selector
from scrapy import signals
import requests
from multiprocessing import Process, Queue
import json
import tempfile
import logging
from llm_api import LMStudioAPI, POTENTIAL_API_URLS, WSL_CONNECTION_TIMEOUT, DEFAULT_API_URL
from dotenv import load_dotenv
import find_host_ip

# Load environment variables from .env file if present
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get LLM API URL from environment variable or use the default
api_url = os.environ.get("LM_STUDIO_API_URL", "http://172.31.64.1:1234/v1")
logger.info(f"Using LM Studio API URL: {api_url}")

# Check if we should use mock mode based on environment or connectivity issues
use_mock_mode = os.environ.get("LLM_MOCK_MODE", "").lower() in ("true", "1", "yes", "y")
if not use_mock_mode:
    # Test if we can actually connect with a much longer timeout
    try:
        logger.info(f"Testing connection with longer timeout ({WSL_CONNECTION_TIMEOUT}s)...")
        test_response = requests.get(f"{api_url}/models", timeout=WSL_CONNECTION_TIMEOUT)
        if test_response.status_code != 200:
            logger.warning(f"Could not connect to LLM API (status {test_response.status_code}), enabling mock mode")
            use_mock_mode = True
        else:
            logger.info(f"Successfully connected to LLM API at {api_url}")
            use_mock_mode = False  # Explicitly disable mock mode
    except Exception as e:
        logger.warning(f"Failed to connect to LLM API ({str(e)}), enabling mock mode")
        use_mock_mode = True

logger.info(f"LLM mock mode enabled: {use_mock_mode}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Initialize LM Studio API client with the discovered URL and forced mock mode setting
llm_api = LMStudioAPI(base_url=api_url, mock_mode=use_mock_mode, skip_auto_discovery=True)

class DynamicSpider(scrapy.Spider):
    name = 'dynamic_spider'
    
    def __init__(self, start_url=None, selectors=None, *args, **kwargs):
        super(DynamicSpider, self).__init__(*args, **kwargs)
        self.start_urls = [start_url]
        # Store selectors dictionary
        self.selectors = selectors or {}
        # Keep track of the original selectors before we pop any values
        self.original_selectors = dict(selectors or {})
        # Set max pages to follow (default to 5 to avoid excessive requests)
        self.max_pages = kwargs.get('max_pages', 5)
        self.pages_followed = 0
        self.current_page = 1
        
        # Log selectors for debugging
        self.logger.info(f"Spider initialized with selectors: {self.selectors}")
        self.logger.info(f"Max pages to follow: {self.max_pages}")
    
    def parse(self, response):
        self.logger.info(f"Parsing page: {response.url} (Page {self.current_page} of max {self.max_pages})")
        
        # Extract pagination and item container selectors
        item_container = self.original_selectors.get('item_container')
        pagination_selector = self.original_selectors.get('pagination_selector')
        
        # Build a dictionary of field selectors (excluding special selectors)
        field_selectors = {k: v for k, v in self.original_selectors.items() 
                          if k not in ['item_container', 'pagination_selector']}
        
        self.logger.info(f"Field selectors: {field_selectors}")
        self.logger.info(f"Item container: {item_container}")
        self.logger.info(f"Pagination selector: {pagination_selector}")
        
        # Check for item container
        if item_container:
            self.logger.info(f"Using item container selector: {item_container}")
            
            # Get all containers based on selector type
            containers = []
            if item_container.startswith('xpath:'):
                xpath_expr = item_container[6:]
                self.logger.info(f"Using XPath for container: {xpath_expr}")
                containers = response.xpath(xpath_expr)
            else:
                self.logger.info(f"Using CSS for container: {item_container}")
                containers = response.css(item_container)
                
            item_count = len(containers)
            self.logger.info(f"Found {item_count} item containers on page {self.current_page} ({response.url})")
            
            # Process each container
            for container_idx, container in enumerate(containers):
                item = {}
                self.logger.info(f"Processing container {container_idx+1}/{item_count}")
                
                # Extract all fields from this container
                for field_name, selector in field_selectors.items():
                    try:
                        # Handle different selector types
                        if selector.startswith('xpath:'):
                            xpath_expr = selector[6:]
                            self.logger.info(f"Using XPath selector for {field_name}: {xpath_expr}")
                            result = container.xpath(xpath_expr).get()
                        elif "::text" in selector:
                            self.logger.info(f"Using CSS text selector for {field_name}: {selector}")
                            result = container.css(selector).get()
                        elif "::attr" in selector:
                            self.logger.info(f"Using CSS attribute selector for {field_name}: {selector}")
                            result = container.css(selector).get()
                        else:
                            self.logger.info(f"Using CSS selector for {field_name}: {selector}")
                            result = container.css(selector).get()
                        
                        # Clean the result if it's a string
                        if result and isinstance(result, str):
                            result = result.strip()
                            
                        item[field_name] = result
                        self.logger.info(f"Extracted {field_name}: {item[field_name]}")
                    except Exception as e:
                        self.logger.error(f"Error extracting {field_name}: {str(e)}")
                
                # Only yield non-empty items
                if item:
                    self.logger.info(f"Yielding item from page {self.current_page}: {item}")
                    yield item
                else:
                    self.logger.warning(f"Container {container_idx+1} yielded an empty item, skipping")
        else:
            # No container specified, extract single item from the page
            self.logger.info("No item container specified, extracting single item from page")
            item = {}
            for field_name, selector in field_selectors.items():
                try:
                    # Handle different selector types
                    if selector.startswith('xpath:'):
                        xpath_expr = selector[6:]
                        self.logger.info(f"Using XPath selector for {field_name}: {xpath_expr}")
                        result = response.xpath(xpath_expr).get()
                    elif "::text" in selector:
                        self.logger.info(f"Using CSS text selector for {field_name}: {selector}")
                        result = response.css(selector).get()
                    elif "::attr" in selector:
                        self.logger.info(f"Using CSS attribute selector for {field_name}: {selector}")
                        result = response.css(selector).get()
                    else:
                        self.logger.info(f"Using CSS selector for {field_name}: {selector}")
                        result = response.css(selector).get()
                    
                    # Clean the result if it's a string
                    if result and isinstance(result, str):
                        result = result.strip()
                        
                    item[field_name] = result
                    self.logger.info(f"Extracted {field_name}: {item[field_name]}")
                except Exception as e:
                    self.logger.error(f"Error extracting {field_name}: {str(e)}")
            
            if item:
                self.logger.info(f"Yielding single item from page {self.current_page}: {item}")
                yield item
        
        # Follow pagination if available and we haven't reached the page limit
        if pagination_selector and self.current_page < self.max_pages:
            self.pages_followed += 1
            self.current_page += 1
            self.logger.info(f"Following pagination to page {self.current_page}/{self.max_pages}")
            
            # Get the next page URL
            next_page = None
            try:
                if pagination_selector.startswith('xpath:'):
                    xpath_expr = pagination_selector[6:]
                    self.logger.info(f"Using XPath for pagination: {xpath_expr}")
                    if 'attr(' in xpath_expr:
                        next_page = response.xpath(xpath_expr).get()
                    else:
                        next_page = response.xpath(xpath_expr).get()
                else:
                    self.logger.info(f"Using CSS for pagination: {pagination_selector}")
                    if '::attr' in pagination_selector:
                        next_page = response.css(pagination_selector).get()
                    else:
                        next_page = response.css(pagination_selector + '::attr(href)').get()
                
                if next_page:
                    self.logger.info(f"Found next page URL: {next_page}")
                    next_page_url = response.urljoin(next_page)
                    self.logger.info(f"Following pagination to: {next_page_url} (Page {self.current_page})")
                    yield scrapy.Request(
                        url=next_page_url, 
                        callback=self.parse,
                        dont_filter=True  # Important for allowing revisits
                    )
                else:
                    self.logger.info(f"No next page found at page {self.current_page-1}, pagination complete")
            except Exception as e:
                self.logger.error(f"Error following pagination: {str(e)}")
        elif self.current_page >= self.max_pages:
            self.logger.info(f"Reached maximum page limit ({self.max_pages}), stopping pagination")
        elif not pagination_selector:
            self.logger.info("No pagination selector provided, not following pagination")

def test_selector(url, selector, is_container=False):
    try:
        logger.info(f"Testing selector: {selector} on URL: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        sel = Selector(text=response.text)
        elements = []

        if selector.startswith('xpath:'):
            xpath_expr = selector[6:]
            logger.info(f"Using XPath selector: {xpath_expr}")
            elements = sel.xpath(xpath_expr)
        else:
            logger.info(f"Using CSS selector: {selector}")
            elements = sel.css(selector)
        
        match_count = len(elements)
        logger.info(f"Found {match_count} elements for selector: {selector}")

        if match_count == 0:
            return {"success": False, "match_count": 0, "message": "Selector returned no results"}

        if is_container:
            first_element_html = elements[0].get()
            return {
                "success": True, 
                "match_count": match_count, 
                "message": f"Found {match_count} container elements.",
                "html_snippet_sample": first_element_html[:500] + ('...' if len(first_element_html) > 500 else '')
            }
        else:
            # Snippet for display is the element itself
            html_snippet_display_content = elements[0].get()
            # Snippet for LLM refinement is the parent element, if available
            parent_element = elements[0].xpath("..")
            html_snippet_for_llm = parent_element[0].get() if parent_element else html_snippet_display_content
            
            text_content_preview = "".join(elements[0].xpath(".//text()").getall()).strip()
            
            html_snippet_display_preview = html_snippet_display_content[:500] + ('...' if len(html_snippet_display_content) > 500 else '')
            text_content_preview_display = text_content_preview[:200] + ('...' if len(text_content_preview) > 200 else '')

            return {
                "success": True, 
                "match_count": match_count,
                "message": f"Found {match_count} match(es). Previewing the first one.",
                "html_snippet": html_snippet_for_llm, # Full parent snippet for LLM
                "html_snippet_display": html_snippet_display_preview, # Snippet of the direct element for UI
                "text_content_preview": text_content_preview_display
            }

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching URL {url}: {str(e)}")
        return {"success": False, "message": f"Timeout fetching URL: {url}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error on URL {url}: {str(e)}")
        return {"success": False, "message": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        logger.error(f"Error processing selector '{selector}' on {url}: {str(e)}")
        return {"success": False, "message": f"Error processing selector: {str(e)}"}

@app.route('/test-selector', methods=['POST'])
def test_selector_route():
    try:
        data = request.json
        url = data.get('url')
        selector_str = data.get('selector')
        is_container = data.get('is_container', False)
        
        if not url or not selector_str:
            return jsonify({
                'success': False,
                'message': 'URL and selector are required'
            }), 400
        
        result_dict = test_selector(url, selector_str, is_container)
        
        return jsonify(result_dict)
    except Exception as e:
        logger.error(f"Error in test_selector_route: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/test-llm', methods=['GET'])
def test_llm_connection():
    """Test the connection to the LM Studio API"""
    try:
        # Get retry settings from environment variables
        retries = int(os.environ.get('LLM_CONNECTION_RETRIES', 3))
        retry_delay = int(os.environ.get('LLM_RETRY_DELAY', 2))
        
        # Check if we need to re-discover the connection
        if request.args.get('rediscover', 'false').lower() == 'true':
            logger.info("Rediscovering LM Studio API connection")
            api_url = find_host_ip.create_api_url_with_fallback()
            os.environ["LM_STUDIO_API_URL"] = api_url
            # Recreate the client with the new URL
            global llm_api
            llm_api = LMStudioAPI(base_url=api_url, mock_mode=use_mock_mode)
        
        # Test the connection
        result = llm_api.test_connection(retries=retries, retry_delay=retry_delay)
        
        # Check if we're in mock mode
        if result.get("mock", False):
            return jsonify({
                'success': True,
                'result': result,
                'warning': "Using mock mode - AI features will be simulated.",
                'api_url': llm_api.base_url
            })
            
        if "error" in result:
            return jsonify({
                'success': False,
                'error': result["error"],
                'tip': result.get("tip", ""),
                'api_url': llm_api.base_url,
                'potential_urls': POTENTIAL_API_URLS
            }), 500
            
        return jsonify({
            'success': True,
            'result': result,
            'api_url': llm_api.base_url
        })
    except Exception as e:
        logger.error(f"Error testing LLM connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/configure-api', methods=['POST'])
def configure_api():
    """Update the LM Studio API configuration"""
    try:
        data = request.json
        api_url = data.get('api_url')
        use_mock = data.get('use_mock', False)
        auto_discover = data.get('auto_discover', False)
        
        if not api_url and not use_mock and not auto_discover:
            return jsonify({
                'success': False,
                'error': 'API URL is required unless using mock mode or auto-discovery'
            }), 400
        
        # If auto-discover is enabled, find a working connection
        if auto_discover:
            logger.info("Auto-discovering LM Studio API connection")
            api_url = find_host_ip.create_api_url_with_fallback()
        
        # Update the environment variable if not using mock mode
        if not use_mock and api_url:
            os.environ['LM_STUDIO_API_URL'] = api_url
        
        # Reinitialize the API client
        global llm_api
        llm_api = LMStudioAPI(base_url=api_url if not use_mock else None, 
                             mock_mode=use_mock)
        
        # Test the connection (will return mock success if in mock mode)
        result = llm_api.test_connection(retries=3, retry_delay=1)
        
        if "error" in result and not use_mock:
            logger.error(f"Connection error: {result['error']}")
            return jsonify({
                'success': False,
                'error': result["error"],
                'tip': result.get("tip", ""),
                'api_url': api_url
            }), 500
            
        return jsonify({
            'success': True,
            'message': f"API URL updated to {api_url}" if not use_mock else "Enabled mock mode",
            'mock_mode': use_mock,
            'api_url': api_url if not use_mock else None
        })
    except Exception as e:
        logger.error(f"Error configuring API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/generate-selectors', methods=['POST'])
def generate_selectors():
    """Generate CSS selectors using the LLM"""
    try:
        data = request.json
        url = data.get('url')
        query = data.get('query')
        
        logger.info(f"Generating selectors for URL: {url} with query: {query}")
        logger.info(f"LLM API URL: {llm_api.base_url}, Mock mode: {llm_api.mock_mode}")
        
        if not url or not query:
            return jsonify({
                'success': False,
                'error': 'URL and query are required'
            }), 400
        
        # Fetch the HTML content
        try:
            response = requests.get(url)
            response.raise_for_status()
            html_content = response.text
            logger.info(f"Successfully fetched HTML content, length: {len(html_content)}")
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            return jsonify({
                'success': False,
                'error': f"Failed to fetch URL: {str(e)}"
            }), 400
        
        # Try a direct connection first to ensure we're not in mock mode unnecessarily
        try:
            logger.info("Testing direct connection to LLM API before generating selectors...")
            test_response = requests.get(f"{api_url}/models", timeout=WSL_CONNECTION_TIMEOUT)
            if test_response.status_code == 200:
                logger.info("Direct connection test successful, using real LLM API")
                # Force disable mock mode if we can connect
                llm_api.mock_mode = False
            else:
                logger.warning(f"Direct connection test failed with status {test_response.status_code}")
        except Exception as e:
            logger.warning(f"Direct connection test failed: {str(e)}")
        
        # Generate selectors using the LLM
        result = llm_api.generate_selectors(html_content, query)
        
        # Check if we got an error response
        if "error" in result:
            logger.error(f"LLM API error: {result['error']}")
            return jsonify({
                'success': False,
                'error': result["error"]
            }), 500
            
        # Check if we're in mock mode
        if result.get("mock", False):
            logger.info("Using mock selectors due to LLM connectivity issues")
            # If all else fails, see if we can provide mock selectors for books.toscrape.com
            if "books.toscrape" in html_content:
                logger.info("Falling back to hardcoded selectors for books.toscrape.com")
                result["selectors"] = {
                    "item_container": "article.product_pod",
                    "title": "h3 a::text",
                    "price": ".price_color::text",
                    "pagination_selector": "li.next a::attr(href)"
                }
                result["fallback_extraction"] = True
                result["raw_response"] = html_content
                
            return jsonify({
                'success': True,
                'selectors': result["selectors"],
                'warning': "Using mock mode - AI-generated selectors are simulated."
            })
        
        # Check if fallback extraction was used
        if result.get("fallback_extraction", False):
            logger.info("LLM response was parsed using fallback extraction method")
            
            # For books.toscrape.com, add a container selector if not already there
            if "books.toscrape" in url and "item_container" not in result["selectors"]:
                result["selectors"]["item_container"] = "article.product_pod"
                
            # For books.toscrape.com, add a pagination selector if not already there
            if "books.toscrape" in url and "pagination_selector" not in result["selectors"]:
                result["selectors"]["pagination_selector"] = "li.next a::attr(href)"
                
            return jsonify({
                'success': True,
                'selectors': result["selectors"],
                'warning': "The AI response had formatting issues but we were able to extract selectors anyway."
            })
        
        # Check if the user mentioned "all pages" in their query but no pagination selector was generated
        all_pages_keywords = ["all pages", "every page", "multiple pages", "paginated", "pagination"]
        if any(keyword in query.lower() for keyword in all_pages_keywords):
            logger.info("User query mentions pagination, ensuring pagination selector is included")
            
            # For books.toscrape.com, add the pagination selector if not already provided
            if "books.toscrape" in url and "pagination_selector" not in result["selectors"]:
                logger.info("Adding pagination selector for books.toscrape.com based on user query")
                result["selectors"]["pagination_selector"] = "li.next a::attr(href)"
                
            # For other sites, try to find a common pagination pattern if not already provided
            elif "pagination_selector" not in result["selectors"]:
                # Look for common pagination elements in the HTML
                pagination_patterns = [
                    "li.next a", ".pagination .next", ".pagination a.next", 
                    "a.next", ".pager-next a", ".next-page", "[rel='next']"
                ]
                
                sel = Selector(text=html_content)
                for pattern in pagination_patterns:
                    if sel.css(pattern):
                        logger.info(f"Found potential pagination selector: {pattern}")
                        # If it's an anchor, we need the href attribute
                        if pattern.endswith('a') or '[rel=' in pattern:
                            result["selectors"]["pagination_selector"] = f"{pattern}::attr(href)"
                        else:
                            result["selectors"]["pagination_selector"] = f"{pattern} a::attr(href)"
                        break
        
        # For books.toscrape.com, add a container selector if not already there
        if "books.toscrape" in url and "item_container" not in result["selectors"]:
            result["selectors"]["item_container"] = "article.product_pod"
            
        # For books.toscrape.com, add a pagination selector if not already there
        if "books.toscrape" in url and "pagination_selector" not in result["selectors"]:
            result["selectors"]["pagination_selector"] = "li.next a::attr(href)"
            
        return jsonify({
            'success': True,
            'selectors': result["selectors"]
        })
    except Exception as e:
        logger.error(f"Error in generate_selectors: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def run_spider(start_url, selectors, output_file, export_format='json', page_limit=10):
    try:
        # Fix path format for Windows and use absolute path
        output_file = os.path.abspath(output_file).replace('\\', '/')
        logger.info(f"Absolute output file path: {output_file}")
        
        # Check if pagination is being used
        is_paginated = 'pagination_selector' in selectors
        # Set a higher request timeout for paginated crawls
        request_timeout = 300 if is_paginated else 60
        
        # Get crawler settings
        logger.info("Setting up Scrapy crawler settings")
        settings = {
            'LOG_LEVEL': 'DEBUG',
            'LOG_ENABLED': True,
            'DOWNLOAD_TIMEOUT': request_timeout,
            'CONCURRENT_REQUESTS': 1,  # Reduce to avoid overwhelming the target site
            'DOWNLOAD_DELAY': 1,  # Add a 1 second delay between requests
            'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'FEEDS': {
                output_file: {
                    'format': export_format,
                    'encoding': 'utf-8',
                    'store_empty': False,
                    'overwrite': True,
                }
            },
            'FEED_EXPORT_ENCODING': 'utf-8'
        }
        
        # Ensure page_limit is a valid integer
        try:
            page_limit = int(page_limit)
            if page_limit < 1:
                page_limit = 1
            elif page_limit > 100:
                page_limit = 100
        except (TypeError, ValueError):
            page_limit = 10 if is_paginated else 1
            
        logger.info(f"Crawler process settings: {settings}")
        logger.info(f"Pagination enabled: {is_paginated}, Max pages: {page_limit}")
        
        # Create a unique feed URI
        if os.name == 'nt':  # Windows
            # On Windows, use a different feed configuration
            logger.info("Windows system detected, using file URI format")
            output_dir = os.path.dirname(output_file)
            output_filename = os.path.basename(output_file)
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # Create a directory-friendly URI
            settings['FEEDS'] = {}
            settings['FEEDS'][output_file] = {
                'format': export_format,
                'encoding': 'utf-8',
                'overwrite': True,
            }
            
            logger.info(f"Windows feed configuration: {settings['FEEDS']}")
        
        # Define a collector to get all items
        items = []
        
        class ItemCollector:
            def item_scraped(self, item, response, spider):
                logger.info(f"Item collected: {item}")
                items.append(dict(item))
                return item
        
        try:
            # Create and configure the process
            logger.info("Creating CrawlerProcess")
            process = CrawlerProcess(settings=settings)
            
            # Configure the crawler with selectors
            logger.info(f"Configuring crawler with selectors: {selectors}")
            crawler = process.create_crawler(DynamicSpider)
            
            # Add our item collector
            crawler.signals.connect(ItemCollector().item_scraped, signal=signals.item_scraped)
            
            # Start the crawler with our parameters
            logger.info(f"Starting crawler with start URL: {start_url}")
            process.crawl(
                crawler,
                start_url=start_url, 
                selectors=selectors,
                max_pages=page_limit
            )
            
            # Run the process
            logger.info("Starting the crawling process")
            process.start()
            
            # Verify the file was created
            if os.path.exists(output_file):
                logger.info(f"Output file successfully created: {output_file}")
                file_size = os.path.getsize(output_file)
                logger.info(f"Output file size: {file_size} bytes")
                
                # If file is empty but we have collected items, write them manually
                if file_size == 0 and items:
                    logger.info(f"File is empty but {len(items)} items were collected. Writing manually.")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        if export_format == 'json':
                            json.dump(items, f, ensure_ascii=False, indent=2)
                        elif export_format == 'csv':
                            import csv
                            if items:
                                fieldnames = items[0].keys()
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(items)
                        logger.info(f"Manually wrote {len(items)} items to {output_file}")
            else:
                logger.error(f"Output file was not created after scraping: {output_file}")
                # If file wasn't created but we have collected items, write them manually
                if items:
                    logger.info(f"Creating output file manually with {len(items)} collected items")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        if export_format == 'json':
                            json.dump(items, f, ensure_ascii=False, indent=2)
                        elif export_format == 'csv':
                            import csv
                            if items:
                                fieldnames = items[0].keys()
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(items)
                        logger.info(f"Manually wrote {len(items)} items to {output_file}")
                
            logger.info(f"Total items collected: {len(items)}")
        except Exception as e:
            logger.error(f"CrawlerProcess error: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # If we have items despite the error, try to write them
            if items:
                logger.info(f"Attempting to write {len(items)} collected items despite error")
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        if export_format == 'json':
                            json.dump(items, f, ensure_ascii=False, indent=2)
                        elif export_format == 'csv':
                            import csv
                            if items:
                                fieldnames = items[0].keys()
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(items)
                        logger.info(f"Successfully wrote {len(items)} items despite crawler error")
                except Exception as write_error:
                    logger.error(f"Failed to write items manually: {str(write_error)}")
            
            raise
            
    except Exception as e:
        logger.error(f"Error in run_spider: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        logger.info("Scrape endpoint called")
        data = request.json
        logger.info(f"Request data: {data}")
        
        start_url = data.get('start_url')
        selectors = data.get('selectors', {})
        export_format = data.get('export_format', 'json')
        save_path = data.get('save_path', '')
        page_limit = data.get('page_limit', 10)
        
        # Validate page limit (ensure it's between 1 and 100)
        try:
            page_limit = int(page_limit)
            if page_limit < 1:
                page_limit = 1
            elif page_limit > 100:
                page_limit = 100
        except (TypeError, ValueError):
            page_limit = 10
            
        logger.info(f"Scraping URL: {start_url} with selectors: {selectors}")
        logger.info(f"Export format: {export_format}, Save path: {save_path}")
        logger.info(f"Page limit: {page_limit}")
        
        # Test URL accessibility
        try:
            logger.info(f"Testing URL accessibility: {start_url}")
            response = requests.head(start_url)
            response.raise_for_status()
            logger.info("URL is accessible")
        except Exception as e:
            logger.error(f"URL access error: {str(e)}")
            return jsonify({'error': f'Could not access URL: {str(e)}'}), 400

        # Determine if we're using a custom save path or a temporary file
        using_custom_path = bool(save_path.strip())
        
        if using_custom_path:
            # Ensure directory exists
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    logger.info(f"Created directory: {save_dir}")
                except Exception as e:
                    logger.error(f"Failed to create directory: {str(e)}")
                    return jsonify({'error': f'Failed to create directory: {str(e)}'}), 500
            
            # Make sure the file has the correct extension
            if export_format == 'json' and not save_path.lower().endswith('.json'):
                save_path += '.json'
            elif export_format == 'csv' and not save_path.lower().endswith('.csv'):
                save_path += '.csv'
                
            output_file = save_path
        else:
            # Create a temporary file for output that works with Windows paths
            temp_dir = tempfile.gettempdir()
            output_filename = f"scrapy_output_{int(time.time())}.json"
            output_file = os.path.join(temp_dir, output_filename)
        
        output_file_abs = os.path.abspath(output_file)
        logger.info(f"Using output file: {output_file_abs}")
        
        # Validate that we have selectors to use
        if not selectors:
            logger.error("No selectors provided")
            return jsonify({'error': 'No selectors provided for scraping'}), 400
            
        # Log the selectors we'll be using for debugging
        logger.info(f"Using selectors: {selectors}")
        if 'item_container' in selectors:
            logger.info(f"Container selector: {selectors['item_container']}")
        if 'pagination_selector' in selectors:
            logger.info(f"Pagination selector: {selectors['pagination_selector']}")
        
        try:
            # Run the spider in a separate process
            logger.info("Starting spider process")
            p = Process(target=run_spider, args=(start_url, selectors, output_file_abs, export_format, page_limit))
            p.start()
            p.join()
            
            # Check if the process ended successfully
            if p.exitcode != 0:
                logger.error(f"Spider process exited with code {p.exitcode}")
                return jsonify({'error': f'Scraping process failed with exit code {p.exitcode}'}), 500
                
            logger.info(f"Spider process completed with exit code: {p.exitcode}")
        except Exception as e:
            logger.error(f"Error running spider process: {str(e)}")
            return jsonify({'error': f'Error running spider: {str(e)}'}), 500
        
        # Read the results
        try:
            # Make sure file exists before trying to read
            if not os.path.exists(output_file_abs):
                logger.error(f"Output file not found: {output_file_abs}")
                
                # Fallback: Try direct scraping if multiprocess approach failed
                logger.info("Trying direct scraping as fallback...")
                try:
                    # Fetch the page directly
                    response = requests.get(start_url)
                    response.raise_for_status()
                    
                    # Extract data using selectors
                    selector = Selector(text=response.text)
                    results = {}
                    for field_name, css_selector in selectors.items():
                        if field_name in ['item_container', 'pagination_selector']:
                            continue
                        result = selector.css(css_selector).get()
                        results[field_name] = result
                    
                    logger.info(f"Direct scraping results: {results}")
                    return jsonify({'success': True, 'data': [results], 'note': 'Used direct scraping fallback'})
                except Exception as e:
                    logger.error(f"Direct scraping fallback also failed: {str(e)}")
                    return jsonify({'error': 'Scraping completed but no output file was generated and direct scraping fallback failed'}), 500
            
            # Check file size
            file_size = os.path.getsize(output_file_abs)
            logger.info(f"Output file size: {file_size} bytes")
            
            if file_size == 0:
                logger.error("Output file is empty")
                return jsonify({'error': 'Scraping completed but output file is empty'}), 500
                
            with open(output_file_abs, 'r') as f:
                content = f.read()
                logger.info(f"Raw file content length: {len(content)}")
                logger.info(f"Raw file content preview: {content[:200]}...")  # Log first 200 chars
                
                # Handle empty content
                if not content.strip():
                    logger.error("File content is empty or whitespace")
                    return jsonify({'error': 'File content is empty'}), 500
                
                # Parse the content based on export format
                if export_format == 'json':
                    results = json.loads(content)
                    logger.info(f"Parsed JSON results, {len(results)} items found")
                elif export_format == 'csv':
                    # For CSV, we need to read the first few lines to show as preview
                    # but we'll still include the file path for the user to access the full file
                    import csv
                    from io import StringIO
                    
                    csv_reader = csv.DictReader(StringIO(content))
                    results = []
                    # Get up to 10 rows for preview
                    for i, row in enumerate(csv_reader):
                        if i >= 10:  # Limit preview to 10 items
                            break
                        results.append(row)
                    
                    if not results and content.strip():
                        # If parsing as DictReader failed but there is content,
                        # just show the raw content for the first few lines
                        results = [{"preview": line} for line in content.strip().split('\n')[:10]]
                        
                    logger.info(f"Parsed CSV results, {len(results)} preview items shown")
                else:
                    logger.error(f"Unsupported export format: {export_format}")
                    return jsonify({'error': f'Unsupported export format: {export_format}'}), 400
                
            # Don't delete the file if it's a custom save path
            if not using_custom_path:
                # Clean up the temporary file
                try:
                    os.unlink(output_file_abs)
                    logger.info(f"Temporary file deleted: {output_file_abs}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")
            
            logger.info(f"Returning scraped results with {len(results)} items")
            return jsonify({
                'success': True, 
                'data': results,
                'saved_to_file': using_custom_path,
                'file_path': output_file_abs if using_custom_path else None,
                'item_count': len(results)
            })
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            logger.error(f"Content that caused error: {content[:500] if 'content' in locals() else 'N/A'}")
            return jsonify({'error': f'Error parsing results: {str(e)}'}), 500
        except Exception as e:
            logger.error(f"Error reading results: {str(e)}")
            return jsonify({'error': f'Error reading results: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in scrape route: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/')
def index():
    logger.info("Rendering index page")
    # Try to determine the best API URL for display if not already set or if it's the default
    if llm_api.base_url == DEFAULT_API_URL and not llm_api.mock_mode:
        llm_api._test_and_set_best_url() # Attempt to find a better one
    return render_template(
        'index.html', 
        api_url=llm_api.base_url, 
        is_mock_mode=llm_api.mock_mode,
        potential_api_urls=POTENTIAL_API_URLS
    )

@app.route('/visual-selector')
def visual_selector():
    logger.info("Rendering visual selector page")
    return render_template('visual_selector.html')

@app.route('/proxy-page')
def proxy_page():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({'error': 'Missing URL parameter'}), 400

    logger.info(f"Proxying request for URL: {target_url}")
    try:
        # It's good practice to set a timeout
        # You might also want to add headers to mimic a browser, e.g., User-Agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(target_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        # Important: To allow relative links/scripts/CSS within the proxied page to work correctly,
        # we should inject a <base> tag into the <head> of the fetched HTML.
        content = response.text
        # A simple way to inject <base href="...">. More robust parsing might be needed for complex cases.
        base_href_tag = f'<base href="{response.url}">' # Use the final URL after redirects
        if '<head>' in content:
            content = content.replace('<head>', '<head>\n' + base_href_tag, 1)
        elif '<HEAD>' in content: # case insensitive for <head>
            content = content.replace('<HEAD>', '<HEAD>\n' + base_href_tag, 1)
        else:
            # If no <head> tag, prepend (less ideal, but a fallback)
            content = base_href_tag + content
            
        return content, 200, {'Content-Type': response.headers.get('content-type', 'text/html')}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout when trying to fetch {target_url} for proxy.")
        return jsonify({'error': 'Timeout fetching the URL'}), 504 # Gateway Timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching URL {target_url} for proxy: {e}")
        return jsonify({'error': f'Error fetching URL: {str(e)}'}), 502 # Bad Gateway

@app.route('/api-status', methods=['GET'])
def api_status():
    """Get the current status of the LLM API"""
    try:
        return jsonify({
            'success': True,
            'mock_mode': llm_api.mock_mode,
            'api_url': llm_api.base_url,
            'message': 'Using mock mode (simulated responses)' if llm_api.mock_mode else 'Connected to real LLM API',
            'mock_mode_reason': 'Cannot connect to LLM API' if llm_api.mock_mode else None
        })
    except Exception as e:
        logger.error(f"Error getting API status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/refine-selector-via-llm', methods=['POST'])
def refine_selector_llm_route():
    try:
        data = request.json
        field_name = data.get('field_name')
        original_selector = data.get('original_selector')
        html_snippet = data.get('html_snippet')
        user_query_context = data.get('user_query_context') # This might come from the main llm-query input

        if not all([field_name, original_selector, html_snippet]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: field_name, original_selector, or html_snippet.'
            }), 400

        # Call the new method in llm_api
        # Ensure llm_api is the globally initialized one
        result = llm_api.refine_single_selector(field_name, original_selector, html_snippet, user_query_context)

        if result.get('success'):
            return jsonify({
                'success': True,
                'data': result.get('data')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'LLM refinement failed.'),
                'raw_response': result.get('raw_response') # Pass raw response if available for debugging
            }), 500
            
    except Exception as e:
        logger.error(f"Error in /refine-selector-via-llm route: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Server error in refinement route: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True) 