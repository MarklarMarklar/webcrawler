"""
Script to modify the Flask app to work without LLM connection
This creates a version that uses mock LLM responses for development
"""
import json
import time

class MockLLMAPI:
    """
    A mock LLM API that returns predefined responses
    This allows development of the web UI without requiring a working LLM
    """
    def __init__(self):
        print("Initializing Mock LLM API")
        
    def test_connection(self, *args, **kwargs):
        """Simulate a successful connection test"""
        time.sleep(0.5)  # Simulate network delay
        return {
            "success": True,
            "models": ["mock-model"]
        }
    
    def generate_selectors(self, html_sample, user_query):
        """Generate mock selectors based on common patterns"""
        time.sleep(1)  # Simulate LLM thinking
        
        # Prepare some realistic selectors based on common web patterns
        selectors = {}
        
        # Basic selectors for common data types based on the query
        if "price" in user_query.lower():
            selectors["price"] = ".product_main .price_color::text"
        
        if "title" in user_query.lower():
            selectors["title"] = ".product_main h1::text"
            
        if "availability" in user_query.lower() or "stock" in user_query.lower():
            selectors["availability"] = ".product_main .availability::text"
            
        if "description" in user_query.lower():
            selectors["description"] = "#product_description + p::text"
            
        if "category" in user_query.lower():
            selectors["category"] = ".breadcrumb li:nth-child(3) a::text"
            
        if "image" in user_query.lower():
            selectors["image"] = ".item.active img::attr(src)"
            
        if "review" in user_query.lower() or "rating" in user_query.lower():
            selectors["rating"] = ".star-rating::attr(class)"
            
        # Add pagination if mentioned
        if "pagination" in user_query.lower() or "next page" in user_query.lower():
            selectors["pagination"] = ".next a::attr(href)"
            
        # If no specific elements matched, provide generic selectors
        if not selectors:
            selectors = {
                "title": "h1::text",
                "price": ".price::text",
                "content": "p::text",
                "links": "a::attr(href)",
                "images": "img::attr(src)"
            }
            
        return {
            "selectors": selectors,
            "raw_response": "Mock response from LLM - these are predefined selectors"
        }

print("Creating mock_config.py...")
with open("mock_config.py", "w") as f:
    f.write("""
# Mock configuration to use instead of LLM
from setup_without_llm import MockLLMAPI

# Create the mock API instance
mock_llm_api = MockLLMAPI()
""")

print("Creating patch for app.py...")
patch_instructions = """
To use the application without LLM:

1. Add this line at the top of app.py:
   from mock_config import mock_llm_api

2. Replace all instances of:
   llm_api.test_connection(...)
   with:
   mock_llm_api.test_connection(...)

3. Replace all instances of:
   llm_api.generate_selectors(...)
   with:
   mock_llm_api.generate_selectors(...)

Or simply run this command to do all the replacements:
sed -i 's/llm_api\\.test_connection/mock_llm_api.test_connection/g' app.py
sed -i 's/llm_api\\.generate_selectors/mock_llm_api.generate_selectors/g' app.py
"""

print("=" * 60)
print("MOCK LLM SETUP")
print("=" * 60)
print("This script has created a mock LLM implementation that returns predefined")
print("selector patterns. This allows you to develop the web interface without")
print("requiring a connection to the actual LLM Studio.")
print("\nTo use the mock implementation:")
print(patch_instructions)
print("\nAfter making these changes, restart your Flask app with:")
print("python app.py")
print("\nThe web interface will now work with mock LLM responses.")
print("=" * 60) 