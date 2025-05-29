"""
This module is responsible for:
    - Connecting to the Shopify MCP server.
"""

import requests
from typing import Dict, Any
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ShopifyMCPServer:
    """
    Storefront MCP server
    """
    def __init__(self, store_domain: str):
        # Clean the domain - remove protocol and trailing slashes
        self.store_domain = store_domain.replace('https://', '').replace('http://', '').replace('www.', '').rstrip('/')
        self.server_url = f"https://{self.store_domain}/api/mcp"
        self.timeout = 30  # Request timeout in seconds
        logger.info(f"Initialized Shopify MCP Server for domain: {self.store_domain}")
    
    def get_products(self, query: str):
        """
          Get products from the Shopify store based on query.
        
        Args:
            query (str): Search query for products
            
        Returns:
            Dict[str, Any]: Response from MCP server
        
        """
        try:
            logger.info(f"Making request to {self.server_url} with query: {query}")
            response = requests.post(self.server_url,
                headers={
                    'Content-Type': 'application/json'
                },
                json={
                    'jsonrpc': '2.0',
                    'method': 'tools/call',
                    'id': 1,
                    'params': {
                        'name': 'search_shop_catalog',
                        'arguments': {
                            'query': query,
                            'context': 'retrieve only the products from the catalog'
                        }
                    }
                },
                timeout=self.timeout
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            result = response.json()
            

            
            # Log specific parts of the response
            if 'result' in result:
                if 'products' in result['result']:
                    products = result['result']['products']
                    print("==" * 30)
                    logger.info(f"Number of products found: {len(products)}")
                    print("==" * 30)
                    if products:
                        logger.info("First product structure:")
                else:
                    logger.warning("No 'products' key in result")
            else:
                logger.warning("No 'result' key in response")
            
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": str(e)}
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            return {"error": "Invalid JSON response"}
