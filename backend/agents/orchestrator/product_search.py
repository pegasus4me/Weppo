import logging
import json
from typing import Optional, Type, List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from ..mcp.shopify_server import ShopifyMCPServer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ShopifySearchInput(BaseModel):
    """Input schema for Shopify search tool"""
    query: str = Field(description="Search query for products")

class ShopifySearchTool(BaseTool):
    """Custom tool for Shopify product search that handles content string responses"""
    name: str = "product_search"
    description: str = "Search for products in the store catalog. Input should be a search query string."
    args_schema: Type[BaseModel] = ShopifySearchInput
    mcp_server: ShopifyMCPServer = Field(description="MCP server instance")
    
    def __init__(self, mcp_server: ShopifyMCPServer, **kwargs):
        super().__init__(mcp_server=mcp_server, **kwargs)
    
    def _clean_tags(self, tags: List[str]) -> List[str]:
        """Clean tags by replacing '=>' with ':' and removing prefixes."""
        import re
        cleaned = []
        for tag in tags:
            tag = tag.replace(' => ', ': ')
            tag = re.sub(r'^(allbirds|loop)::', '', tag)
            cleaned.append(tag)
        return cleaned
    
    def _format_product_to_markdown(self, product: Dict[str, Any]) -> str:
        """Format a single product into markdown with title as a link."""
        title = product.get('title', 'Unknown Product')
        url = product.get('url', 'URL not available')
        price_range = product.get('price_range', {})
        price = f"{price_range.get('min', 'Price not available')} {price_range.get('currency', '')}"
        product_type = product.get('product_type', 'Unknown Type')
        description = product.get('description', 'No description available')
        description = description[:100] + "..." if len(description) > 100 else description
        
        # Get key features from tags
        tags = self._clean_tags(product.get('tags', []))
        key_features = [tag for tag in tags if any(key in tag.lower() for key in ['material', 'style', 'gender', 'edition'])]
        
        variants = product.get('variants', [])
        available = any(variant.get('available', False) for variant in variants)
        availability = "In stock" if available else "Out of stock"
        
        # Format variants more concisely
        variant_info = ""
        if variants:
            sizes = [v.get('title', 'Unknown') for v in variants if v.get('available', False)]
            if sizes:
                variant_info = f"\n- **Available Sizes**: {', '.join(sizes)}"
        
        return f"""### [{title}]({url})
            - **Price**: {price}
            - **Availability**: {availability}
            - **Key Features**:
            - Type: {product_type}
            - {chr(10) + '  - '.join(key_features[:3])}
            - **Description**: {description}{variant_info}
            """
    
    def _parse_content(self, content: Any) -> Dict[str, Any]:
        """Parse content to extract products and metadata."""
        try:
            if not isinstance(content, list) or not content:
                logger.error(f"Content is not a list or is empty: {type(content)}")
                return {"products": [], "pagination": {}, "filters": []}
            
            if 'text' not in content[0]:
                logger.error("No 'text' field in content[0]")
                return {"products": [], "pagination": {}, "filters": []}
            
            # Parse the 'text' field as JSON
            text_content = content[0]['text']
            try:
                data = json.loads(text_content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse 'text' as JSON: {str(e)}")
                logger.debug(f"Content[0]['text']: {text_content[:200]}...")
                return {"products": [], "pagination": {}, "filters": []}
            
            products = data.get('products', [])
            pagination = data.get('pagination', {})
            filters = data.get('available_filters', [])
            return {"products": products, "pagination": pagination, "filters": filters}
            
        except Exception as e:
            logger.error(f"Error parsing content: {str(e)}")
            logger.debug(f"Content structure: {content}")
            return {"products": [], "pagination": {}, "filters": []}
    
    def _run(self, query: str) -> str:
        """Execute the tool synchronously"""
        try:
            logger.info(f"Searching products with query: {query}")
            result = self.mcp_server.get_products(query)
            
            # Log the full response for debugging
            logger.debug(f"Full API response: {json.dumps(result, indent=2)[:500]}...")
            
            # Check for error in response
            if 'error' in result:
                logger.error(f"Error from MCP server: {result['error']}")
                return f"Error searching products: {result['error']}"
            
            if result.get('result', {}).get('isError', False):
                logger.error("MCP server returned isError=True")
                return "Error: MCP server reported an error"
            
            # Extract content
            content = None
            if 'result' in result and 'content' in result['result']:
                content = result['result']['content']
            elif 'content' in result:
                content = result['content']
            else:
                logger.error(f"No content found in response structure: {list(result.keys())}")
                return "Error: No content found in server response"
            
            # Parse content to extract products and metadata
            parsed_data = self._parse_content(content)
            products = parsed_data['products']
            pagination = parsed_data['pagination']
            filters = parsed_data['filters']
            
            if not products:
                logger.warning("No products found in content")
                return "No products found matching your search criteria."
            
            
            # Format products as markdown
            markdown = "# Allbirds Products\n\n"
            for i, product in enumerate(products):  # Removed limit to show all products
                try:
                    if not isinstance(product, dict):
                        logger.warning(f"Product {i+1} is not a dict: {type(product)}")
                        continue
                    markdown += self._format_product_to_markdown(product) + "\n"
                except Exception as e:
                    logger.error(f"Error formatting product {i+1}: {str(e)}")
                    logger.debug(f"Product data: {product}")
                    continue
            
            if not markdown.strip().endswith("Products"):
                # Add pagination info
                if pagination.get('hasNextPage', False):
                    markdown += f"\n**Pagination**: Showing page {pagination.get('currentPage', 1)} of {pagination.get('maxPages', 1)}. Would you like to see more results?\n"
                
                # Add available filters
                filter_labels = [f.get('label', 'Unknown') for f in filters]
                markdown += f"\n**Available Filters**: {', '.join(filter_labels)}\n"
            else:
                markdown += "No valid products could be formatted.\n"
            
            # Save to file
            try:
                with open('products.md', 'w') as f:
                    f.write(markdown)
                logger.info("Saved formatted output to 'products.md'")
            except Exception as e:
                logger.error(f"Error saving markdown file: {str(e)}")
            
            return markdown
            
        except Exception as e:
            logger.error(f"Error in product search: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error searching products: {str(e)}"
    
    async def _arun(self, query: str) -> str:
        """Execute the tool asynchronously"""
        return self._run(query)
    
    class Config:
        """Pydantic config to allow arbitrary types"""
        arbitrary_types_allowed = True