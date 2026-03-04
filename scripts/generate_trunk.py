"""CLI trigger for trunk generation — use for manual/testing runs."""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db
from src.trunk.service import generate_trunk


async def main():
    print("Initializing database...")
    init_db()

    print("Generating trunk...")
    trunk = await generate_trunk()
    print(f"\nTrunk #{trunk.id} generated!")
    print(f"Season: {trunk.season}")
    print(f"Items: {len(trunk.items)}")
    print(f"Brief: {trunk.stylist_brief[:200]}...")

    for item in trunk.items:
        wc = " [WILDCARD]" if item.is_wildcard else ""
        print(f"  - [{item.category}] {item.brand} {item.product_name} ${item.price:.2f}{wc}")
        print(f"    {item.purchase_url}")


if __name__ == "__main__":
    asyncio.run(main())
