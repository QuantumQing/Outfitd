# Premium Upgrades: Advanced Product Discovery & Scraping

To take the AI Stylist application to the "Trunk Club / Stitch Fix" level with precise, real-time inventory and metadata, we will need to upgrade our discovery architecture. Relying on basic search engines (like Perplexity or generalized Serper.dev algorithms) cannot guarantee size availability or reliably extract merchant-specific return policies without visiting the actual product pages.

If you are willing to spend $1-$2 per trunk generation, here is the exact premium architecture we should invoke when you are ready:

## 1. Finding & Linking Actual Product Information
**Current Method:** We use a generalized LLM (Perplexity/OpenRouter) to "search" or assemble products, or naive Google Shopping searches, which often yield generic links or dead URLs.
**Premium Solution:** We need an actual e-commerce scraping engine or an affiliate product API to query exact SKUs in real time.

**Tools & APIs to explore:**
- **Rainforest API / Zinc API:** If we focus heavily on Amazon or specific major retailers, these provide perfect real-time JSON data.
- **SerpApi (Google Shopping API):** A more robust integration with SerpApi's Google Shopping engine can provide direct purchase links, prices, and merchant names.
- **Apify (Store Specific Scrapers):** The most expensive but most accurate method. Apify offers ready-made "Actors" (scrapers) for H&M, Zara, Macy\'s, Nordstrom, etc. We can programmatically trigger a scraper to find items matching the stylist brief. 
- **Affiliate Networks (CJ Affiliate, Rakuten):** If approved, their APIs provide direct access to retailer catalogs (including inventory) for free. Because approval takes time, Scraping APIs are our immediate fallback.

*Recommendation:* Use **SerpApi for Google Shopping** as the first discovery layer to get actual URLs, then use an LLM-powered scraping tool like **Firecrawl** or **Zyte API** to extract granular page data.

## 1a. Real-time Size In-Stock Verification
Verifying that a specific size (e.g., Men's Medium) is currently in stock *before* recommending it is the hardest problem in fashion aggregation. Generic search engines do not consistently index size-level inventory.

**How we will do it:**
1. Generate the initial candidate products using the discovery API above.
2. For each candidate URL, we will use a headless browser scraper designed for AI (like **Firecrawl** or **Browserbase**) to fetch the product page HTML.
3. We will pass the HTML (or extracted text) and the User's exact size to a fast, cheap LLM model (like Claude 3 Haiku or GPT-4o-mini).
4. The prompt will be: *"Does this page show that Size '{user_size}' is currently in stock for this color? Return True or False."*
5. Items that return False are immediately pruned from the candidate list before the 'Outfit Assembler' phase limits the options.

*Cost:* Scraping and executing an LLM check on ~30 candidate products per trunk generation will cost about $0.30 - $0.60 total.

## 1b. Merchant Return Policy Hover Icon
To extract the return policy for each merchant reliably without breaking when their site updates:

**How we will do it:**
1. When scraping the product page (during the Size Verification step above), we will also instruct the LLM to extract the return policy timeline.
2. Prompt: *"Look at the shipping & returns text on this page. What is the return policy? Summarize it in one concise sentence (e.g., 'Free returns within 30 days')."*
3. We will store this summary in the `return_policy_days` or a new `return_policy_summary` column in the database for each `TrunkItem`.
4. **UI Implementation:** In `trunk.html`, we will add a small 'ℹ️' or '📦' icon next to the retailer's name. We will add a CSS tooltip or a JS popover that displays the exact `return_policy_summary` string when hovered over by the user.

## Summary of the Premium Architecture Flow
1. **Query Generation:** Generate specific search queries based on profile & stylist brief.
2. **Catalog Discovery:** Hit SerpApi Google Shopping to get ~30 real candidate URLs.
3. **Data Enrichment (The Premium Step):** Use Firecrawl to grab the text of all 30 URLs. Fire off 30 async LLM requests (using GPT-4o-mini) to extract "Is size X in stock?" and "What is the return policy summary?".
4. **Pruning:** Drop out-of-stock items.
5. **Assembly:** Send the remaining, verified-in-stock items with their real URLs and prices to the Outfit Assembler LLM.
6. **Delivery:** The web app displays the final outfits with precise purchase links, return policy tooltips, and guarantees of user size availability.

*Expected Cost:* $0.50 - $1.20 per trunk.
*When you are ready, prompt me with:* "Let's implement the Premium Upgrades from the markdown file."
