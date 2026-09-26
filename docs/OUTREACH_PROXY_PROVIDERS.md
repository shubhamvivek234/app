# Outreach proxy providers

Outreach sender connections use one pre-purchased **dedicated, static ISP** IP
per connected sender. Proxies do not make session-based LinkedIn automation
authorized or prevent account restrictions. Review LinkedIn's terms and the
provider's acceptable-use policy before any live or public use.

## One-IP IPRoyal pilot

1. Purchase one **ISP (Static Residential)** IP in the intended sender country.
   Do not buy rotating residential, datacenter, or SOCKS-only credentials.
2. In the server's `backend/.env`, configure:

   ```dotenv
   OUTREACH_PROXY_PROVIDER=iproyal
   IPROYAL_PROXY_URL=http://USERNAME:URL_ENCODED_PASSWORD@PUBLIC_STATIC_IP:HTTP_PORT
   IPROYAL_PROXY_COUNTRY=IN
   ```

   Use the HTTP port from IPRoyal's **Formatted Proxy List**, not its SOCKS5
   port. Percent-encode special characters in the username and password.
   Never put these values in frontend environment variables, Git, or chat.
3. Recreate the API container so it receives the new environment. The
   connection modal's two-letter proxy country must match
   `IPROYAL_PROXY_COUNTRY` and the country actually purchased.

The app does **not** purchase, renew, or cancel IPRoyal orders. The configured
URL supplies exactly one IP, and MongoDB leases it to at most one sender. A
second sender fails closed. Reconnect that same sender from the Accounts page
to renew its session without needing a second IP. If the proxy expires, is
replaced, or changes credentials, update the server secret and reconnect; if
the IP itself changes, disconnect the old sender or reconnect it so a new lease
can be allocated. Check IPRoyal's auto-renew setting yourself.

## Webshare at scale

`OUTREACH_PROXY_PROVIDER=webshare` is the default. Set `WEBSHARE_API_KEY` and
maintain an active Dedicated Static Residential (`dedicated` + `isp`) plan in
Webshare. The app selects available IPs from that plan and leases them 1:1;
the app does not order or cancel provider subscriptions.

Switching the environment back to Webshare changes **new** connections only.
Existing IPRoyal senders retain their stored proxy configuration. Reconnect
each sender to migrate it after buying enough Webshare IPs, and verify the
result before allowing campaigns to run. Disconnecting a sender only clears
the app's lease; cancel or resize provider subscriptions with the provider.

Never set `OUTREACH_MOCK_AUTH=true` in a public or production environment.
Mock proxy mode is only for isolated tests and does not verify LinkedIn.
