import sys
import argparse
import time
import base64
import os
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from PyPDF2 import PdfMerger

def get_candidate_urls(base_url):
    print(f"Fetching {base_url} to extract candidate URLs...")
    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {base_url}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    parsed_base = urlparse(base_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
    
    candidates = []
    seen = set()
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # remove fragments
        href = href.split('#')[0]
        if not href:
            continue
            
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        # Keep URLs from the same domain
        if parsed_url.netloc == parsed_base.netloc:
            # Avoid self-referencing links if they are exactly the base_url
            if full_url not in seen:
                seen.add(full_url)
                # optionally parse title
                title = a_tag.get_text(strip=True) or href
                candidates.append((full_url, title))
                
    return candidates

def render_and_save_pdf(driver, url, output_path):
    print(f"Rendering {url}...")
    driver.get(url)
    
    # Wait for MathJax to process
    # This checks multiple possible MathJax signatures (v2 and v3)
    mathjax_wait_script = """
    return (function() {
        if (typeof MathJax === 'undefined') {
            return true; // No MathJax on this page
        }
        if (typeof MathJax.startup !== 'undefined' && MathJax.startup.promise) {
            // MathJax 3
            return document.querySelector('mjx-container') !== null || true; // just a rough check
        }
        if (typeof MathJax.Hub !== 'undefined' && MathJax.Hub.queue) {
            // MathJax 2
            return MathJax.Hub.queue.pending === 0;
        }
        return false;
    })();
    """
    
    # Also we give it some raw time to let JS execute
    time.sleep(2)
    
    try:
        WebDriverWait(driver, 10).until(lambda d: d.execute_script(mathjax_wait_script))
    except Exception as e:
        print(f"Wait for MathJax timed out. Generating anyway...")
    
    # Give a bit more processing time after detection
    time.sleep(1)

    # Use Chrome DevTools Protocol to print PDF
    # https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-printToPDF
    print_options = {
        "landscape": False,
        "displayHeaderFooter": False,
        "printBackground": True,
        "preferCSSPageSize": True,
    }
    
    result = driver.execute_cdp_cmd("Page.printToPDF", print_options)
    pdf_base64 = result['data']
    
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(pdf_base64))
        
    print(f"Saved PDF to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Convert web pages to PDF for eBook creation.")
    parser.add_argument("url", nargs='?', help="Base URL to extract candidate URLs from")
    args = parser.parse_args()

    base_url = args.url
    if not base_url:
        base_url = input("Enter the target URL: ").strip()
        
    if not base_url:
        print("URL is required.")
        return

    candidates = get_candidate_urls(base_url)
    if not candidates:
        print("No candidate URLs found.")
        return

    print("\n--- Candidate URLs ---")
    for i, (url, title) in enumerate(candidates, 1):
        # Truncate title for display if it's too long
        display_title = title if len(title) < 60 else title[:57] + "..."
        print(f"[{i:02d}] {display_title} ({url})")

    print("\nSelect URLs to convert to PDF.")
    print("Example: '1-5, 8, 11' or 'all'")
    selection = input("Selection (default 'all'): ").strip().lower()

    selected_urls = []
    if not selection or selection == 'all':
        selected_urls = [url for url, _ in candidates]
    else:
        # Parse complex selection like 1-5, 8
        parts = selection.split(',')
        indices = set()
        for p in parts:
            p = p.strip()
            if '-' in p:
                try:
                    start, end = map(int, p.split('-'))
                    indices.update(range(start, end + 1))
                except ValueError:
                    continue
            else:
                try:
                    indices.add(int(p))
                except ValueError:
                    continue
                    
        for idx in sorted(list(indices)):
            if 1 <= idx <= len(candidates):
                selected_urls.append(candidates[idx-1][0])

    if not selected_urls:
        print("No valid URLs selected.")
        return

    print(f"\nProceeding to convert {len(selected_urls)} pages...")
    
    # Initialize Selenium Chrome Driver
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # To reduce unnecessary output
    chrome_options.add_argument("--log-level=3")

    driver = webdriver.Chrome(options=chrome_options)
    
    output_dir = "ebook_output"
    os.makedirs(output_dir, exist_ok=True)
    
    pdf_files = []
    try:
        for i, url in enumerate(selected_urls, 1):
            pdf_path = os.path.join(output_dir, f"page_{i:03d}.pdf")
            render_and_save_pdf(driver, url, pdf_path)
            pdf_files.append(pdf_path)
    finally:
        driver.quit()
        
    if not pdf_files:
        return
        
    # Merge PDFs
    output_merged_pdf = "Final_eBook.pdf"
    print(f"\nMerging {len(pdf_files)} PDFs into '{output_merged_pdf}'...")
    merger = PdfMerger()
    for pdf in pdf_files:
        merger.append(pdf)
    
    try:
        merger.write(output_merged_pdf)
        merger.close()
        print("Merge successful!")
        
        # Clean up individual PDFs if desired?
        # for pdf in pdf_files:
        #     os.remove(pdf)
            
    except Exception as e:
        print(f"Failed to merge PDFs: {e}")

if __name__ == "__main__":
    main()
