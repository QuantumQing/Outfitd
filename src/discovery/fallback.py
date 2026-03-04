
from src.models import Product

FALLBACK_PRODUCTS = [
    Product(
        product_name="Essential Oxford Shirt",
        brand="Uniqlo",
        category="top",
        color="Light Blue",
        size="M",
        price=39.90,
        retailer="Uniqlo",
        purchase_url="https://www.uniqlo.com",
        image_url="https://image.uniqlo.com/UQ/ST3/us/imagesgoods/458039/item/usgoods_60_458039.jpg",
        return_policy_days=30
    ),
    Product(
        product_name="Slim Fit Chino Pants",
        brand="J.Crew",
        category="bottom",
        color="Navy",
        size="32x32",
        price=79.50,
        retailer="J.Crew",
        purchase_url="https://www.jcrew.com",
        image_url="https://www.jcrew.com/s7-img-facade/H4832_NA6434",
        return_policy_days=30
    ),
    Product(
        product_name="Leather Chelsea Boots",
        brand="Thursday Boot Co",
        category="shoes",
        color="Brown",
        size="10.5",
        price=199.00,
        retailer="Thursday Boots",
        purchase_url="https://thursdayboots.com",
        image_url="https://cdn.shopify.com/s/files/1/0023/9478/3809/products/Captain-Brown-3.jpg",
        return_policy_days=30
    ),
    Product(
        product_name="Classic White T-Shirt",
        brand="Everlane",
        category="top",
        color="White",
        size="M",
        price=30.00,
        retailer="Everlane",
        purchase_url="https://www.everlane.com",
        image_url="https://media.everlane.com/image/upload/c_scale,dpr_1.0,f_auto,q_auto,w_auto/v1/i/1f6a1d82_1d3e_4b3e_8e2a_1e2e1e2e1e2e",
        return_policy_days=365
    ),
    Product(
        product_name="Denim Jacket",
        brand="Levi's",
        category="outerwear",
        color="Medium Wash",
        size="M",
        price=89.50,
        retailer="Levi's",
        purchase_url="https://www.levi.com",
        image_url="https://lsco.scene7.com/is/image/lsco/723340134-front-pdp",
        return_policy_days=30
    )
]

def get_fallback_products() -> list[Product]:
    """Return a robust list of fallback products to ensure generation never fails."""
    return FALLBACK_PRODUCTS
