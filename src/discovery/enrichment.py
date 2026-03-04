import logging
import asyncio
import httpx
from src.config import settings
from src.models import Product
from src.curation.llm_client import call_llm

logger = logging.getLogger(__name__)

async def _enrich_product_single(product: Product, size: str) -> bool:
    """Takes a Product and target size, scrapes the page, and updates return policy summary.
    Returns True if the item size is in stock, False otherwise."""
    url = "https://api.firecrawl.dev/v1/scrape"
    headers = {
        "Authorization": f"Bearer {settings.firecrawl_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": product.purchase_url,
        "formats": ["markdown"],
        "onlyMainContent": True
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Firecrawl failed for {product.purchase_url}: {resp.text}")
                return True # assume in-stock if we can't scrape
            data = resp.json()
            markdown = data.get("data", {}).get("markdown", "")
            
            if not markdown:
                return True
                
            # Now call LLM to extract info
            sys_prompt = "You are a shopping assistant that extracts information from e-commerce page text."
            user_prompt = f"""
Here is the markdown from a product page for "{product.product_name}":

{markdown[:10000]}

Analyze this text to answer two questions:
1. Is the size "{size}" currently in stock for this product? (If size is empty or not mentioned, assume yes).
2. What is the return policy? Summarize it in one concise sentence (e.g., 'Free returns within 30 days.'). If not found, say ''.

Return exactly this JSON:
{{
   "in_stock": true,
   "return_policy_summary": "..."
}}
"""
            llm_resp = await call_llm(sys_prompt, user_prompt, temperature=0.0)
            if isinstance(llm_resp, dict):
                product.return_policy_summary = llm_resp.get("return_policy_summary", "")
                return bool(llm_resp.get("in_stock", True))
            return True
    except Exception as e:
        logger.warning(f"Error enriching {product.purchase_url}: {e}")
        return True

async def enrich_products(products: list[Product], sizes) -> list[Product]:
    if not settings.firecrawl_api_key:
        logger.info("Skipping Firecrawl enrichment (no API key).")
        return products
        
    logger.info(f"Enriching {len(products)} products with Firecrawl to verify size/returns...")
    
    sem = asyncio.Semaphore(5)
    
    async def process_p(p: Product):
        async with sem:
            # Determine correct size mapping
            if p.category in ["top", "outerwear"]:
                sz = sizes.shirt
            elif p.category == "bottom":
                sz = sizes.pants
            else:
                sz = ""
                
            if not sz:
                return p # Can't check stock if size isn't specified
                
            in_stock = await _enrich_product_single(p, sz)
            return p if in_stock else None
            
    tasks = [process_p(p) for p in products]
    results = await asyncio.gather(*tasks)
    
    enriched = [p for p in results if p is not None]
    logger.info(f"Enrichment completed: {len(enriched)}/{len(products)} products in stock.")
    return enriched
