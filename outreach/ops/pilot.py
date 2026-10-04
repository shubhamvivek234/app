"""Private operator CLI for manually fulfilled, paid outreach pilot seats.

Run on the trusted backend host with DB_NAME, MONGODB_URI and ENCRYPTION_KEY set.
The customer API never calls these commands. Never put proxy credentials in
CLI arguments; import reads the IPROYAL_PROXY_URL environment variable.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import os
import json

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
    try:
        await _run_db(args, db)
    finally:
        await close_client()


async def _run_db(args, db) -> None:
    if args.command in {'inspect-studio-review', 'resolve-studio-review'}:
        from outreach.core.voice_studio_review import VoiceStudioReview
        service = VoiceStudioReview(db)
        result = (await service.inspect(args.workspace, args.job) if args.command.startswith('inspect-')
            else await service.resolve(args.workspace, args.job, args.decision, args.operator, args.evidence,
                expected_digest=args.review_digest, workers_drained=
                    args.workers_drained == 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES'))
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {'inspect-oauth-hold', 'stop-oauth-hold'}:
        from outreach.core.oauth_hold_review import OAuthHoldReview
        service = OAuthHoldReview(db)
        result = (await service.inspect(args.workspace, args.job) if args.command.startswith('inspect-')
            else await service.stop(args.workspace, args.job, args.operator, args.evidence,
                expected_digest=args.review_digest,
                workers_drained=args.workers_drained == 'I_PAUSED_AND_DRAINED_ALL_MAILBOX_AND_SENDER_WRITERS'))
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-provider-custody", "migrate-provider-custody"}:
        from outreach.core.provider_credential_migration import ProviderCredentialMigration
        service = ProviderCredentialMigration(db)
        if args.command.startswith("inspect-"):
            result = await service.inspect(args.workspace, args.kind, args.sender)
        else:
            result = await service.migrate(args.workspace, args.kind, args.sender, args.operator, args.review_digest,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS")
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-proxy-custody", "migrate-proxy-custody"}:
        from outreach.core.proxy_migration import ProxyMigration
        service = ProxyMigration(db)
        if args.command.startswith("inspect-"):
            result = await service.inspect(args.workspace, args.proxy)
        else:
            result = await service.migrate(args.workspace, args.proxy, args.operator, args.review_digest,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS")
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-connection-storage", "stop-connection-storage"}:
        from outreach.core.connection_storage_repair import ConnectionStorageRepair
        service = ConnectionStorageRepair(db)
        if args.command.startswith("inspect-"):
            result = await service.inspect(args.workspace, args.job)
        else:
            result = await service.resolve(args.workspace, args.job, args.operator, args.evidence, args.review_digest,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS")
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-credential-custody", "migrate-credential-custody"}:
        from outreach.core.credential_migration import CredentialMigration
        service = CredentialMigration(db)
        if args.command == "inspect-credential-custody":
            result = await service.inspect(args.workspace, args.sender)
        else:
            result = await service.migrate(args.workspace, args.sender, args.operator, args.review_digest,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS")
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-erasure", "finish-erasure", "inspect-erasure-hold", "release-erasure-hold"}:
        from outreach.core.erasure import OutreachErasure
        service = OutreachErasure(db)
        if args.command == "inspect-erasure":
            result = await service.inspect(args.workspace)
        elif args.command == "finish-erasure":
            result = await service.finish(args.workspace, args.operator, args.evidence,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS", expected_digest=args.review_digest)
        elif args.command == "inspect-erasure-hold":
            result = await service.inspect_hold(args.workspace, args.hold)
        else:
            result = await service.release_hold(args.workspace, args.hold, args.operator, args.evidence, expected_digest=args.review_digest)
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"inspect-manual-review", "resolve-manual-review", "inspect-connection-repair", "resolve-connection-repair"}:
        from outreach.core.manual_resolution import ManualResolution
        from outreach.core.connection_repair import ConnectionRepair
        service = ManualResolution(db) if "manual" in args.command else ConnectionRepair(db)
        if args.command.startswith("inspect-"):
            result = await service.inspect(args.workspace, args.job)
        else:
            decision = args.decision
            if "manual" in args.command:
                pairs = [item.split("=", 1) for item in decision]
                if any(len(pair) != 2 for pair in pairs) or len({pair[0] for pair in pairs}) != len(pairs):
                    raise ValueError("Use unique stage=decision entries")
                decision = dict(pairs)
            result = await service.resolve(args.workspace, args.job, decision, args.operator, args.evidence,
                workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_SENDER_WORKERS", expected_digest=args.review_digest)
        print(json.dumps(result, default=str, sort_keys=True))
    elif args.command in {"grant-execution", "stop-execution", "review-request", "list-request-review"}:
        from outreach.core.execution_permission import ExecutionPermission
        from outreach.core.inbox_freshness import credential_generation
        permission = ExecutionPermission(db)
        if args.command == "grant-execution":
            if args.connection_job:
                job = await db.outreach_connection_jobs.find_one({
                    "id": args.connection_job, "workspace_id": args.workspace, "sender_id": args.sender,
                    "status": {"$in": ["queued", "running"]}})
                if not job or args.sources != ["verify"]:
                    raise ValueError("Pending connection permission is restricted to that job's verification")
                generation = "pending:" + args.connection_job
            else:
                account = await db.outreach_accounts.find_one({"workspace_id": args.workspace, "id": args.sender, "status": "active"})
                if not account:
                    raise ValueError("Active sender not found")
                generation = credential_generation(account)
                providers = set(args.sources) & {"email_send", "email_find"}
                if providers:
                    if len(args.sources) != 1:
                        raise ValueError("Provider permissions require exactly one source and generation")
                    from outreach.core.provider_boundary import provider_generation
                    source = args.sources[0]
                    resource = await (db.outreach_mailboxes.find_one({"workspace_id": args.workspace, "sender_account_id": args.sender,
                        "status": "active"}) if source == "email_send" else db.outreach_hunter_credentials.find_one({"workspace_id": args.workspace}))
                    if not resource:
                        raise ValueError("Provider resource is unavailable")
                    generation = provider_generation(account, resource, source)
            grant = await permission.grant(args.workspace, args.sender, generation, args.sources, args.operator,
                ttl_seconds=args.ttl, clear_latch=args.clear_latch)
            print(f"Permission expires={grant['expires_at'].isoformat()} revision={grant['revision']}; feature flags are unchanged")
        elif args.command == "stop-execution":
            await permission.revoke(args.workspace, args.sender, args.operator, args.reason)
            print("Sender execution permission is stopped and latched")
        elif args.command == "review-request":
            await permission.resolve_request(args.workspace, args.sender, args.request_id, args.operator,
                args.decision, args.evidence, workers_drained=args.workers_drained == "I_PAUSED_AND_DRAINED_SENDER_WORKERS")
            print("Human assertion recorded; permission remains stopped and campaigns are not resumed")
        else:
            records = await db.outreach_physical_requests.find({"workspace_id": args.workspace, "sender_id": args.sender,
                "status": {"$in": ["in_flight", "unknown_outcome"]}}).limit(100).to_list(length=100)
            for record in records:
                print(f"{record['_id']} source={record['source']} action={record['action']} status={record['status']} created={record['created_at'].isoformat()}")
    elif args.command == "list-requests":
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Private paid-outreach pilot operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-requests")
    for name in ('inspect-studio-review', 'resolve-studio-review'):
        command = commands.add_parser(name)
        command.add_argument('--workspace', required=True)
        command.add_argument('--job', required=True)
        if name.startswith('resolve-'):
            command.add_argument('--decision', choices=('stop_local', 'use_receipt'), required=True)
            for argument in ('operator', 'review-digest', 'evidence', 'workers-drained'):
                command.add_argument('--' + argument, required=True)
    for name in ('inspect-oauth-hold', 'stop-oauth-hold'):
        command = commands.add_parser(name)
        command.add_argument('--workspace', required=True)
        command.add_argument('--job', required=True)
        if name.startswith('stop-'):
            for argument in ('operator', 'review-digest', 'evidence', 'workers-drained'):
                command.add_argument('--' + argument, required=True)
    for name in ("inspect-provider-custody", "migrate-provider-custody"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--kind", required=True, choices=("mailbox", "finder"))
        command.add_argument("--sender")
        if name.startswith("migrate-"):
            command.add_argument("--operator", required=True)
            command.add_argument("--review-digest", required=True)
            command.add_argument("--workers-drained", required=True)
    for name in ("inspect-proxy-custody", "migrate-proxy-custody", "inspect-connection-storage", "stop-connection-storage"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--proxy" if "proxy" in name else "--job", required=True)
        if not name.startswith("inspect-"):
            command.add_argument("--operator", required=True)
            command.add_argument("--review-digest", required=True)
            command.add_argument("--workers-drained", required=True)
            if name == "stop-connection-storage": command.add_argument("--evidence", required=True)
    for name in ("inspect-credential-custody", "migrate-credential-custody"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--sender", required=True)
        if name == "migrate-credential-custody":
            command.add_argument("--operator", required=True)
            command.add_argument("--review-digest", required=True)
            command.add_argument("--workers-drained", required=True)
    for name in ("inspect-erasure", "finish-erasure", "inspect-erasure-hold", "release-erasure-hold"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        if name.endswith("hold"):
            command.add_argument("--hold", required=True)
        if name in {"finish-erasure", "release-erasure-hold"}:
            command.add_argument("--operator", required=True)
            command.add_argument("--evidence", required=True)
            command.add_argument("--review-digest", required=True)
        if name == "finish-erasure":
            command.add_argument("--workers-drained", required=True)
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
    for name in ("inspect-manual-review", "resolve-manual-review", "inspect-connection-repair", "resolve-connection-repair"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--job", required=True)
        if name.startswith("resolve-"):
            command.add_argument("--operator", required=True)
            command.add_argument("--evidence", required=True)
            command.add_argument("--review-digest", required=True)
            command.add_argument("--workers-drained", required=True)
            if "manual" in name:
                command.add_argument("--decision", nargs="+", required=True, help="stage=confirmed_sent|not_sent_stop|use_receipt")
            else:
                command.add_argument("--decision", choices=["retain_installed", "stop_and_scrub"], required=True)
    from outreach.core.execution_permission import SOURCES
    for name in ("grant-execution", "stop-execution", "review-request", "list-request-review"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        command.add_argument("--sender", required=True)
        if name != "list-request-review":
            command.add_argument("--operator", required=True)
        if name == "grant-execution":
            command.add_argument("--sources", nargs="+", choices=sorted(SOURCES), required=True)
            command.add_argument("--ttl", type=int, default=60)
            command.add_argument("--connection-job")
            command.add_argument("--clear-latch", action="store_true")
        elif name == "stop-execution":
            command.add_argument("--reason", required=True)
        elif name == "review-request":
            command.add_argument("--request-id", required=True)
            command.add_argument("--decision", choices=["confirmed_sent", "not_sent_stop", "read_interrupted"], required=True)
            command.add_argument("--evidence", required=True)
            command.add_argument("--workers-drained", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
