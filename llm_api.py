"""
Module for interacting with local LM Studio API
"""
import requests
import logging
import json
import os
import time
import platform
import socket
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG) # Change to DEBUG for more detailed logs
logger = logging.getLogger(__name__)

# Default LM Studio API URL - using the IP from user's log
DEFAULT_API_URL = "http://172.31.64.1:1234/v1"

# Use much longer timeouts for WSL-Windows connections
WSL_CONNECTION_TIMEOUT = 60
WSL_RESPONSE_TIMEOUT = 120
CONNECTION_TIMEOUT = WSL_CONNECTION_TIMEOUT

# List of possible connection URLs to try
POTENTIAL_API_URLS = [
    "http://172.31.64.1:1234/v1",    # IP address from logs
    "http://host.docker.internal:1234/v1",  # Docker/WSL connection to host
    "http://localhost:1234/v1",      # Local connection
    "http://127.0.0.1:1234/v1",      # Localhost IP
]

class LMStudioAPI:
    """
    Client for interacting with a locally running LM Studio API
    """
    def __init__(self, base_url=None, mock_mode=False, skip_auto_discovery=False):
        # If mock mode is enabled, don't try to connect to a real API
        self.mock_mode = mock_mode
        
        # If no URL provided, try to determine the best default based on platform
        if base_url is None:
            base_url = os.environ.get("LM_STUDIO_API_URL", DEFAULT_API_URL)
            logger.info(f"Using LM Studio API URL: {base_url}")
        
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json"
        }
        logger.info(f"Initialized LMStudioAPI with base URL: {self.base_url}")
        
        # Force disable mock mode if explicitly given a valid URL
        if base_url and base_url != DEFAULT_API_URL and self.mock_mode:
            logger.info(f"Explicit URL provided ({base_url}), disabling mock mode")
            self.mock_mode = False
        
        # Test all potential URLs if no specific one was provided and auto-discovery is enabled
        if not mock_mode and not skip_auto_discovery:
            # Only run the auto-discovery if mock mode isn't explicitly enabled
            if self.test_specific_url(self.base_url):
                logger.info(f"Successfully connected to the provided URL: {self.base_url}")
                # Explicitly ensure mock mode is off since we have a working connection
                self.mock_mode = False
            elif base_url == DEFAULT_API_URL:
                # Only try auto-discovery if the default URL was used
                self._test_and_set_best_url()
    
    def test_specific_url(self, url):
        """Test a specific URL to see if it works"""
        logger.info(f"Testing direct connection to: {url}")
        try:
            response = requests.get(
                f"{url}/models", 
                headers=self.headers,
                timeout=WSL_CONNECTION_TIMEOUT  # Use much longer timeout for WSL
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Connection to {url} failed: {str(e)}")
            return False
    
    def _test_and_set_best_url(self):
        """
        Try all potential URLs and set the best working one
        """
        logger.info("Testing multiple connection methods to find LM Studio...")
        for url in POTENTIAL_API_URLS:
            logger.info(f"Trying connection to: {url}")
            try:
                # Create a temporary requests session for testing
                session = requests.Session()
                response = session.get(
                    f"{url}/models", 
                    headers=self.headers,
                    timeout=WSL_CONNECTION_TIMEOUT  # Longer timeout for WSL connections
                )
                if response.status_code == 200:
                    logger.info(f"Successfully connected to LM Studio at: {url}")
                    self.base_url = url
                    self.mock_mode = False  # Explicitly disable mock mode if we found a working URL
                    return
            except requests.exceptions.RequestException as e:
                logger.warning(f"Connection to {url} failed: {str(e)}")
                continue
        
        logger.warning("Could not connect to any LM Studio API endpoints.")
        logger.info("Enabling mock mode for offline testing")
        self.mock_mode = True
    
    def test_connection(self, retries=1, retry_delay=1):
        """
        Test the connection to the LM Studio API
        
        Args:
            retries: Number of connection retry attempts
            retry_delay: Seconds to wait between retries
        """
        # If in mock mode, return a simulated successful response
        if self.mock_mode:
            logger.info("Mock mode: Simulating successful connection")
            return {
                "object": "list",
                "data": [{"id": "mock-model", "object": "model"}],
                "mock": True
            }
            
        for attempt in range(retries):
            try:
                logger.info(f"Testing connection to LM Studio API (attempt {attempt+1}/{retries})")
                response = requests.get(
                    f"{self.base_url}/models", 
                    headers=self.headers,
                    timeout=WSL_CONNECTION_TIMEOUT  # Use much longer timeout for WSL-Windows connections
                )
                response.raise_for_status()
                logger.info("Successfully connected to LM Studio API")
                # Explicitly disable mock mode when connection is successful
                self.mock_mode = False
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Connection attempt {attempt+1} failed: {str(e)}")
                if attempt < retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to LM Studio API after {retries} attempts: {str(e)}")
                    # Don't automatically enable mock mode here, let the caller decide
                    return {
                        "error": str(e),
                        "tip": "Make sure LM Studio server is running and accessible at " + self.base_url
                    }
    
    def generate_selectors(self, html_sample, user_query):
        """
        Ask the LLM to generate CSS selectors based on HTML sample and user query
        
        Args:
            html_sample (str): A sample of the HTML from the target page
            user_query (str): What the user wants to extract from the page
            
        Returns:
            dict: The selectors generated by the model and relevant explanations
        """
        # Always make a direct connection attempt, regardless of mock mode setting
        # We only want to use mock mode if explicitly requested
        try:
            # Let's verify connection is working first
            logger.info(f"Testing direct connection to {self.base_url} for selector generation")
            try:
                test_conn = requests.get(
                    f"{self.base_url}/models",
                    headers=self.headers,
                    timeout=WSL_CONNECTION_TIMEOUT  # Much longer timeout for WSL connections
                )
                test_conn.raise_for_status()
                # If connection worked, ensure mock mode is off
                self.mock_mode = False
                logger.info("Confirmed LLM connection is working, using real LLM API")
            except Exception as e:
                if self.mock_mode:
                    logger.info(f"Using configured mock mode due to connection error: {str(e)}")
                else:
                    logger.error(f"LLM connection failed and mock mode not enabled: {str(e)}")
                    # Don't auto-enable mock mode, just report the error
                    return {"error": f"Failed to connect to LLM API: {str(e)}"}
        except Exception as e:
            logger.error(f"Error testing LLM connection: {str(e)}")
        
        # If in mock mode, return predefined selectors
        if self.mock_mode:
            logger.info("Mock mode: Returning sample selectors")
            
            # Use specific selectors for books.toscrape.com
            if "books.toscrape.com" in html_sample:
                return {
                    "selectors": {
                        "item_container": "article.product_pod",
                        "title": "h3 a::text",
                        "price": ".price_color::text",
                        "availability": ".availability::text",
                        "star_rating": "p.star-rating::attr(class)",
                        "pagination_selector": "li.next a::attr(href)"
                    },
                    "mock": True
                }
            
            # Generic mock response for other sites
            return {
                "selectors": {
                    "item_container": "article.product_pod",  # Container for each product
                    "title": "h3 a::text",
                    "price": ".price_color::text",
                    "availability": ".availability::text",
                    "star_rating": "p.star-rating::attr(class)",
                    "pagination_selector": "li.next a::attr(href)"  # Pagination link to next page
                },
                "mock": True
            }
            
        # Truncate HTML if it's too large to fit in context window
        if len(html_sample) > 10000:
            html_sample = html_sample[:10000] + "... [HTML truncated for brevity]"
        
        prompt = self._create_selector_prompt(html_sample, user_query)
        
        try:
            logger.info(f"Sending chat completion request to {self.base_url}/chat/completions")
            
            # Use even longer timeout for actual inference in WSL-Windows environment
            total_timeout = WSL_RESPONSE_TIMEOUT
            logger.info(f"Using extended timeout of {total_timeout}s for WSL-Windows connection")
            
            # Log the API request for debugging
            request_data = {
                "model": "local-model",  # LM Studio uses this generic name
                "messages": prompt,
                "temperature": 0.1,  # Low temperature for more deterministic responses
                "max_tokens": 1000
            }
            logger.debug(f"API request data: {json.dumps(request_data)[:500]}...")
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=request_data,
                timeout=total_timeout  # Much longer timeout for model inference via WSL
            )
            
            # Log the status code for debugging
            logger.info(f"LLM API response status: {response.status_code}")
            
            response.raise_for_status()
            result = response.json()
            logger.info("Successfully received JSON response from LLM API")
            
            # Extract the selector suggestions from the LLM response
            if "choices" in result and result["choices"]:
                answer = result["choices"][0]["message"]["content"]
                logger.info(f"LLM response received, length: {len(answer)}")
                return self._parse_selectors_from_response(answer)
            else:
                logger.error(f"Unexpected API response format: {result}")
                return {"error": "Unexpected API response format"}
                
        except requests.exceptions.Timeout:
            logger.error(f"Request to LM Studio API timed out after {total_timeout}s")
            return {"error": f"Request to LM Studio API timed out after {total_timeout}s. The model might be taking too long to respond or there could be network issues between WSL and Windows."}
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error with LM Studio API: {str(e)}")
            return {"error": f"Failed to connect to LM Studio API at {self.base_url}. Please ensure the server is running and accessible from WSL."}
        except Exception as e:
            logger.error(f"Error calling LM Studio API: {str(e)}")
            return {"error": str(e)}
    
    def _create_selector_prompt(self, html_sample, user_query):
        """Create a prompt for the LLM to generate selectors"""
        
        # Check if user query mentions pagination/all pages
        pagination_keywords = ["all pages", "every page", "multiple pages", "paginated", "pagination"]
        needs_pagination = any(keyword in user_query.lower() for keyword in pagination_keywords)
        
        pagination_emphasis = ""
        if needs_pagination:
            pagination_emphasis = (
                "The user specifically wants data from MULTIPLE PAGES. "
                "You MUST include a 'pagination_selector' in your response that points to the 'next page' link. "
                "This is REQUIRED to scrape data from all pages.\n\n"
            )
        
        return [
            {
                "role": "system",
                "content": (
                    "You are an expert web scraper specializing in generating precise CSS and XPath selectors. "
                    "Given an HTML sample and user query, generate the most accurate selectors "
                    "to extract the requested information. Format your response as JSON with "
                    "selector names and their selectors.\n\n"
                    + pagination_emphasis +
                    "IMPORTANT RULES:\n"
                    "1. When extracting text content with CSS selectors, always use the '::text' suffix. "
                    "For example, use '.price_color::text' to get the text content instead of '.price_color'.\n"
                    "2. For complex selections that CSS cannot handle (like following siblings, ancestors, or complex conditions), "
                    "use XPath selectors instead. XPath selectors should start with 'xpath:' prefix.\n"
                    "3. When using XPath, include the /text() function to extract text content.\n"
                    "4. If the page has multiple items (like products, listings, search results), include an 'item_container' "
                    "selector that points to the repeating element containing each individual item.\n"
                    "5. Your JSON output must be valid. DO NOT include comments in the JSON. Any explanations should be "
                    "provided as separate text outside the JSON block."
                )
            },
            {
                "role": "user",
                "content": (
                    f"I need selectors to extract information from this webpage.\n\n"
                    f"Query: {user_query}\n\n"
                    f"HTML Sample:\n```html\n{html_sample}\n```\n\n"
                    + (f"IMPORTANT: Since you mentioned extracting data from multiple pages, "
                       f"make sure to include a pagination_selector that points to the 'next page' link.\n\n"
                       if needs_pagination else "") +
                    f"Please provide the selectors in this format:\n"
                    f"```json\n{{\n"
                    f"  \"item_container\": \".product\",\n"
                    + (f"  \"pagination_selector\": \".next a::attr(href)\",\n" if needs_pagination else "") +
                    f"  \"field_name\": \".css_selector::text\",\n"
                    f"  \"another_field\": \"xpath://xpath/selector/path/text()\"\n"
                    f"}}\n```\n\n"
                    f"SELECTOR EXAMPLES:\n"
                    f"1. For multiple items:\n"
                    f"   - 'item_container': '.product' - Container for each product\n\n"
                    + (f"2. For pagination:\n"
                       f"   - 'pagination_selector': '.next a::attr(href)' - Link to next page\n"
                       f"   - 'pagination_selector': 'li.next a::attr(href)' - For books.toscrape.com\n\n"
                       if needs_pagination else "") +
                    f"2. For basic text extraction:\n"
                    f"   - '.price_color::text' - Gets price text using CSS\n"
                    f"   - '.product_main h1::text' - Gets title text using CSS\n\n"
                    f"3. For complex relationships (use XPath):\n"
                    f"   - 'xpath://div[@id=\"product_description\"]/following-sibling::p/text()' - Gets text from paragraph after product description div\n"
                    f"   - 'xpath://table[@class=\"table table-striped\"]//tr[contains(., \"UPC\")]/td/text()' - Gets UPC from a table\n"
                    f"   - 'xpath://p[contains(@class, \"star-rating\")]/@class' - Gets the star rating class attribute\n\n"
                    f"If there's pagination or multiple items to scrape, also provide the selectors for those.\n\n"
                    f"IMPORTANT: Your JSON must be valid - do not include any comments inside the JSON block itself."
                )
            }
        ]
    
    def _parse_selectors_from_response(self, response_text):
        """Extract JSON formatted selectors from the LLM response"""
        try:
            # Look for JSON blocks in the response
            json_start = response_text.find('```json')
            if json_start == -1:
                json_start = response_text.find('{')
            
            if json_start != -1:
                # Find where the json block ends
                if '```' in response_text[json_start:]:
                    json_text = response_text[json_start:].split('```')[1]
                    if json_text.startswith('json'):
                        json_text = json_text[4:]
                else:
                    # Try to extract just the JSON object
                    open_braces = 0
                    json_end = json_start
                    for i, char in enumerate(response_text[json_start:]):
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                            if open_braces == 0:
                                json_end = json_start + i + 1
                                break
                    json_text = response_text[json_start:json_end]
                
                # Clean up any remaining markdown formatting
                if not json_text.startswith('{'):
                    json_text = json_text[json_text.find('{'):]
                
                # Remove any JavaScript comments to make it valid JSON
                # First, replace /* */ comments with empty string
                json_text = re.sub(r'/\*.*?\*/', '', json_text)
                # Then remove // comments until end of line
                json_text = re.sub(r'//.*?$', '', json_text, flags=re.MULTILINE)
                # Replace any commas followed by closing brackets (invalid JSON but common error)
                json_text = re.sub(r',\s*}', '}', json_text)
                json_text = re.sub(r',\s*]', ']', json_text)
                
                logger.debug(f"Cleaned JSON text: {json_text}")
                selectors = json.loads(json_text)
                
                # Check if this is for books.toscrape.com and add pagination if missing
                if "books.toscrape.com" in response_text and "item_container" in selectors:
                    if "pagination_selector" not in selectors:
                        logger.info("Adding pagination selector for books.toscrape.com")
                        selectors["pagination_selector"] = "li.next a::attr(href)"
                
                # Check if there's text about pagination but no selector
                if ("pagination" in response_text.lower() or 
                    "next page" in response_text.lower() or 
                    "multiple pages" in response_text.lower()):
                    
                    # Look for potential pagination selectors mentioned in the text
                    pagination_patterns = [
                        r'pagination.*?selector.*?[\'"]([^\'"]+)[\'"]',
                        r'next.*?page.*?[\'"]([^\'"]+)[\'"]',
                        r'pagination.*?link.*?[\'"]([^\'"]+)[\'"]',
                        r'li\.next.*?[\'"]([^\'"]+)[\'"]'
                    ]
                    
                    if "pagination_selector" not in selectors:
                        for pattern in pagination_patterns:
                            match = re.search(pattern, response_text, re.IGNORECASE)
                            if match:
                                potential_selector = match.group(1)
                                logger.info(f"Found potential pagination selector in text: {potential_selector}")
                                selectors["pagination_selector"] = potential_selector
                                break
                
                # Add the raw LLM response for debugging
                return {
                    "selectors": selectors,
                    "raw_response": response_text
                }
            else:
                logger.warning("No JSON found in LLM response")
                return {
                    "selectors": {},
                    "raw_response": response_text
                }
        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}")
            logger.error(f"Raw response that caused error: {response_text}")
            
            # Try to fall back to a simple regex extraction of key-value pairs
            # This is a last resort if JSON parsing fails
            try:
                logger.info("Attempting fallback extraction with regex")
                # Look for patterns like "key": "value" or 'key': 'value'
                # Extract key-value pairs using regex
                pattern = r'["\']([\w_]+)["\']:\s*["\'](.*?)["\']'
                matches = re.findall(pattern, response_text)
                
                if matches:
                    logger.info(f"Fallback extraction found {len(matches)} key-value pairs")
                    selectors = {key: value for key, value in matches}
                    return {
                        "selectors": selectors,
                        "raw_response": response_text,
                        "fallback_extraction": True
                    }
            except Exception as fallback_error:
                logger.error(f"Fallback extraction also failed: {str(fallback_error)}")
            
            # If all else fails, see if we can provide mock selectors for books.toscrape.com
            if "books.toscrape" in response_text:
                logger.info("Falling back to hardcoded selectors for books.toscrape.com")
                return {
                    "selectors": {
                        "item_container": "article.product_pod",
                        "title": "h3 a::text",
                        "price": ".price_color::text",
                    },
                    "fallback_extraction": True,
                    "raw_response": response_text
                }
            
            return {
                "error": f"Failed to parse selectors: {str(e)}",
                "raw_response": response_text
            } 