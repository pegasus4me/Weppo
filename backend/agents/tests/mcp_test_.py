import sys
import os
import logging
import json
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent.parent)
sys.path.append(project_root)

from backend.agents.mcp.shopify_server import ShopifyMCPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clean_tags(tags):
    """Clean tags by replacing '=>' with ':' and removing unnecessary prefixes."""
    import re
    cleaned = []
    for tag in tags:
        tag = tag.replace(' => ', ': ')
        tag = re.sub(r'^(allbirds|loop)::', '', tag)
        cleaned.append(tag)
    return cleaned

def format_product_to_markdown(product):
    """Format a single product into markdown with title as a link."""
    title = product['title']
    url = product['url']
    price = f"{product['price_range']['min']} {product['price_range']['currency']}"
    product_type = product['product_type']
    description = product['description'][:100] + "..." if len(product['description']) > 100 else product['description']
    tags = ", ".join(clean_tags(product['tags']))
    
    variants = product.get('variants', [])
    available = any(variant['available'] for variant in variants)
    availability = "In stock" if available else "Out of stock"
    
    variant_info = "\n".join([f"  - {v['title']}: {v['price']} {v['currency']} ({'Available' if v['available'] else 'Out of stock'})" for v in variants])
    
    return f"""### [{title}]({url})
- **Type**: {product_type}
- **Price**: {price}
- **Availability**: {availability}
- **Description**: {description}
- **Tags**: {tags}
- **Variants**:
{variant_info}
"""

def analyze_content_structure():
    """Analyze the content field and format products as markdown."""
    store_domain = "www.allbirds.com"
    mcp_server = ShopifyMCPServer(store_domain)
    
    query = "red shoes"
    logger.info(f"Testing with query: {query}")
    
    try:
        result = mcp_server.get_products(query)
        
        print("\n" + "="*80)
        print("CONTENT FIELD ANALYSIS")
        print("="*80)
        
        # Extract the content
        content = None
        if 'result' in result and 'content' in result['result']:
            content = result['result']['content']
            print("✅ Found content at: result.content")
        elif 'content' in result:
            content = result['content']
            print("✅ Found content at: content")
        else:
            print("❌ No content field found")
            return
        
        print(f"\nContent type: {type(content)}")
        print(f"Content length: {len(str(content))}")
        
        # Check if content is a list and has a 'text' field
        if not isinstance(content, list) or not content or 'text' not in content[0]:
            print("❌ Content is not a list or missing 'text' field")
            return
        
        # Parse the 'text' field as JSON
        try:
            data = json.loads(content[0]['text'])
            print("\n✅ Successfully parsed 'text' field as JSON!")
            print(f"JSON keys: {list(data.keys())}")
            
            # Format products as markdown
            if 'products' in data:
                print("\n" + "-"*60)
                print("FORMATTED PRODUCTS")
                print("-"*60)
                markdown = "# Allbirds Products\n\n"
                for product in data['products']:
                    markdown += format_product_to_markdown(product) + "\n"
                
                # Add pagination info
                pagination = data.get('pagination', {})
                if pagination.get('hasNextPage', False):
                    markdown += f"\n**Pagination**: Showing page {pagination.get('currentPage', 1)} of {pagination.get('maxPages', 1)}. Would you like to see more results?\n"
                
                # Add available filters
                filters = data.get('available_filters', [])
                filter_labels = [f['label'] for f in filters]
                markdown += f"\n**Available Filters**: {', '.join(filter_labels)}\n"
                
                print(markdown)
                
                # Save to file
                with open('products.md', 'w') as f:
                    f.write(markdown)
                print("✅ Saved formatted output to 'products.md'")
            
            # Check isError flag
            is_error = result.get('result', {}).get('isError', False)
            print(f"\nisError flag: {is_error}")
            
            # Show full result structure
            print(f"\nFull result keys: {list(result.keys())}")
            if 'result' in result:
                print(f"result keys: {list(result['result'].keys())}")
                
        except json.JSONDecodeError as e:
            print(f"\n❌ Failed to parse 'text' field as JSON: {str(e)}")
            logger.error(f"JSON parsing error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_content_structure()