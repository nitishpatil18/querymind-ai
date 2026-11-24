"""Deterministic synthetic data for the demo e-commerce database.

Everything is generated from a fixed random seed and a fixed anchor date, so
the same rows are produced on every run. No real personal data is used: names
are synthetic and every email uses the reserved example.com domain.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

SEED = 20261114
ANCHOR_DATE = date(2026, 11, 14)  # "today" of the dataset; orders end here

N_CUSTOMERS = 520
ORDERS_TARGET = 1650
INACTIVE_CUSTOMER_RATIO = 0.10  # customers who never order

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Siddharth", "Rahul", "Manoj", "Suresh",
    "Anil", "Vikram", "Nikhil", "Pranav", "Harsha", "Naveen", "Deepak", "Ravi", "Sanjay", "Mohan",
    "Ananya", "Diya", "Priya", "Sneha", "Kavya", "Meera", "Isha", "Neha", "Pooja", "Lakshmi",
    "Divya", "Swathi", "Shruti", "Aishwarya", "Ritu", "Anjali", "Nandini", "Bhavana", "Tanvi", "Chaitra",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patil", "Reddy", "Nair", "Iyer", "Kulkarni", "Rao", "Shetty",
    "Gowda", "Hegde", "Bhat", "Menon", "Pillai", "Singh", "Kumar", "Joshi", "Desai", "Mehta",
    "Chopra", "Banerjee", "Chatterjee", "Das", "Naidu", "Yadav", "Jain", "Agarwal", "Pandey", "Kapoor",
]
# (state, [cities], weight)
LOCATIONS = [
    ("Karnataka", ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi"], 22),
    ("Maharashtra", ["Mumbai", "Pune", "Nagpur"], 14),
    ("Tamil Nadu", ["Chennai", "Coimbatore", "Madurai"], 10),
    ("Telangana", ["Hyderabad", "Warangal"], 9),
    ("Delhi", ["New Delhi"], 8),
    ("West Bengal", ["Kolkata", "Siliguri"], 6),
    ("Gujarat", ["Ahmedabad", "Surat", "Vadodara"], 7),
    ("Kerala", ["Kochi", "Thiruvananthapuram"], 6),
    ("Rajasthan", ["Jaipur", "Jodhpur"], 5),
    ("Uttar Pradesh", ["Lucknow", "Noida", "Kanpur"], 7),
    ("Punjab", ["Ludhiana", "Amritsar"], 3),
    ("Madhya Pradesh", ["Indore", "Bhopal"], 3),
]

# category -> (description, price range, product names)
CATEGORIES: list[tuple[str, str, tuple[int, int], list[str]]] = [
    ("Electronics", "Consumer electronics and gadgets.", (1500, 85000), [
        "Wireless Bluetooth Headphones", "Noise Cancelling Earbuds", "Portable Bluetooth Speaker", "Smart Watch Series 4",
        "4K Action Camera", "Mechanical Gaming Keyboard", "Wireless Gaming Mouse", "27-inch IPS Monitor",
        "Portable SSD 1TB", "Laptop Cooling Pad"]),
    ("Mobiles & Accessories", "Smartphones, chargers, cases and related accessories.", (299, 70000), [
        "Android Smartphone 128GB", "Android Smartphone 256GB", "Fast Charging Adapter 65W", "USB-C Braided Cable",
        "Tempered Glass Screen Guard", "Shockproof Phone Case", "Power Bank 20000mAh", "Wireless Charging Pad",
        "Phone Tripod Stand", "Bluetooth Neckband"]),
    ("Home & Kitchen", "Appliances and utensils for the home and kitchen.", (399, 25000), [
        "Non-stick Cookware Set", "Electric Kettle 1.5L", "Mixer Grinder 750W", "Air Fryer 4L",
        "Stainless Steel Water Bottle", "Vacuum Insulated Flask", "Induction Cooktop", "Pressure Cooker 5L",
        "Glass Storage Container Set", "Robotic Vacuum Cleaner"]),
    ("Books", "Printed books across genres.", (149, 1200), [
        "Data Structures Made Simple", "Introduction to Machine Learning", "Clean Code Handbook", "Indian History Illustrated",
        "Mystery at Midnight Novel", "Personal Finance Basics", "Cooking the South Indian Way", "Mindful Living Guide",
        "Children's Story Collection", "World Atlas Edition"]),
    ("Fashion - Men", "Clothing and accessories for men.", (299, 6000), [
        "Cotton Casual Shirt", "Slim Fit Denim Jeans", "Running Sports Shoes", "Leather Formal Belt",
        "Polo T-Shirt Pack of 3", "Hooded Sweatshirt", "Classic Leather Wallet", "Formal Trousers",
        "Canvas Sneakers", "Quilted Winter Jacket"]),
    ("Fashion - Women", "Clothing and accessories for women.", (299, 8000), [
        "Printed Cotton Kurta", "Silk Blend Saree", "High Waist Jeans", "Leather Handbag",
        "Designer Dupatta", "Casual Sling Bag", "Ethnic Palazzo Set", "Block Heel Sandals",
        "Woolen Cardigan", "Party Wear Gown"]),
    ("Sports & Fitness", "Equipment and apparel for sports and fitness.", (199, 18000), [
        "Yoga Mat 6mm", "Adjustable Dumbbell Set", "Cricket Bat Kashmir Willow", "Badminton Racquet Pair",
        "Resistance Band Set", "Football Size 5", "Skipping Rope", "Treadmill Foldable",
        "Fitness Tracker Band", "Gym Duffle Bag"]),
    ("Beauty & Personal Care", "Skincare, haircare and grooming products.", (99, 4500), [
        "Vitamin C Face Serum", "Sunscreen SPF 50", "Herbal Shampoo 500ml", "Beard Trimmer Kit",
        "Hair Dryer 1800W", "Aloe Vera Gel", "Matte Lipstick Set", "Electric Toothbrush",
        "Body Lotion 400ml", "Perfume Gift Set"]),
    ("Toys & Games", "Toys, puzzles and board games.", (149, 7000), [
        "Building Blocks 500 Pieces", "Remote Control Car", "Strategy Board Game", "Jigsaw Puzzle 1000 Pieces",
        "Plush Teddy Bear", "Art and Craft Kit", "Educational Science Kit", "Chess Set Wooden",
        "Kids Ride-on Scooter", "Card Game Party Pack"]),
    ("Grocery & Gourmet", "Packaged food, beverages and gourmet items.", (49, 2500), [
        "Organic Basmati Rice 5kg", "Cold Pressed Olive Oil 1L", "Assorted Dry Fruits 1kg", "Filter Coffee Powder 500g",
        "Green Tea 100 Bags", "Whole Wheat Flour 10kg", "Honey Raw 500g", "Masala Spice Box",
        "Dark Chocolate Pack", "Protein Muesli 1kg"]),
    ("Furniture", "Home and office furniture.", (1999, 60000), [
        "Ergonomic Office Chair", "Wooden Study Table", "Three Seater Sofa", "Queen Size Bed Frame",
        "Bookshelf Five Tier", "Shoe Rack Cabinet", "Recliner Armchair", "Dining Table Set",
        "TV Entertainment Unit", "Foldable Laptop Desk"]),
    ("Office Supplies", "Stationery and office essentials.", (49, 9000), [
        "A4 Copier Paper Ream", "Gel Pen Pack of 20", "Spiral Notebook Set", "Desk Organizer",
        "Laser Printer Monochrome", "Whiteboard 3x2 ft", "Stapler Heavy Duty", "Sticky Notes Bundle",
        "Document File Folder Set", "Label Maker"]),
]

ORDER_STATUSES = [("completed", 62), ("shipped", 8), ("processing", 7), ("pending", 8), ("cancelled", 15)]
PAYMENT_METHODS = [("upi", 34), ("credit_card", 22), ("debit_card", 16), ("net_banking", 9), ("cash_on_delivery", 11), ("wallet", 8)]


@dataclass
class SeedData:
    customers: list[tuple]
    categories: list[tuple]
    products: list[tuple]
    orders: list[tuple]
    order_items: list[tuple]
    payments: list[tuple]


def _weighted(rng: random.Random, pairs):
    values = [p[0] for p in pairs]
    weights = [p[-1] for p in pairs]
    return rng.choices(values, weights=weights, k=1)[0]


def generate(seed: int = SEED) -> SeedData:
    rng = random.Random(seed)

    # categories
    categories = [(i + 1, name, desc) for i, (name, desc, _, _) in enumerate(CATEGORIES)]

    # products
    products: list[tuple] = []
    pid = 1
    for cid, (_, _, (lo, hi), names) in enumerate(CATEGORIES, start=1):
        for name in names:
            raw = rng.uniform(lo, hi) if rng.random() < 0.25 else lo + (hi - lo) * rng.random() ** 2.2
            price = Decimal(str(round(max(raw, 49), 0))) - Decimal("0.01")
            products.append((pid, name, cid, price, rng.randint(0, 500)))
            pid += 1
    price_of = {p[0]: p[3] for p in products}

    # customers
    customers: list[tuple] = []
    reg_start, reg_end = date(2022, 1, 1), ANCHOR_DATE - timedelta(days=30)
    span = (reg_end - reg_start).days
    states = [(s, c, w) for s, c, w in LOCATIONS]
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        state, cities, _ = rng.choices(states, weights=[s[2] for s in states], k=1)[0]
        city = rng.choice(cities)
        # slightly more recent registrations than old ones
        reg = reg_start + timedelta(days=int(span * rng.random() ** 0.8))
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
        customers.append((cid, first, last, email, city, state, reg))
    reg_of = {c[0]: c[6] for c in customers}

    # who orders
    ids = [c[0] for c in customers]
    rng.shuffle(ids)
    n_inactive = int(len(ids) * INACTIVE_CUSTOMER_RATIO)
    active = sorted(ids[n_inactive:])
    cust_weights = [rng.lognormvariate(0, 0.85) for _ in active]

    window_start = ANCHOR_DATE - timedelta(days=730)
    orders: list[tuple] = []
    items: list[tuple] = []
    payments: list[tuple] = []
    oid = iid = payid = 1

    for _ in range(ORDERS_TARGET):
        cust = rng.choices(active, weights=cust_weights, k=1)[0]
        earliest = max(reg_of[cust], window_start)
        days = (ANCHOR_DATE - earliest).days
        order_date = earliest + timedelta(days=int(days * rng.random() ** 0.7))
        age = (ANCHOR_DATE - order_date).days
        status = _weighted(rng, ORDER_STATUSES)
        # recent orders are less likely to be finished; old orders are not pending/processing
        if age > 45 and status in ("pending", "processing"):
            status = rng.choice(["completed", "completed", "cancelled"])
        if age > 20 and status == "shipped":
            status = "completed"
        if age < 5 and status == "completed":
            status = rng.choice(["processing", "shipped", "pending"])

        n_lines = rng.choices([1, 2, 3, 4, 5], weights=[40, 30, 18, 8, 4], k=1)[0]
        chosen = rng.sample(range(1, len(products) + 1), n_lines)
        total = Decimal("0.00")
        for p in chosen:
            qty = rng.choices([1, 2, 3, 4], weights=[65, 22, 9, 4], k=1)[0]
            unit = price_of[p]
            if rng.random() < 0.12:  # occasional discount
                unit = (unit * Decimal("0.90")).quantize(Decimal("0.01"))
            items.append((iid, oid, p, qty, unit))
            iid += 1
            total += unit * qty
        total = total.quantize(Decimal("0.01"))
        orders.append((oid, cust, order_date, status, total))

        method = _weighted(rng, PAYMENT_METHODS)
        if status == "completed" or status == "shipped":
            if rng.random() < 0.06:  # failed attempt followed by success
                payments.append((payid, oid, method, "failed", order_date, total)); payid += 1
            pay_date = order_date + timedelta(days=rng.randint(0, 2))
            payments.append((payid, oid, method, "completed", min(pay_date, ANCHOR_DATE), total)); payid += 1
        elif status == "processing":
            if method == "cash_on_delivery":
                payments.append((payid, oid, method, "pending", None, total))
            else:
                payments.append((payid, oid, method, "completed", order_date, total))
            payid += 1
        elif status == "pending":
            payments.append((payid, oid, method, "pending", None, total)); payid += 1
        else:  # cancelled
            kind = rng.choices(["refunded", "failed", "pending"], weights=[50, 35, 15], k=1)[0]
            pdate = None if kind == "pending" else order_date + timedelta(days=rng.randint(0, 3))
            payments.append((payid, oid, method, kind, pdate and min(pdate, ANCHOR_DATE), total)); payid += 1
        oid += 1

    # order ids in chronological order, which reads naturally
    order_map = {o[0]: i for i, o in enumerate(sorted(orders, key=lambda o: (o[2], o[0])), start=1)}
    orders = sorted(((order_map[o[0]], *o[1:]) for o in orders), key=lambda o: o[0])
    items = sorted(((i[0], order_map[i[1]], *i[2:]) for i in items), key=lambda r: (r[1], r[0]))
    items = [(n, *row[1:]) for n, row in enumerate(items, start=1)]
    payments = sorted(((p[0], order_map[p[1]], *p[2:]) for p in payments), key=lambda r: (r[1], r[0]))
    payments = [(n, *row[1:]) for n, row in enumerate(payments, start=1)]

    return SeedData(customers, categories, products, orders, items, payments)
