# Clash Verge loopback egress tunnel

This path gives only the Hermes Bridge and durable worker outbound HTTP(S) proxy
settings. It does not expose Clash, SSH, or the Bridge publicly and does not copy
proxy subscriptions, node URIs, controller credentials, private keys, or traffic
logs into this repository or onto the server.

## Server contract

Create a dedicated, locked SSH account used only for remote forwarding. Its
`authorized_keys` entry must use a separate public key and restrict the key to the
single listener, for example:

```text
restrict,port-forwarding,permitlisten="127.0.0.1:17897" <public-key>
```

Keep `GatewayPorts no` effective for that account. If an sshd `Match User` block
is required, allow remote TCP forwarding only, keep agent/X11/TTY forwarding and
commands disabled, and retain the `PermitListen 127.0.0.1:17897` restriction.
Validate the effective sshd configuration before reloading it. The server must
listen only on `127.0.0.1:17897`; never add a public firewall rule or bind the
reverse forward to `0.0.0.0`, `*`, a public address, or a Docker gateway address.

Install `/etc/ai-lab-platform/hermes-egress.env` as a root-owned, root-group,
regular non-symlink file with mode `0600`, no more than 1024 bytes, and exactly:

```text
HTTPS_PROXY=http://127.0.0.1:17897
HTTP_PROXY=http://127.0.0.1:17897
NO_PROXY=localhost,127.0.0.1,<validated-Hermes-Bridge-bind-address>,::1
```

The optional systemd `EnvironmentFile` is shared by Bridge and Worker. If the
file is absent, direct egress behavior is unchanged. If it exists but ownership,
mode, type, size, keys, values, loopback endpoint, or `NO_PROXY` contract is
wrong, deployment and rollback verification fail closed before a runtime restart.

## macOS contract

In Clash Verge, set `allow-lan: false`, keep the HTTP/mixed listener on
`127.0.0.1:7897`, enable Clash Verge launch at login, and confirm it is running
before relying on the tunnel. Store the dedicated SSH private key as a user-owned
regular non-symlink file with mode `0400` or `0600`; keep a pinned, user-owned,
non-writable `known_hosts` file separately.

Use a per-user LaunchAgent with `RunAtLoad` and `KeepAlive` to call the generic
repository script with only host, restricted user, key path, known-hosts path,
and a non-sensitive HTTPS reachability URL:

```xml
<key>ProgramArguments</key>
<array>
  <string>/path/to/ops/scripts/clash-verge-egress-tunnel.sh</string>
  <string>server.example.invalid</string>
  <string>restricted-egress-user</string>
  <string>/Users/you/.ssh/restricted-egress</string>
  <string>/Users/you/.ssh/restricted-egress-known-hosts</string>
  <string>https://example.com/</string>
</array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

Do not put private-key contents, proxy configuration, subscriptions, node URIs,
controller credentials, or authenticated probe URLs in the plist, logs, shell
history, repository, or server environment file.

## Verification and rollback

Before enabling Hermes, verify on macOS that Clash owns only
`127.0.0.1:7897`, the HTTPS probe succeeds through it, and the LaunchAgent stays
loaded. On the server verify that SSH owns only `127.0.0.1:17897`, then run the
deployment verifier and inspect both units' effective `EnvironmentFiles`. Restart
Bridge and Worker only after those checks; verify real provider model sync, one
durable run, and the physical-device end-to-end path.

To roll back, quarantine or stop Bridge and Worker, unload the LaunchAgent, remove
the server egress env file, and confirm port 17897 is absent. Restore the prior
units/release through the normal deployment rollback, restart without proxy
variables, and repeat health checks. Leave the restricted account/key disabled if
the tunnel is retired. Never weaken host-key checking or widen either listener to
recover service.
