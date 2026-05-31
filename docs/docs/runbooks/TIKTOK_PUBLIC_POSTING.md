# TikTok Public Posting Restriction

## Symptom
- TikTok video publish fails immediately after `POST /v2/post/publish/video/init/`
- Provider code: `unaudited_client_can_only_post_to_private_accounts`

## Meaning
- The current TikTok app/client is not approved for public-account posting.
- This is a TikTok app-review / audit dependency, not an OAuth, Celery, Redis, or upload pipeline failure.

## Expected Product Behavior
- Post should finalize as `failed`, not remain in `processing`.
- `platform_results.tiktok` and the matching `account_results.*` entry should include:
  - `error_code = unaudited_client_can_only_post_to_private_accounts`
  - `error_category = provider_restriction`
  - `action_required = complete_tiktok_audit_or_use_private_account`
  - `restriction_type = tiktok_public_posting_not_approved`

## Operator Response
1. Confirm the post failed with the provider restriction code in worker logs or MongoDB.
2. Tell the user public TikTok posting is blocked until TikTok app review/audit is approved.
3. If needed, suggest testing with a private TikTok account because TikTok may allow unaudited clients to post there.
4. Do not trigger reconnect guidance or token-refresh debugging for this case.

## Quick Check
```bash
docker compose --env-file backend/.env -f docker-compose.prod.yml logs --since=15m worker_video | rg "unaudited_client_can_only_post_to_private_accounts|publish/video/init"
```
