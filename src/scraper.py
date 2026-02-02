"""
Amazon ASIN Scraper for Price and BSR (Best Seller Rank)
"""

import re
import time
import random
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent


@dataclass
class ProductData:
    """Data class for Amazon product information."""
    asin: str
    title: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    bsr: Optional[str] = None
    bsr_value: Optional[int] = None
    bsr_category: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class AmazonScraper:
    """Scraper for Amazon product price and BSR data."""

    BASE_URL = "https://www.amazon.com/dp/{asin}"

    def __init__(self, marketplace: str = "com"):
        """
        Initialize the scraper.

        Args:
            marketplace: Amazon marketplace (com, co.uk, de, etc.)
        """
        self.marketplace = marketplace
        self.base_url = f"https://www.amazon.{marketplace}/dp/{{asin}}"
        self.ua = UserAgent()
        self.session = requests.Session()

    def _get_headers(self) -> dict:
        """Generate request headers with random user agent."""
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _fetch_page(self, asin: str) -> Optional[str]:
        """
        Fetch the Amazon product page HTML.

        Args:
            asin: Amazon Standard Identification Number

        Returns:
            HTML content or None if request fails
        """
        url = self.base_url.format(asin=asin)

        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching page for ASIN {asin}: {e}")
            return None

    def _parse_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from page."""
        title_elem = soup.find("span", {"id": "productTitle"})
        if title_elem:
            return title_elem.get_text(strip=True)
        return None

    def _parse_price(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
        """
        Extract price from the product page.

        Returns:
            Tuple of (price_string, price_float)
        """
        price_selectors = [
            {"class_": "a-price-whole"},
            {"id": "priceblock_ourprice"},
            {"id": "priceblock_dealprice"},
            {"id": "priceblock_saleprice"},
            {"class_": "a-offscreen"},
        ]

        # Try apex price first (most common)
        apex_price = soup.find("span", {"class": "a-price"})
        if apex_price:
            offscreen = apex_price.find("span", {"class": "a-offscreen"})
            if offscreen:
                price_text = offscreen.get_text(strip=True)
                price_value = self._extract_price_value(price_text)
                return price_text, price_value

        # Try other selectors
        for selector in price_selectors:
            price_elem = soup.find("span", selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                if "$" in price_text or "£" in price_text or "€" in price_text:
                    price_value = self._extract_price_value(price_text)
                    return price_text, price_value

        return None, None

    def _extract_price_value(self, price_text: str) -> Optional[float]:
        """Extract numeric value from price string."""
        # Remove currency symbols and extract number
        match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
        if match:
            try:
                return float(match.group().replace(",", ""))
            except ValueError:
                pass
        return None

    def _parse_bsr(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Extract Best Seller Rank from the product page.

        Returns:
            Tuple of (bsr_string, bsr_value, category)
        """
        bsr_patterns = [
            r'#([\d,]+)\s+in\s+([^(\n]+)',
            r'Best Sellers Rank[:\s]*#?([\d,]+)\s+in\s+([^(\n]+)',
        ]

        # Check product details section
        details_section = soup.find("div", {"id": "detailBulletsWrapper_feature_div"})
        if details_section:
            text = details_section.get_text()
            for pattern in bsr_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                    bsr_value = int(match.group(1).replace(",", ""))
                    category = match.group(2).strip()
                    return bsr_str, bsr_value, category

        # Check product information table
        tables = soup.find_all("table", {"id": "productDetails_detailBullets_sections1"})
        for table in tables:
            text = table.get_text()
            for pattern in bsr_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                    bsr_value = int(match.group(1).replace(",", ""))
                    category = match.group(2).strip()
                    return bsr_str, bsr_value, category

        # Check entire page as fallback
        page_text = soup.get_text()
        for pattern in bsr_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                bsr_value = int(match.group(1).replace(",", ""))
                category = match.group(2).strip()
                return bsr_str, bsr_value, category

        return None, None, None

    def scrape(self, asin: str) -> ProductData:
        """
        Scrape price and BSR for a given ASIN.

        Args:
            asin: Amazon Standard Identification Number

        Returns:
            ProductData object with scraped information
        """
        url = self.base_url.format(asin=asin)
        result = ProductData(asin=asin, url=url)

        html = self._fetch_page(asin)
        if not html:
            result.error = "Failed to fetch page"
            return result

        soup = BeautifulSoup(html, "lxml")

        # Check for CAPTCHA or bot detection
        if "Enter the characters you see below" in html or "api-services-support@amazon.com" in html:
            result.error = "Bot detection triggered - CAPTCHA required"
            return result

        # Parse data
        result.title = self._parse_title(soup)
        result.price, result.price_value = self._parse_price(soup)
        result.bsr, result.bsr_value, result.bsr_category = self._parse_bsr(soup)

        return result

    def scrape_multiple(self, asins: list[str], delay: float = 2.0) -> list[ProductData]:
        """
        Scrape multiple ASINs with delay between requests.

        Args:
            asins: List of ASINs to scrape
            delay: Delay between requests in seconds

        Returns:
            List of ProductData objects
        """
        results = []
        for i, asin in enumerate(asins):
            result = self.scrape(asin)
            results.append(result)

            # Add delay between requests (with some randomization)
            if i < len(asins) - 1:
                time.sleep(delay + random.uniform(0, 1))

        return results


def scrape_asin(asin: str, marketplace: str = "com") -> ProductData:
    """
    Convenience function to scrape a single ASIN.

    Args:
        asin: Amazon Standard Identification Number
        marketplace: Amazon marketplace (com, co.uk, de, etc.)

    Returns:
        ProductData object with scraped information
    """
    scraper = AmazonScraper(marketplace=marketplace)
    return scraper.scrape(asin)
