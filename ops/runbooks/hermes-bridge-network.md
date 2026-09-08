# Hermes Bridge private Docker gateway contract

`hermes-bridge` is a host systemd service and the Compose API/workers reach it at
`http://host.docker.internal:9118`. Every caller declares
`host.docker.internal:host-gateway`; Docker maps that special value to the default
`bridge` gateway unless the daemon has an explicit host-gateway override.

The updater resolves `host.docker.internal` inside the running API container,
rejects empty, public, non-IPv4, or non-local addresses, and writes the accepted address to
`/etc/ai-lab-platform/hermes-bridge.env`. The systemd unit requires that file and
the Python bridge independently rejects anything outside RFC1918 space. The
service therefore listens only on the private Docker host address, never on
loopback, a public interface, or `0.0.0.0`. No public firewall rule for TCP 9118
is required or permitted; Ubuntu UFW may keep its normal public deny policy.
After `daemon-reload`, the installer rejects an effective systemd `ExecStart`
that bypasses the dedicated Bridge/Worker Python. `hermes_bridge.py` accepts no
command-line arguments, so `--host`, `--port`, positional, and stale drop-in
overrides fail instead of being silently ignored. The bind address comes only
from the validated environment file.

Host firewall policy still applies to container-to-host INPUT traffic. The final
API-container health probe is the authoritative check. If it fails while `ss`
shows the expected listener, permit TCP 9118 only from the Compose bridge
interface/subnet to the exact `HERMES_BRIDGE_BIND_ADDRESS`; never open the port on
a public interface or change the listener to `0.0.0.0`.

## Bridge/Worker runtime isolation

The exact-SHA updater builds a venv keyed by the runtime version and all dependency lock digests under
`/var/lib/quantumn-hermes/bridge-worker-venvs/`, owned by `quantumn-hermes`, then
atomically points `/var/lib/quantumn-hermes/bridge-worker-venv` at it. Both units
run platform code with that Python. The venv is populated from `requirements-build.lock`,
`requirements.lock`, and the host-only `requirements-bridge-worker.lock`, then the fixed
Hermes 0.21.1 source is installed with `--no-deps`. No hashed lock contains a Hermes wheel.
Startup validates that exact installed version. CLI fallback always uses
`/var/lib/quantumn-hermes/.local/bin/hermes`. Do not install platform requirements
into `.hermes/hermes-agent/venv` and do not invoke the Hermes launcher through the
Bridge/Worker venv.

After changing Docker address pools or `host-gateway-ip`, rerun the exact-SHA
updater before restarting the bridge. A resolution or local-address check failure
is a hard deployment failure; do not replace the address with `0.0.0.0`.

Verify on the host:

```bash
systemctl show hermes-bridge.service -p EnvironmentFiles
systemctl cat hermes-bridge.service
cat /etc/ai-lab-platform/hermes-bridge.env
readlink -f /var/lib/quantumn-hermes/bridge-worker-venv
sudo -u quantumn-hermes /var/lib/quantumn-hermes/bridge-worker-venv/bin/python -m pip check
sudo -u quantumn-hermes /var/lib/quantumn-hermes/bridge-worker-venv/bin/python -c \
  'import httpx, sqlalchemy, run_agent; print(run_agent.__file__)'
sudo -u quantumn-hermes /var/lib/quantumn-hermes/.hermes/hermes-agent/venv/bin/python -c \
  'import importlib.metadata; print(importlib.metadata.version("hermes-agent"))'
ss -ltnp '( sport = :9118 )'
docker compose exec -T api python -c \
  'import urllib.request; print(urllib.request.urlopen("http://host.docker.internal:9118/health", timeout=5).read().decode())'
```

The `ss` local address must equal the environment file and must be RFC1918. The
container probe must return the Hermes Bridge health JSON. A listener on
`0.0.0.0:9118`, `[::]:9118`, or `127.0.0.1:9118` fails the contract.
The printed Hermes version must be `0.21.1`; `run_agent.__file__` must be under
`/var/lib/quantumn-hermes/.hermes/hermes-agent`, while `httpx` and `sqlalchemy`
must import from the Bridge/Worker venv.

## Rollback

The updater records the prior application and Bridge/Worker venv symlink targets.
Any post-switch failure restores both before restarting services. For a manual
rollback, restore the previous immutable application release and its recorded
`bridge-worker-venv` target together, run `systemctl daemon-reload`, restart Bridge
and Worker, then repeat the version, import, listener, and container health probes.
Never point the units back at the Hermes runtime venv.
