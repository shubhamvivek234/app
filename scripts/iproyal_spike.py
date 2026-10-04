#!/usr/bin/env python3
"""
IPRoyal Reseller API — Phase 0 Provider Spike Script.

This script tests and records the exact runtime behavior of the IPRoyal Reseller API:
1. Balance verification (GET /v1/reseller/balance)
2. Dynamic product & location inspection (GET /v1/reseller/products)
3. Price verification per country (GET /v1/reseller/orders/calculate-pricing)
4. Order placement (POST /v1/reseller/orders)
5. Asynchronous provisioning measurement (polling GET /v1/reseller/orders/{id})
6. Live proxy connectivity & geo-IP verification
7. Order extension verification (POST /v1/reseller/orders/{id}/extend)

Usage:
    # Dry run (catalog, pricing, balance check - zero cost):
    .venv/bin/python scripts/iproyal_spike.py --token <TOKEN>

    # Live order execution ($4.00 charge on IPRoyal wallet):
    .venv/bin/python scripts/iproyal_spike.py --token <TOKEN> --execute --country "United States"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "https://apid.iproyal.com/v1/reseller"


class IPRoyalSpikeClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "X-Access-Token": self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def get_balance(self) -> float:
        resp = self.client.get("/balance")
        resp.raise_for_status()
        try:
            return float(resp.text.strip())
        except ValueError:
            return float(resp.json().get("balance", 0.0))

    def get_products(self) -> Dict[str, Any]:
        resp = self.client.get("/products")
        resp.raise_for_status()
        return resp.json()

    def calculate_pricing(
        self, product_id: int, plan_id: int, location_id: int, quantity: int = 1
    ) -> Dict[str, Any]:
        params = {
            "product_id": product_id,
            "product_plan_id": plan_id,
            "product_location_id": location_id,
            "quantity": quantity,
        }
        resp = self.client.get("/orders/calculate-pricing", params=params)
        resp.raise_for_status()
        return resp.json()

    def create_order(
        self, product_id: int, plan_id: int, location_id: int, quantity: int = 1
    ) -> Dict[str, Any]:
        payload = {
            "product_id": product_id,
            "product_plan_id": plan_id,
            "product_location_id": location_id,
            "quantity": quantity,
            "auto_extend": False,
        }
        resp = self.client.post("/orders", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_order(self, order_id: int) -> Dict[str, Any]:
        resp = self.client.get(f"/orders/{order_id}")
        resp.raise_for_status()
        return resp.json()

    def extend_order(self, order_id: int, plan_id: int) -> Dict[str, Any]:
        payload = {
            "product_plan_id": plan_id,
        }
        resp = self.client.post(f"/orders/{order_id}/extend", json=payload)
        resp.raise_for_status()
        return resp.json()


def run_spike(token: str, execute: bool, target_country: str, extend_test: bool):
    print("=" * 75)
    print("  IPRoyal Reseller API — Phase 0 Spike & Runtime Verification")
    print("=" * 75)

    client = IPRoyalSpikeClient(token)

    # 1. Balance Check
    print("\n[Step 1] Checking Wallet Balance (GET /v1/reseller/balance)...")
    try:
        balance = client.get_balance()
        print(f"  Current Wallet Balance: ${balance:.2f} USD")
    except Exception as e:
        print(f"  FAILED to fetch balance: {e}")
        return

    # 2. Product Catalog Inspection
    print("\n[Step 2] Fetching Products Catalog (GET /v1/reseller/products)...")
    products_data = client.get_products()
    products = products_data.get("data", [])

    isp_product = None
    for p in products:
        if p.get("id") == 9 or "ISP" in p.get("name", ""):
            isp_product = p
            break

    if not isp_product:
        print("  ERROR: ISP Dedicated / Static Residential product not found in catalog!")
        return

    product_id = isp_product["id"]
    product_name = isp_product["name"]
    print(f"  Found Product ID: {product_id} ({product_name})")

    # Find 30-Day Plan
    plans = isp_product.get("plans", [])
    plan_30d = None
    for pl in plans:
        if "30" in pl.get("name", ""):
            plan_30d = pl
            break
    if not plan_30d and plans:
        plan_30d = plans[0]

    plan_id = plan_30d["id"]
    plan_name = plan_30d["name"]
    plan_price = plan_30d.get("price")
    min_qty = plan_30d.get("min_quantity", 1)
    max_qty = plan_30d.get("max_quantity", 1000)

    print(f"  Selected Plan: ID {plan_id} ('{plan_name}')")
    print(f"    - Base Price: ${plan_price}")
    print(f"    - min_quantity: {min_qty}")
    print(f"    - max_quantity: {max_qty}")

    # Locations
    locations = isp_product.get("locations", [])
    in_stock_locs = [loc for loc in locations if not loc.get("out_of_stock")]
    out_of_stock_locs = [loc for loc in locations if loc.get("out_of_stock")]

    print(f"  Locations summary: Total={len(locations)}, In-Stock={len(in_stock_locs)}, Out-of-Stock={len(out_of_stock_locs)}")

    # Match target country
    selected_loc = None
    for loc in locations:
        if target_country.lower() in loc.get("name", "").lower():
            selected_loc = loc
            break

    if not selected_loc:
        print(f"  Target country '{target_country}' not found. Defaulting to first in-stock location.")
        selected_loc = in_stock_locs[0] if in_stock_locs else locations[0]

    loc_id = selected_loc["id"]
    loc_name = selected_loc["name"]
    is_oos = selected_loc.get("out_of_stock", False)

    print(f"  Target Location: ID {loc_id} ({loc_name}) [Out-of-stock: {is_oos}]")
    if is_oos:
        print("  WARNING: Selected location is currently marked OUT OF STOCK!")

    # 3. Calculate Pricing
    print(f"\n[Step 3] Verifying Exact Price (GET /v1/reseller/orders/calculate-pricing)...")
    try:
        pricing = client.calculate_pricing(product_id, plan_id, loc_id, quantity=1)
        calc_price = pricing.get("price")
        print(f"  Calculate-Pricing Response:")
        print(f"    - Final Price: ${calc_price} USD")
        print(f"    - Price per item: ${pricing.get('price_per_item')} USD")
        print(f"    - Pre-discount price: ${pricing.get('pre_discount_price')} USD")
    except Exception as e:
        print(f"  Calculate-pricing call failed: {e}")
        calc_price = plan_price

    print("\n" + "-" * 75)
    print(f"  SUMMARY BEFORE ORDER:")
    print(f"  - Product: {product_id} ({product_name})")
    print(f"  - Plan:    {plan_id} ({plan_name})")
    print(f"  - Country: {loc_id} ({loc_name})")
    print(f"  - Cost:    ${calc_price} USD (Balance: ${balance:.2f})")
    print("-" * 75)

    if not execute:
        print("\n[DRY RUN COMPLETE]")
        print("  To place a real 30-day ISP order ($4.00 charge):")
        print(f"  1. Ensure your IPRoyal wallet balance has at least $4.00 (currently ${balance:.2f}).")
        print(f"  2. Re-run this script with the --execute flag:")
        print(f"     .venv/bin/python scripts/iproyal_spike.py --token <TOKEN> --execute --country \"{loc_name}\"")
        return

    if balance < calc_price:
        print(f"\n[ERROR: INSUFFICIENT BALANCE]")
        print(f"  Cannot place order. Required: ${calc_price:.2f}, Available in wallet: ${balance:.2f}.")
        print("  Please deposit funds at https://dashboard.iproyal.com and re-run.")
        return

    # 4. Place Live Order
    print(f"\n[Step 4] Placing Live Order (POST /v1/reseller/orders)...")
    t0 = time.time()
    try:
        order_resp = client.create_order(product_id, plan_id, loc_id, quantity=1)
    except httpx.HTTPStatusError as e:
        print(f"  Order creation failed (HTTP {e.response.status_code}):")
        print(f"  {e.response.text}")
        return
    except Exception as e:
        print(f"  Order creation request error: {e}")
        return

    order_data = order_resp.get("data", order_resp)
    order_id = order_data.get("id")
    initial_status = order_data.get("status")
    initial_proxies = order_data.get("proxies", [])

    print(f"  Order successfully placed!")
    print(f"    - Order ID: {order_id}")
    print(f"    - Initial Status: {initial_status}")
    print(f"    - Initial Proxies count: {len(initial_proxies)}")

    # 5. Polling Asynchronous Provisioning
    print(f"\n[Step 5] Polling Asynchronous Provisioning (GET /v1/reseller/orders/{order_id})...")
    poll_count = 0
    max_polls = 40  # 40 * 3s = 120s max
    confirmed_order = None

    while poll_count < max_polls:
        poll_count += 1
        elapsed = time.time() - t0
        try:
            curr_resp = client.get_order(order_id)
            curr_order = curr_resp.get("data", curr_resp)
            curr_status = curr_order.get("status")
            proxies = curr_order.get("proxies", [])

            print(f"  Poll #{poll_count} ({elapsed:.1f}s): status='{curr_status}', proxies={len(proxies)}")

            if curr_status == "confirmed" and len(proxies) > 0:
                confirmed_order = curr_order
                break
            elif curr_status in ["failed", "refunded"]:
                print(f"  Order entered terminal error status: '{curr_status}'")
                break
        except Exception as e:
            print(f"  Warning: poll request failed: {e}")

        time.sleep(3.0)

    total_provision_time = time.time() - t0

    if not confirmed_order:
        print(f"\n  TIMEOUT or FAILURE: Order did not confirm within {total_provision_time:.1f} seconds.")
        return

    print("\n" + "=" * 75)
    print(f"  PROVISIONING SUCCESSFUL in {total_provision_time:.2f} seconds!")
    print("=" * 75)

    expire_date_raw = confirmed_order.get("expire_date")
    print(f"  - Raw expire_date from API: '{expire_date_raw}'")

    proxies = confirmed_order.get("proxies", [])
    first_proxy = proxies[0] if proxies else {}

    proxy_ip = first_proxy.get("ip")
    proxy_port = first_proxy.get("port") or first_proxy.get("http_port") or 12323
    proxy_user = first_proxy.get("username")
    proxy_pass = first_proxy.get("password")

    print(f"  - Allocated IP:       {proxy_ip}")
    print(f"  - HTTP Port:          {proxy_port}")
    print(f"  - Username:           {proxy_user}")
    print(f"  - Password:           [STORED - length: {len(str(proxy_pass))}]")

    # 6. Live Connectivity & Geolocation Verification
    print(f"\n[Step 6] Testing Live Proxy Connectivity through {proxy_ip}:{proxy_port}...")
    proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_ip}:{proxy_port}"
    try:
        with httpx.Client(proxies=proxy_url, timeout=15.0) as test_client:
            geo_resp = test_client.get("https://ipinfo.io/json")
            if geo_resp.status_code == 200:
                geo_data = geo_resp.json()
                exit_ip = geo_data.get("ip")
                exit_country = geo_data.get("country")
                exit_org = geo_data.get("org")
                print(f"  Proxy Probe Succeeded:")
                print(f"    - Exit IP:      {exit_ip} (Matches allocated: {exit_ip == proxy_ip})")
                print(f"    - Geolocation:  {exit_country} ({geo_data.get('city')}, {geo_data.get('region')})")
                print(f"    - ASN / Org:    {exit_org}")
            else:
                print(f"  Geo-probe returned HTTP {geo_resp.status_code}")
    except Exception as e:
        print(f"  Proxy probe failed: {e}")

    # 7. Test Order Extension (Optional)
    if extend_test:
        print(f"\n[Step 7] Testing Order Extension (POST /v1/reseller/orders/{order_id}/extend)...")
        t_ext_start = time.time()
        try:
            ext_resp = client.extend_order(order_id, plan_id)
            print("  Order extend response:")
            print(json.dumps(ext_resp, indent=2))
            
            # Fetch updated order to inspect new expiry date
            updated_order = client.get_order(order_id).get("data", {})
            new_expire_date = updated_order.get("expire_date")
            print(f"  Initial expire_date:    '{expire_date_raw}'")
            print(f"  Post-extend expire_date: '{new_expire_date}'")
        except Exception as e:
            print(f"  Extend test failed: {e}")

    # Save Results
    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "product_id": product_id,
        "product_name": product_name,
        "plan_id": plan_id,
        "plan_name": plan_name,
        "location_id": loc_id,
        "location_name": loc_name,
        "price_usd": calc_price,
        "order_id": order_id,
        "provision_duration_seconds": round(total_provision_time, 2),
        "raw_expire_date": expire_date_raw,
        "allocated_ip": proxy_ip,
        "proxy_port": proxy_port,
    }
    results_path = "scripts/iproyal_spike_output.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[Finished] Summary saved to {results_path}")


def main():
    parser = argparse.ArgumentParser(description="IPRoyal Reseller API Provider Spike")
    parser.add_argument(
        "--token",
        default=os.getenv("IPROYAL_API_TOKEN", "76ffeb16f037d711f418e35c524a0a88eb85b23729e25b28420b5dc160ef"),
        help="IPRoyal Reseller API Token (X-Access-Token)",
    )
    parser.add_argument(
        "--country",
        default="United States",
        help="Target country name (default: 'United States')",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Place a real $4.00 order on the live API (requires wallet balance >= $4)",
    )
    parser.add_argument(
        "--extend-test",
        action="store_true",
        help="Test the /orders/{id}/extend endpoint on the newly placed order (charges additional plan price)",
    )

    args = parser.parse_args()
    run_spike(args.token, args.execute, args.country, args.extend_test)


if __name__ == "__main__":
    main()
