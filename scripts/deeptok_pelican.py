"""DeepTok / ARGUS IPython startup: Pelican/DIII-D data access.

Defines reload_pelican() (and runs it once at kernel start). It:
  1. loads the Pelican bearer token into BEARER_TOKEN, searching (in order):
       - $FDP_TOKEN_FILE (if set)
       - ~/.fdp/token
       - ~/work/_User-Persistent-Storage_CephBlock_/.fdp/token   (NRP persistent
         storage -- set once, survives the short-lived JupyterHub pods)
  2. configures the DIII-D MDSplus tree paths by asking `fdp env` (computed
     trees like efit01 live under codes/, raw diagnostic trees like
     spectroscopy live under shots/, so a single static path is not enough).

It also defines the %fdp_login magic, which gets a new FDP token from a
notebook cell -- the only route for a scientist with no terminal, since
`fdp login` shells out to pelican and pelican requires a TTY.

If the token is placed AFTER the kernel started, just call `reload_pelican()`
in a cell -- no kernel restart needed. BEARER_TOKEN and the tree paths are read
by MDSplus at fetch time; only LD_PRELOAD must be set at launch, which the
Jupyter kernelspec handles.

Because IPython runs startup files in the interactive namespace, reload_pelican
is available directly in notebooks/consoles.

sage_magic's %reset keeps only the names that were in the namespace when ITS
startup script finished, and that snapshot is taken before this file runs
(00-sage-magic.py, then 01-deeptok-pelican.py). Without the block at the end of
this file a %reset wipes reload_pelican(), the %fdp_login helpers and every
other name defined here -- and because IPython execs startup files INTO the
user namespace, the still-registered %fdp_login magic is then looking up its
own globals in a namespace that no longer has them.
"""

try:
    _FDP_NS_AT_IMPORT = frozenset(get_ipython().user_ns.keys())  # noqa: F821
except Exception:                                                # noqa: BLE001
    _FDP_NS_AT_IMPORT = frozenset()


def reload_pelican(verbose=True):
    """(Re)load the Pelican token + DIII-D MDSplus tree paths into the env.

    Call this after placing your token if data access is off -- no kernel restart
    required. Returns True if the token was loaded, else False.
    """
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    candidates = []
    env_path = os.environ.get("FDP_TOKEN_FILE")
    if env_path:
        candidates.append(Path(env_path))
    candidates += [
        Path.home() / ".fdp" / "token",
        Path.home() / "work" / "_User-Persistent-Storage_CephBlock_" / ".fdp" / "token",
    ]

    token = None
    for p in candidates:
        try:
            if p.exists():
                t = p.read_text().strip()
                if t:
                    token = t
                    break
        except Exception:
            continue

    if not token:
        if verbose:
            # The first thing a new user sees, so it names the one step that
            # works from a notebook. Telling someone with no token to paste a
            # token is not an instruction they can follow.
            print("DeepTok: no FDP token found -- DIII-D data access is OFF.")
            print("  Run this in a cell to get one:")
            print("      %fdp_login")
            print("  It opens a browser link to approve, then sets everything up.")
            print("  Searched: " + ", ".join(str(p) for p in candidates))
        return False
    os.environ["BEARER_TOKEN"] = token

    # Mirror the token to ~/.fdp/token so the `fdp` wrapper works too -- fdp reads
    # that exact path (`cat ~/.fdp/token`), but the token may live only in NRP
    # persistent storage. This keeps in-kernel fetches and `fdp python` consistent.
    try:
        std = Path.home() / ".fdp" / "token"
        if not std.exists() or std.read_text().strip() != token:
            std.parent.mkdir(parents=True, exist_ok=True)
            std.write_text(token)
    except Exception:
        pass

    # Tree paths come from `fdp env`, which prints the same `export K=V` lines
    # the old mdsplus_d3d_env.py helper did. That helper shipped with fdp 0.4.x
    # and is absent from 0.11.0, so this block silently set NOTHING from the
    # 0.1.15 upgrade onward -- `Path(env_helper).exists()` was simply False and
    # n stayed 0. Agent fetches were unaffected because the skills invoke
    # `fdp run`, which builds this environment itself; only direct in-kernel
    # fetches saw it, and only outside efit01, whose path is baked into the
    # image. Asking fdp removes the duplicate and cannot go stale again.
    device = os.environ.get("FDP_DEFAULT_DEVICE", "d3d")
    n = 0
    try:
        out = subprocess.run(
            ["fdp", "env", "-D", device],
            capture_output=True, text=True, timeout=90,
        )
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                k, v = line[len("export "):].split("=", 1)
                os.environ[k] = v.strip().strip("'").strip('"')
                n += 1
        if n == 0 and verbose:
            detail = (out.stderr or out.stdout).strip()[:200]
            print(f"DeepTok: `fdp env -D {device}` set no tree paths."
                  + (f" {detail}" if detail else ""))
    except Exception as e:
        if verbose:
            print("DeepTok: could not configure DIII-D tree paths:", e)

    if verbose:
        print(f"DeepTok: Pelican ready -- token loaded, {n} {device} env vars set.")
    return True


# ---------------------------------------------------------------------------
# %fdp_login -- get a new FDP token from a notebook cell.
#
# A first-time user has no token and must do this; an existing user whose token
# expired does the same thing, so one command covers both. It runs the OAuth
# device flow over plain HTTP, which is why it works here at all: `fdp login`
# shells out to pelican, and pelican requires a TTY that a notebook kernel does
# not have.
#
# The issuer is DISCOVERED from the federation director, never hardcoded --
# devices do not share one. d3d uses the automated issuer on :8000, while cmod
# still points at t.nationalresearchplatform.org/fdp, which serves no device
# flow at all; a hardcoded URL would hand a cmod request a d3d token.
# ---------------------------------------------------------------------------

_FDP_UA = {"User-Agent": "fdp-login/1.0"}  # osg-htc.org 403s Python-urllib
_FDP_SCOPE = "storage.read:/ offline_access"


def _fdp_paths(device):
    """Where a token is written. CephBlock is the only durable one: /home/jovyan
    is wiped on every pod restart, including ~/.fdp/cache that `fdp` reads."""
    from pathlib import Path
    home = Path.home()
    persist = home / "work" / "_User-Persistent-Storage_CephBlock_" / ".fdp"
    return {
        "persist": persist / "token",                    # what reload_pelican reads
        "refresh": persist / f"{device}.refresh",        # for silent renewal later
        "mirror": home / ".fdp" / "token",               # the `fdp` CLI fallback
        "cache": home / ".fdp" / "cache" / f"{device}.token",  # what fdp reads first
    }


def _fdp_write_private(path, value):
    """Atomic 0600 write: temp in the same directory, then rename over."""
    import os
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(value)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(str(tmp), str(path))


def _fdp_discover(device):
    """(issuer, namespace) for a device, read from the federation director.

    The director answers 307 and the auth headers ride on THAT response;
    following the redirect lands on a cache that 403s without a token.
    """
    import json, re, urllib.error, urllib.parse, urllib.request

    from fdp import devices

    root = devices.active_handles(device)[0].schema.pelican_root
    if not root:
        raise RuntimeError(f"device '{device}' declares no pelican_root")
    u = urllib.parse.urlparse(root)
    federation, namespace = u.netloc, u.path.rstrip("/")

    cfg = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://{federation}/.well-known/pelican-configuration",
        headers=_FDP_UA), timeout=25).read())

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    url = cfg["director_endpoint"].rstrip("/") + namespace + "/"
    try:
        hdr = urllib.request.build_opener(_NoRedirect).open(
            urllib.request.Request(url, headers=_FDP_UA), timeout=25).headers
    except urllib.error.HTTPError as exc:
        hdr = exc.headers
    gen = hdr.get("X-Pelican-Token-Generation", "") if hdr else ""
    match = re.search(r"issuer=([^,\s]+)", gen)
    if not match:
        raise RuntimeError(f"the director advertises no token issuer for {namespace}")
    return match.group(1), namespace


def _fdp_post(url, data, headers):
    import json, urllib.error, urllib.parse, urllib.request
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(), headers=headers)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read()), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return None, json.loads(raw)
        except Exception:
            return None, {"error": f"http_{exc.code}", "detail": raw[:300]}


_FDP_KEEP_HOURS = 4.0  # matches fdp's own "expiring soon" threshold


def _fdp_remaining_hours(device):
    """Hours left on the installed token, or None if there isn't a usable one."""
    import base64, json, time
    for path in (_fdp_paths(device)["persist"], _fdp_paths(device)["mirror"]):
        try:
            tok = path.read_text().strip()
            payload = tok.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        except Exception:                                    # noqa: BLE001
            continue
        if exp:
            left = (exp - time.time()) / 3600.0
            if left > 0:
                return left
    return None


def fdp_login(line=""):
    """%fdp_login [device] [force] -- get a new FDP token via the browser.

    Covers a first-time user (no token at all) and an expired one; both need a
    fresh browser consent. Returns True when a token was installed.

    A login REPLACES whatever is installed, and the automated issuer mints
    24-hour tokens while hand-issued ones can run a month. Without a guard,
    someone with three weeks left who ran this out of curiosity would be left
    with one day. So a token that still has real time on it is kept unless
    `force` is given, and the user is told how long they have.
    """
    import base64, json, os, time, urllib.request

    words = (line or "").split()
    force = any(w.lower() in ("force", "--force", "-f") for w in words)
    named = [w for w in words if not w.startswith("-")
             and w.lower() not in ("force",)]
    device = (named[0] if named else "") or os.environ.get("FDP_DEFAULT_DEVICE", "d3d")

    if not force:
        left = _fdp_remaining_hours(device)
        if left is not None and left > _FDP_KEEP_HOURS:
            days = left / 24.0
            have = f"{days:.1f} days" if days >= 1 else f"{left:.1f} hours"
            print(f"You already have a token for {device} valid for {have}.\n"
                  f"  Logging in again would REPLACE it, and a new token lasts "
                  f"24 hours.\n"
                  f"  Run  %fdp_login {device} force  to replace it anyway.")
            return True

    try:
        issuer, namespace = _fdp_discover(device)
    except Exception as exc:
        print(f"Could not find the token issuer for '{device}': {exc}")
        return False

    meta = json.loads(urllib.request.urlopen(urllib.request.Request(
        issuer + "/.well-known/openid-configuration", headers=_FDP_UA),
        timeout=25).read())
    if not meta.get("device_authorization_endpoint"):
        print(f"The issuer for '{device}' ({issuer}) serves no device flow,\n"
              f"so a token cannot be obtained from a notebook. Ask the FDP team\n"
              f"for a token for {namespace}.")
        return False

    scope = _FDP_SCOPE
    supported = meta.get("scopes_supported")
    if supported:
        scope = " ".join(s for s in ("storage.read:/", "offline_access")
                         if s in supported) or scope

    body = json.dumps({
        "client_name": "argus-feder-notebook",
        "grant_types": ["urn:ietf:params:oauth:grant-type:device_code",
                        "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_basic",
        "scope": scope}).encode()
    reg = json.loads(urllib.request.urlopen(urllib.request.Request(
        meta["registration_endpoint"], data=body,
        headers={"Content-Type": "application/json", **_FDP_UA}), timeout=30).read())
    basic = base64.b64encode(
        f"{reg['client_id']}:{reg['client_secret']}".encode()).decode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + basic, **_FDP_UA}

    dev, err = _fdp_post(meta["device_authorization_endpoint"],
                         {"client_id": reg["client_id"], "scope": scope}, hdrs)
    if err:
        print(f"Could not start the login: {err}")
        return False

    url = dev.get("verification_uri_complete") or dev.get("verification_uri")
    try:
        from IPython.display import HTML, display
        display(HTML(
            f'<div style="padding:10px;border-left:4px solid #2a7;'
            f'background:rgba(136,136,136,0.12)">'
            f'<b>Approve this FDP login</b><br>'
            f'<a href="{url}" target="_blank" rel="noopener">{url}</a><br>'
            f'<small>code <b>{dev.get("user_code")}</b> &middot; '
            f'if it returns the same expired token, approve in a private '
            f'window &mdash; the issuer caches your groups for up to 16 h.'
            f'</small></div>'))
    except Exception:
        print(f"Approve this FDP login:\n  {url}\n  code {dev.get('user_code')}")

    interval = int(dev.get("interval", 5))
    deadline = time.time() + int(dev.get("expires_in", 600))
    tok = None
    while time.time() < deadline:
        time.sleep(interval)
        tok, err = _fdp_post(meta["token_endpoint"], {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dev["device_code"],
            "client_id": reg["client_id"]}, hdrs)
        if tok:
            break
        code = (err or {}).get("error", "")
        if code in ("authorization_pending", "slow_down", "not_found"):
            if code == "slow_down":
                interval += 5
            continue
        print(f"Login failed: {err}")
        return False
    if not tok:
        print("Timed out waiting for approval. Run %fdp_login again.")
        return False

    access = tok["access_token"]
    paths = _fdp_paths(device)
    # The refresh token rotates, so persist it before anything else touches it.
    if tok.get("refresh_token"):
        _fdp_write_private(paths["refresh"], tok["refresh_token"])
    for key in ("persist", "mirror", "cache"):
        _fdp_write_private(paths[key], access)
    os.environ["BEARER_TOKEN"] = access

    payload = access.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    hours = (claims.get("exp", 0) - time.time()) / 3600
    groups = claims.get("wlcg.groups")
    print(f"Logged in to {device}. Token valid for {hours:.1f} h"
          + (f"; groups {groups}" if groups else ""))
    if "storage.read:/" not in (claims.get("scope") or ""):
        print("  WARNING: this token carries no storage.read scope, so data\n"
              "  reads will be refused. Your account may not be authorized\n"
              "  for this namespace yet.")
        return False
    reload_pelican(verbose=False)
    print("  Data access is ready.")
    return True


try:
    from IPython.core.magic import register_line_magic as _register_line_magic

    def _fdp_login_magic(line=""):
        """Run the login and show nothing extra.

        A line magic's return value IS the cell's result, so returning the
        bool printed a bare `True` under the message, as an Out[...] with its
        own prompt. The bool is for a caller -- `if fdp_login(): ...` -- and
        is kept by calling through to the function rather than registering it.
        """
        fdp_login(line)

    _fdp_login_magic.__name__ = "fdp_login"
    _register_line_magic(_fdp_login_magic)
except Exception:  # not under IPython, or magics unavailable
    pass


# Run once at kernel start.
try:
    reload_pelican(verbose=True)
except Exception as _e:  # never let startup break the kernel
    print("DeepTok: reload_pelican() failed at startup:", _e)


# Protect this file's own names from %reset (see the note in the module
# docstring). Additive: it only ever adds to the keep-set, and it does nothing
# when sage_magic has not already published one -- which is also the case when
# the load order is reversed, where sage_magic's own snapshot covers these
# names anyway.
try:
    _ip = get_ipython()  # noqa: F821
    if _ip is not None and "_SAGE_RESET_KEEP" in _ip.user_ns:
        _ip.user_ns["_SAGE_RESET_KEEP"] = (
            frozenset(_ip.user_ns["_SAGE_RESET_KEEP"])
            | (frozenset(_ip.user_ns.keys()) - _FDP_NS_AT_IMPORT)
        )
except Exception:                                                # noqa: BLE001
    pass
