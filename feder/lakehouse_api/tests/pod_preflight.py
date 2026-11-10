#!/usr/bin/env python3
"""Can THIS environment use the lakehouse? Run it in the pod before a notebook run.

Self-contained: no imports beyond the standard library, no skills, no agent
call. Paste it into a cell or run it in a terminal. It costs nothing, and it
answers the two questions that would otherwise waste a full notebook run:

  1. can this host reach the endpoint at all?
  2. does it hold a token the endpoint will accept?

Since FEDER_AUTH_MODE=required, a failure on either one means every skill call
fails, and the notebook run tells you nothing about the skills.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("FEDER_API_URL", "https://sparcal.sdsc.edu/api/v1/FEDER").rstrip("/")
TOKEN_ENV = ("FEDER_API_TOKEN", "FDP_TOKEN", "BEARER_TOKEN")
TOKEN_FILES = ("~/.fdp/token",
               "~/work/_User-Persistent-Storage_CephBlock_/.fdp/token")

bad = []


def say(ok, label, detail=""):
    print(f"  {'OK      ' if ok else 'PROBLEM '}  {label}")
    if not ok:
        bad.append(label)
    if detail:
        print(f"              {detail}")


def find_token():
    for var in TOKEN_ENV:
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip(), f"${var}"
    unreadable = []
    for path in TOKEN_FILES:
        p = os.path.expanduser(path)
        try:
            with open(p) as fh:
                v = fh.read().strip()
            if v:
                return v, p
        except PermissionError:
            # "no token found" would send someone looking for a missing file
            # when one is sitting right there with the wrong owner or mode.
            unreadable.append(p)
        except OSError:
            continue
    return None, ("UNREADABLE:" + ",".join(unreadable)) if unreadable else None


def get(url, token=None, timeout=25):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"} if token else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def post(url, payload, token=None, timeout=40):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


print(f"endpoint: {BASE}\n")

print("=== 1. is the endpoint reachable from here? ===")
mode = None
try:
    t0 = time.time()
    _, h = get(f"{BASE}/health")
    mode = h.get("auth")
    say(True, f"reachable in {time.time() - t0:.1f}s "
              f"(auth={mode}, token_validation={h.get('token_validation')})")
except urllib.error.URLError as e:
    say(False, "cannot reach the endpoint", f"{e.reason} -- no outbound HTTPS "
        f"from this pod, DNS, or a proxy. Nothing else can work.")
except Exception as e:                                       # noqa: BLE001
    say(False, "cannot reach the endpoint", f"{type(e).__name__}: {e}")

print("\n=== 2. is there a token here, and will it be accepted? ===")
tok, where = find_token()
if not tok and where and where.startswith("UNREADABLE:"):
    say(False, "a token file exists but cannot be read",
        f"{where[len('UNREADABLE:'):]} -- wrong owner or mode. Fix with "
        f"`chmod 600` as its owner, or copy it somewhere this account can read.")
elif not tok:
    say(False, "no token found",
        f"looked at {', '.join('$' + v for v in TOKEN_ENV)} then "
        f"{', '.join(TOKEN_FILES)}. With auth=required nothing will work.")
else:
    say(True, f"token found in {where} ({len(tok)} chars)")
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        import base64
        claims = json.loads(base64.urlsafe_b64decode(payload))
        days = (claims["exp"] - time.time()) / 86400
        say(days > 0, f"expires {time.strftime('%Y-%m-%d', time.gmtime(claims['exp']))} "
                      f"({days:.1f} days)",
            "" if days > 3 else "renew it before relying on this for a demo")
    except Exception:                                        # noqa: BLE001
        print("              (could not read the expiry locally; the server decides)")

print("\n=== 3. does a real query work end to end? ===")
if tok:
    try:
        st, out = post(f"{BASE}/query",
                       {"sql": "SELECT COUNT(*) n FROM shots WHERE shot BETWEEN ? AND ?",
                        "params": [190000, 195000]}, token=tok)
        n = out["rows"][0][0]
        say(n == 3507, f"shots 190000..195000 -> {n:,} (expected 3,507)",
            "" if n == 3507 else "the view layer may not be in the search_path")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        say(False, f"query refused: HTTP {e.code}", body)
    except Exception as e:                                   # noqa: BLE001
        say(False, "query failed", f"{type(e).__name__}: {e}")

    print("\n=== 4. which skill version is installed here? ===")
    # $HOME is not always the account the image installed skills under -- a
    # container run with a host uid gets HOME=/tmp and would report every skill
    # ABSENT, which reads as a broken image rather than a wrong path.
    candidates = [os.path.expanduser("~/.deepagents/agent/skills"),
                  "/home/jovyan/.deepagents/agent/skills"]
    skills = next((c for c in candidates
                   if os.path.isdir(os.path.join(c, "d3d-elm-index"))),
                  candidates[0])
    if skills != candidates[0]:
        print(f"  (skills found under {skills}, not $HOME)")
    # A skill that still reads a local SQLite file can answer perfectly well
    # while proving nothing about the endpoint -- and if the old files are still
    # mounted it would look like a pass. Say which version is installed before
    # reporting anything about whether the skills work.
    for name in ("d3d-relational-db", "d3d-elm-index", "d3d-disruption"):
        d = os.path.join(skills, name)
        if not os.path.isdir(d):
            print(f"  ABSENT    {name}")
            continue
        served = os.path.exists(os.path.join(d, "d3d_lakehouse.py"))
        print(f"  {'ENDPOINT ' if served else 'SQLITE   '} {name}"
              f"{'' if served else '   <- pre-rc7 image; section 5 tests local files, not the lakehouse'}")

    print("\n=== 5. do the skills answer? ===")
    for name, mod, call in (
            ("d3d-relational-db", "d3d_relational_db",
             lambda m: len(m.plasma_shots_in_range(190000, 190010))),
            ("d3d-elm-index", "d3d_elm_index", lambda m: m.is_indexed(149058)),
            ("d3d-disruption", "d3d_disruption", lambda m: len(m.parameters()))):
        path = os.path.join(skills, name)
        if not os.path.isdir(path):
            say(False, f"{name} is not installed", path)
            continue
        sys.path.insert(0, path)
        try:
            import importlib
            m = importlib.import_module(mod)
            say(True, f"{name} -> {call(m)}")
        except Exception as e:                               # noqa: BLE001
            say(False, f"{name} failed", f"{type(e).__name__}: {str(e)[:140]}")

print()
print("Sections 1-3 are the go/no-go for the endpoint and are meaningful on ANY\n"
      "image. Sections 4-5 only test the lakehouse once the rc carrying the\n"
      "endpoint-backed skills is running.")
print()
if bad:
    print(f"NOT READY -- {len(bad)} problem(s). Fix these before spending a "
          f"notebook run:\n  - " + "\n  - ".join(bad))
    sys.exit(1)
print("READY. The lakehouse is reachable, the token is accepted, and all three "
      "skills answer.")
