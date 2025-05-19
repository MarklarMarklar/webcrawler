# Web Scraper with LLM Integration

A Flask web application that combines Scrapy for web scraping with LLM integration for automatically generating CSS selectors.

## Features

- **Automatic CSS Selector Generation**: Uses LM Studio API to analyze web pages and generate CSS selectors
- **Visual Scraper Configuration**: User-friendly UI for setting up scraping tasks
- **Real-time Selector Testing**: Test selectors directly in the browser
- **WSL-Windows Connectivity**: Support for connecting to LM Studio running in Windows from WSL
- **Mock Mode**: Fallback option when LLM connection is unavailable

## System Requirements

- Python 3.8+
- Flask
- Scrapy
- LM Studio with Qwen2.5 Coder (or similar LLM model) for AI features

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/MarklarMarklar/webcrawler.git
   cd webcrawler
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Configuration

### LLM API Connection

The application can connect to LM Studio running on:
- Same machine (localhost:1234)
- WSL-to-Windows (172.31.64.1:1234)
- Any custom endpoint

Set the environment variable `LM_STUDIO_API_URL` to your LM Studio endpoint, or configure it in the web UI.

### Offline Mode

If no LLM connection is available, enable mock mode through:
- Setting the environment variable: `LLM_MOCK_MODE=true`
- Using the UI checkbox "Use Mock Mode"

## Usage

1. Start the Flask application:
   ```
   python app.py
   ```

2. Open your browser at http://127.0.0.1:5000/

3. Configure your scraper:
   - Enter the target URL
   - Describe what data you want to extract
   - Generate selectors with AI assistance
   - Test and refine the selectors
   - Run the scraper

## Troubleshooting LLM Connection

For WSL-to-Windows connections:
- Run the diagnostics script: `python test_llm_direct.py`
- Ensure Windows Firewall allows connections
- Try alternative connection methods via the UI

## License

MIT

## Acknowledgements

- [Scrapy](https://scrapy.org/) for web scraping
- [Flask](https://flask.palletsprojects.com/) for the web framework
- [LM Studio](https://lmstudio.ai/) for the local LLM server 