from flask import Flask, render_template, request, jsonify
import os
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy import Selector
import requests
from multiprocessing import Process, Queue
import json
import tempfile
import logging
from llm_api import LMStudioAPI, POTENTIAL_API_URLS, WSL_CONNECTION_TIMEOUT
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
        self.selectors = selectors or {}
    
    def parse(self, response):
        item = {}
        for field_name, selector in self.selectors.items():
            try:
                item[field_name] = response.css(selector).get()
                self.logger.info(f"Extracted {field_name}: {item[field_name]}")
            except Exception as e:
                self.logger.error(f"Error extracting {field_name}: {str(e)}")
        return item

def test_selector(url, selector):
    try:
        logger.info(f"Testing selector: {selector} on URL: {url}")
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        sel = Selector(text=response.text)
        result = sel.css(selector).get()
        
        logger.info(f"Selector test result: {result}")
        
        if result is None:
            return False, "Selector returned no results"
        return True, result.strip() if result else result
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return False, f"Failed to fetch URL: {str(e)}"
    except Exception as e:
        logger.error(f"Selector error: {str(e)}")
        return False, f"Error processing selector: {str(e)}"

@app.route('/test-selector', methods=['POST'])
def test_selector_route():
    try:
        data = request.json
        url = data.get('url')
        selector = data.get('selector')
        
        if not url or not selector:
            return jsonify({
                'success': False,
                'error': 'URL and selector are required'
            }), 400
        
        success, result = test_selector(url, selector)
        return jsonify({
            'success': success,
            'result': result
        })
    except Exception as e:
        logger.error(f"Error in test_selector_route: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
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
            return jsonify({
                'success': True,
                'selectors': result["selectors"],
                'warning': "Using mock mode - AI-generated selectors are simulated."
            })
            
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

def run_spider(start_url, selectors, output_file):
    try:
        process = CrawlerProcess(settings={
            'FEEDS': {
                output_file: {
                    'format': 'json',
                    'overwrite': True,
                },
            },
            'LOG_LEVEL': 'DEBUG'
        })
        
        process.crawl(DynamicSpider, start_url=start_url, selectors=selectors)
        process.start()
    except Exception as e:
        logger.error(f"Error in run_spider: {str(e)}")
        raise

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = request.json
        start_url = data.get('start_url')
        selectors = data.get('selectors', {})
        
        logger.info(f"Scraping URL: {start_url} with selectors: {selectors}")
        
        # Test URL accessibility
        try:
            response = requests.head(start_url)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"URL access error: {str(e)}")
            return jsonify({'error': f'Could not access URL: {str(e)}'}), 400

        # Create a temporary file for output
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            output_file = tmp.name
        
        # Run the spider in a separate process
        p = Process(target=run_spider, args=(start_url, selectors, output_file))
        p.start()
        p.join()
        
        # Read the results
        try:
            with open(output_file, 'r') as f:
                results = json.load(f)
            os.unlink(output_file)  # Clean up the temporary file
            logger.info(f"Scraping results: {results}")
            return jsonify({'success': True, 'data': results})
        except Exception as e:
            logger.error(f"Error reading results: {str(e)}")
            return jsonify({'error': f'Error reading results: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error in scrape route: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

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

if __name__ == '__main__':
    app.run(debug=True) 