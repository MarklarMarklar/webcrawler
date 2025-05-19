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
            return {
                "selectors": {
                    "title": "h1.product_title::text",
                    "price": "span.price::text",
                    "description": "div.product_description p::text",
                    "availability": "p.stock::text"
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
        return [
            {
                "role": "system",
                "content": (
                    "You are an expert web scraper specializing in generating precise CSS selectors. "
                    "Given an HTML sample and user query, generate the most accurate CSS selectors "
                    "to extract the requested information. Format your response as JSON with "
                    "selector names and their CSS selectors.\n\n"
                    "IMPORTANT: When extracting text content, always use the '::text' suffix in your selectors. "
                    "For example, use '.price_color::text' to get the text content instead of '.price_color' which would return the HTML element."
                )
            },
            {
                "role": "user",
                "content": (
                    f"I need CSS selectors to extract information from this webpage.\n\n"
                    f"Query: {user_query}\n\n"
                    f"HTML Sample:\n```html\n{html_sample}\n```\n\n"
                    f"Please provide the CSS selectors in this format:\n"
                    f"```json\n{{\n  \"field_name\": \"css_selector::text\",\n  \"another_field\": \"another_selector::text\"\n}}\n```\n\n"
                    f"IMPORTANT: Always use '::text' suffix when extracting text content. For example:\n"
                    f"- '.price_color::text' to get the price text\n"
                    f"- '.product_main h1::text' to get the title text\n"
                    f"- 'p.description::text' to get the description text\n\n"
                    f"If there's pagination or multiple items to scrape, also provide the selectors for those."
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
                
                selectors = json.loads(json_text)
                
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
            return {
                "error": f"Failed to parse selectors: {str(e)}",
                "raw_response": response_text
            } 