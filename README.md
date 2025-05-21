# AI-Powered Web Scraper

This web application allows users to configure and run web scraping tasks with the assistance of a locally running Large Language Model (LLM) via LM Studio. It includes features for AI-assisted selector generation, a visual selector tool, and proxying for sites that restrict iframe loading.

## Features

### Core Scraping
*   **URL Input**: Specify the starting URL for scraping.
*   **Pagination**: Define a CSS selector for the "next page" link to scrape multiple pages.
*   **Page Limit**: Control the maximum number of pages to scrape.
*   **Item Container**: Specify a CSS selector for repeating item blocks (e.g., product listings).
*   **Field Selectors**: Define individual CSS or XPath selectors for each piece of data to extract (e.g., title, price, image URL).
    *   Supports `::text` for text content and `::attr(attribute_name)` for attributes.
*   **Export Formats**: Export scraped data as JSON or CSV.
*   **Save Path**: Optionally specify a local file path to save the results, or view them directly in the browser.

### AI-Assisted Selector Generation
*   **Generate Selectors**: Based on the target URL and a natural language query (e.g., "get all book titles and prices"), the application uses a local LLM to suggest:
    *   Item container selector
    *   Pagination selector
    *   Individual field selectors
*   **LLM Connection Test**: Test connectivity to the LM Studio API.
*   **API Configuration**: Configure the LM Studio API URL and toggle mock mode (for offline development/testing).
*   **Mock Mode**: If the LLM is unavailable, the application can run in a mock mode with pre-defined responses for testing UI and basic functionality.

### Visual Selector Tool
*   **New Page**: A dedicated `/visual-selector` page.
*   **Load Target URL**: Input a URL to load it into an iframe.
    *   **Proxy**: For sites that block iframe loading (e.g., via `X-Frame-Options`), a server-side proxy (`/proxy-page`) fetches and serves the content. This attempts to rewrite base URLs for relative asset loading but may have limitations with complex JavaScript-driven sites.
*   **Click-to-Select**:
    *   Click on elements within the loaded iframe.
    *   The tool generates a basic CSS selector path for the clicked element.
    *   Prompt for a field name for the selected element.
    *   Selectors are added to a list on the page.
*   **Manual Entry**: Manually add/edit item container and pagination selectors on the visual selector page.
*   **Transfer to Main Scraper**: A "Use These Selectors & Go to Main Scraper" button collects all defined selectors and the target URL from the visual tool and populates them into the main scraper form on `index.html` using `sessionStorage`.

### Selector Testing & Refinement (on Main Scraper Page)
*   **Test Individual Selectors**: Test each field selector and the item container selector against the target URL.
    *   Displays match count.
    *   Shows a preview of the extracted text content.
    *   Shows a preview of the HTML snippet for the matched element.
*   **Refine with AI**:
    *   For each successfully tested field selector, a "Refine with AI" button appears.
    *   Clicking this sends the field name, the current selector, and the HTML snippet of its *parent element* to the LLM.
    *   The LLM is prompted to generate a new, robust, and accurate Scrapy CSS selector for the field based on the provided snippet and context.
    *   The AI's suggestion (new selector, extraction method, confidence, notes) is displayed.
    *   "Accept Suggestion" and "Discard" buttons allow the user to choose whether to update the selector input field.

### Backend
*   Flask-based web server.
*   Scrapy for the actual crawling and data extraction process.
*   Interaction with a local LLM (e.g., LM Studio) for AI features.
*   WSL compatibility considerations (longer timeouts, IP discovery helpers).

## Setup

1.  **Clone the repository.**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run LM Studio**: Ensure your local LLM server (e.g., LM Studio) is running and accessible. The application will attempt to auto-discover it or you can configure the URL in the UI.
4.  **Run the Flask application**:
    ```bash
    python webcrawler/app.py
    ```
5.  Open your web browser and navigate to `http://127.0.0.1:5000`.

## Usage

1.  **Configure AI Assistant**:
    *   Verify or update the LM Studio API URL.
    *   Test the connection.
    *   Use "Auto-discover" if unsure of the URL.
2.  **Configure Target**:
    *   Enter the "Start URL".
    *   Optionally, describe what you want to extract and click "Generate Selectors" for AI assistance.
3.  **Define Selectors**:
    *   Manually enter/edit the "Pagination Selector", "Item Container Selector", and "Field Selectors".
    *   Or, use the "Visual Selector" tool to click and generate initial selectors, then transfer them back.
4.  **Test and Refine**:
    *   Use the "Test" buttons for the container and each field selector.
    *   Use "Refine with AI" for individual field selectors to get improved suggestions from the LLM.
5.  **Set Export Options**:
    *   Choose export format (JSON/CSV).
    *   Optionally, provide a "Save Path".
6.  **Start Scraping**: Click "Start Scraping". Results will be displayed or saved to the specified file.

## Known Limitations
*   The iframe proxy for the Visual Selector might not work perfectly for all websites, especially those with complex JavaScript, ServiceWorkers, or strict CSP/CORS policies.
*   AI-generated selectors are suggestions and may require manual tweaking for optimal performance and accuracy. 