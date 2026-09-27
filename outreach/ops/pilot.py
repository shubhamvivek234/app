"""Private operator CLI for manually fulfilled, paid outreach pilot seats.

Run on the trusted backend host with DB_NAME, MONGODB_URI and ENCRYPTION_KEY set.
The customer API never calls these commands. Never put proxy credentials in
CLI arguments; import reads the IPROYAL_PROXY_URL environment variable.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import os

from db.mongo import get_client, close_client
from outreach.core.managed_proxy import import_iproyal_proxy
from outreach.core.paid_access import record_verified_payment, _utc


def _date(value: str) -> datetime:
    result = _utc(value)
    if result is None:
        raise argparse.ArgumentTypeError("Use an ISO-8601 date/time")
    return result


async def _run(args) -> None:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]
    if args.command == "list-requests":
        requests = await db.outreach_access_requests.find({"status": "pending_quote"}).to_list(length=100)
        for request in requests:
            print(f"{request['workspace_id']} country={request['country_code']} seats={request['seats']}")
    elif args.command == "import-iproyal":
        proxy_url = os.environ.get("IPROYAL_PROXY_URL", "")
        if not proxy_url:
            raise ValueError("Set IPROYAL_PROXY_URL in the operator environment; do not pass it on the command line")
        result = await import_iproyal_proxy(
            db, proxy_url, args.country, args.order_id, args.workspace, args.expires_at,
        )
        print(f"Imported {result['proxy_id']} country={result['country_code']} expires={result['expires_at'].isoformat()}")
    elif args.command == "record-payment":
        if args.verified_in_processor != "I_VERIFIED_THIS_INVOICE":
            raise ValueError("Independently verify the paid invoice before granting access")
        result = await record_verified_payment(
            db, args.workspace, args.invoice_id, args.operator,
            args.seats, args.paid_through,
        )
        print(f"Activated {result['workspace_id']} seats={result['seats']} paid_through={result['paid_through'].isoformat()}")
    elif args.command == "extend-ip":
        if args.verified_in_provider != "I_VERIFIED_THIS_ORDER":
            raise ValueError("Confirm the extension in IPRoyal before updating its local term")
        inventory = await db.outreach_proxy_inventory.find_one({
            "_id": args.proxy_id, "provider": "iproyal_static", "provider_order_id": args.order_id,
        })
        if not inventory or _utc(inventory.get("expires_at")) >= args.expires_at:
            raise ValueError("Order not found or the new expiry does not extend its term")
        await db.outreach_proxy_inventory.update_one(
            {"_id": args.proxy_id, "provider_order_id": args.order_id},
            {"$set": {"expires_at": args.expires_at, "extended_at": datetime.now(timezone.utc)}},
        )
        print(f"Extended {args.proxy_id} until {args.expires_at.isoformat()}")
    elif args.command == "list-expiring":
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) + timedelta(days=args.days)
        inventory = await db.outreach_proxy_inventory.find({
            "status": "available", "expires_at": {"$lte": cutoff},
        }).to_list(length=200)
        for proxy in inventory:
            print(f"{proxy['_id']} country={proxy['country_code']} order={proxy['provider_order_id']} expires={proxy['expires_at'].isoformat()} workspace={proxy.get('last_workspace_id') or '-'}")
    await close_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Private paid-outreach pilot operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-requests")
    imp = commands.add_parser("import-iproyal")
    imp.add_argument("--country", required=True)
    imp.add_argument("--workspace", required=True)
    imp.add_argument("--order-id", required=True)
    imp.add_argument("--expires-at", type=_date, required=True)
    pay = commands.add_parser("record-payment")
    pay.add_argument("--workspace", required=True)
    pay.add_argument("--invoice-id", required=True)
    pay.add_argument("--operator", required=True)
    pay.add_argument("--seats", type=int, required=True)
    pay.add_argument("--paid-through", type=_date, required=True)
    pay.add_argument("--verified-in-processor", required=True)
    ext = commands.add_parser("extend-ip")
    ext.add_argument("--proxy-id", required=True)
    ext.add_argument("--order-id", required=True)
    ext.add_argument("--expires-at", type=_date, required=True)
    ext.add_argument("--verified-in-provider", required=True)
    exp = commands.add_parser("list-expiring")
    exp.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
