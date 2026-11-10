#!/bin/bash
# Build, verify, push and tidy an ARGUS-FEDER image.
#
#   ./scripts/build_argus_feder.sh 0.1.8-rc12              # build + verify
#   ./scripts/build_argus_feder.sh 0.1.8-rc12 --push       # + push, delete the previous rc
#   ./scripts/build_argus_feder.sh 0.1.8-rc12 --push --keep-previous
#
# Why this exists rather than a hand-typed docker build:
#
#   * `docker build ... | tail` returns the PIPE's exit code, so a failed build
#     reports success. This redirects to a log and checks the real code.
#   * Several things must be IN the image and are invisible until a run fails:
#     the review criteria, the agent packages at their pinned versions, the
#     skills, the magic. They are asserted here, before the push.
#   * The superseded rc tags have to go, under both names, every time.
#
set -u -o pipefail

VERSION="${1:-}"
[ -n "$VERSION" ] || { echo "usage: $0 <version> [--push] [--keep-previous]"; exit 2; }
shift
PUSH=0; KEEP=0
for a in "$@"; do
    case "$a" in
        --push) PUSH=1 ;;
        --keep-previous) KEEP=1 ;;
        *) echo "unknown option: $a"; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL="argus-feder:${VERSION}"
HUB="kaiucsd/argus-feder:${VERSION}"
LOG="/tmp/argus-feder-${VERSION}-build.log"

cd "$ROOT"

echo "==> building ${LOCAL} and ${HUB}"
echo "    log: ${LOG}"
docker build -t "$LOCAL" -t "$HUB" -f scripts/Dockerfile.argus . > "$LOG" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    echo "!!  BUILD FAILED (exit $rc). Last 25 lines:"
    tail -25 "$LOG"
    exit $rc
fi
echo "    built"

# ---------------------------------------------------------------- verify -----
# Each check is a thing that has silently been wrong in a shipped image.
echo "==> verifying the image"
fail=0
check() {  # check <description> <expected> <shell producing actual>
    local desc="$1" want="$2" got
    got=$(docker run --rm --entrypoint bash "$LOCAL" -lc "$3" 2>/dev/null | tr -d '\r\n[:space:]')
    if [ "$got" = "$want" ]; then
        printf '    ok    %-46s %s\n' "$desc" "$got"
    else
        printf '    FAIL  %-46s got %-14s want %s\n' "$desc" "${got:-<empty>}" "$want"
        fail=1
    fi
}

MAGIC=/home/jovyan/.ipython/profile_default/startup/00-sage-magic.py
PELICAN=/home/jovyan/.ipython/profile_default/startup/01-deeptok-pelican.py
RULES=/home/jovyan/.deepagents/review_rules.md

check "sage magic installed"          "1"  "test -f $MAGIC && echo 1 || echo 0"
check "review_rules.md baked"         "1"  "test -f $RULES && echo 1 || echo 0"
check "review criteria (bullets)"     "5"  "grep -c '^- ' $RULES"
check "DATA FILE RULE in the prompt"  "1"  "grep -c 'DATA FILE RULE' $MAGIC"
check "FIGURE RULE in the prompt"      "1"  "grep -c 'FIGURE RULE' $MAGIC"
check "MATH RULE in the prompt"        "1"  "grep -c 'MATH RULE' $MAGIC"
# The progress fold has to work in a notebook nobody has trusted: a new pod
# keeps no record of this file, so a script in saved output never runs and a
# JavaScript fold would be there the day it ran and gone the day it reopened.
# Folded for real here and the result inspected, rather than grepped for.
check "trail folds with no script"    "1"  "ipython -c \"import IPython.display as d;o=[];d.display=lambda *a,**k:o.append(getattr(a[0],'data',''));d.clear_output=lambda wait=False:None;_sage_trail_start();_display_tool_call('read_file',{'file_path':'/x'});_sage_trail_collapse(1);_sage_trail_emit();f=[str(x) for x in o if 'sage-fold-' in str(x)];print('TRAIL',1 if (len(f)==1 and '<script' not in f[0] and 'read_file' in f[0] and 'summary' in f[0]) else 0)\" 2>/dev/null | sed -n 's/^TRAIL //p'"
# The agent stopping and the answer being ready are seconds apart -- a
# notebook to sign, a widget to flush -- and for those seconds the cell used
# to show a folded trail and no answer. The fold is built when the agent
# stops and shown when the answer is ready, so building it must emit nothing.
check "fold waits for the answer"    "1"  "ipython -c \"import IPython.display as d;o=[];c=[];d.display=lambda *a,**k:o.append(getattr(a[0],'data','') if a else '');d.clear_output=lambda wait=False:c.append(wait);_sage_trail_start();_display_tool_call('read_file',{'file_path':'/x'});_sage_trail_collapse(1);built=(not c and not [x for x in o if 'sage-fold-' in str(x)] and bool(_SAGE_TRAIL['block']));_sage_trail_emit();_sage_trail_emit();shown=(c==[True] and len([x for x in o if 'sage-fold-' in str(x)])==1);print('WAIT',1 if (built and shown) else 0)\" 2>/dev/null | sed -n 's/^WAIT //p'"
check "markdown-it (fold narration)" "1"  "python -c 'import markdown_it' >/dev/null 2>&1 && echo 1 || echo 0"
# Two scripts are left, and neither may reach the saved file. One records
# where the reader is looking while the trail streams; the rewrite's
# clear_output takes it with the cards. The other corrects the scroll
# afterwards, consults that recording, and erases itself through its own
# display handle. Asserted: both emitted, the correction keyed to the
# recording, and the correction replaced by nothing.
check "scroll script erases itself"  "1"  "ipython -c \"import IPython.display as d,types;o=[];u=[];d.display=(lambda *a,**k:(o.append(getattr(a[0],'data','') if a else ''),types.SimpleNamespace(update=lambda obj,**kw:u.append(getattr(obj,'data',''))) if k.get('display_id') else None)[1]);d.clear_output=lambda wait=False:None;_sage_trail_start();w=_SAGE_TRAIL['watch_id'];_display_tool_call('read_file',{'file_path':'/x'});_sage_trail_collapse(1);_sage_trail_emit();_sage_scroll_to_answer();s=[str(x) for x in o if '<script' in str(x)];print('SCROLL',1 if (len(s)==2 and w and w in s[0] and w in s[1] and u==['']) else 0)\" 2>/dev/null | sed -n 's/^SCROLL //p'"
# A run that fails keeps its trail open on screen -- but the recorder is not
# the reader's output, and nothing clears it on that path, so it is taken
# back by hand or it ends up in the saved file.
check "watcher taken back on error"  "1"  "ipython -c \"import IPython.display as d,types;u=[];d.display=(lambda *a,**k:types.SimpleNamespace(update=lambda obj,**kw:u.append(getattr(obj,'data',''))) if k.get('display_id') else None);d.clear_output=lambda wait=False:None;_sage_trail_start();_display_tool_call('read_file',{'file_path':'/x'});_sage_trail_cancel();print('WATCH',1 if u==[''] else 0)\" 2>/dev/null | sed -n 's/^WATCH //p'"
# %model is how Greg and Amy pick the LLM without a terminal. Its cache clear
# is not cosmetic: without it the config changes and the kernel keeps serving
# the previous model, silently and with a perfectly good answer.
check "%model magic installed"        "1"  "grep -c 'def model(line)' $MAGIC"
check "%model clears config cache"    "1"  "grep -c 'model_config.clear_caches' $MAGIC"
check "tomlkit (%model needs it)"     "1"  "python -c 'import tomlkit' >/dev/null 2>&1 && echo 1 || echo 0"
# The data layer. These were unpinned and silently stale for several releases
# (see Dockerfile.argus step 1), so the versions are asserted here too: a pin
# that is never checked is a pin that drifts the next time a layer is rebuilt.
# The data layer, per Brian Sammuli's spec for the cross-device image.
# fdp-core-latest (NOT fdp-core: that one pins python 3.11 and would move the
# whole image off 3.12). toksearch_cmod is separate and carries MIT's C-Mod TDI
# functions -- without it C-Mod trees open but \ip does not evaluate, which
# looks like bad data rather than a missing package.
check "python stays 3.12"            "1"  "python -c \"import sys;print(1 if sys.version_info[:2]==(3,12) else 0)\""
check "fdp-core-latest >= 1.25"      "1"  "conda list 2>/dev/null | awk '/^fdp-core-latest /{print (\$2>=\"1.25.0\")?1:0}'"
check "toksearch_cmod installed"     "1"  "conda list 2>/dev/null | grep -c '^toksearch_cmod '"
check "mdsip-fdp installed"          "1"  "conda list 2>/dev/null | grep -c '^mdsip-fdp '"
# Exactly two devices, and no duplicate catalog: fdp raises RuntimeError on a
# duplicate tokamak name, so a leftover hand-written cmod YAML breaks everything.
check "fdp devices = d3d + cmod"     "2"  "python -c \"from fdp.catalog import catalog; n=catalog.names(); print(len([x for x in n if x in ('d3d','cmod')]))\" 2>/dev/null"
check "no hand-rolled cmod catalog"  "0"  "python -c \"import importlib.util;print(1 if importlib.util.find_spec('fdp_cmod') else 0)\" 2>/dev/null"
# disruption-py lives in its own prefix and must NOT see toksearch.
check "disruption-py env imports"    "1"  "/opt/conda/envs/disruption-py-fdp/bin/python -c 'from disruption_py.workflow import get_shots_data' >/dev/null 2>&1 && echo 1 || echo 0"
check "d-py env has no toksearch"    "0"  "/opt/conda/envs/disruption-py-fdp/bin/python -c 'import toksearch' >/dev/null 2>&1 && echo 1 || echo 0"
check "d-py smoke test present"      "1"  "test -f /opt/disruption-py-fdp/tests/test_fdp_origin.py && echo 1 || echo 0"
check "d-py origin config baked"     "1"  "grep -c 'fdp://fdp-d3d-origin' /home/jovyan/.config/disruption-py/user.toml"
check "USER is set (disruption-py)" "jovyan" "printf '%s' \"\$USER\""
# The MCP is a stdio server inside the FDP env, not a URL.
check "toksearch MCP module present"  "1"  "python -c 'import importlib.util;print(1 if importlib.util.find_spec(\"toksearch.llm.mcp\") else 0)' 2>/dev/null"
# The disruption-py COMPUTE skill. Without it the image can run disruption-py
# but an agent driven by natural language cannot reach it.
# 0.1.15 shipped with PTDATA broken: two registered devices made bare
# `fdp run` refuse to pick one. Both halves of the fix are asserted.
check "default device is d3d"      "d3d"  "printf '%s' \"\$FDP_DEFAULT_DEVICE\""
check "ptdata helper names device"    "1"  "grep -c '\"-D\", \"d3d\"' /home/jovyan/.deepagents/agent/skills/d3d-shot-fetcher/d3d_ptdata.py"
check "bare fdp run resolves"         "1"  "fdp env 2>/dev/null | grep -c 'fdp-d3d/archives' | awk '{print (\$1>0)?1:0}'"
check "d3d-disruption-compute skill" "1"  "test -f /home/jovyan/.deepagents/agent/skills/d3d-disruption-compute/SKILL.md && echo 1 || echo 0"
check "compute skill helper"         "1"  "python -c \"import importlib.util as u;print(1 if u.spec_from_file_location('m','/home/jovyan/.deepagents/agent/skills/d3d-disruption-compute/d3d_disruption_compute.py') else 0)\" 2>/dev/null"
# working_dir() is what stopped the agent writing files outside the folder.
check "compute skill working_dir"    "1"  "grep -c 'def working_dir' /home/jovyan/.deepagents/agent/skills/d3d-disruption-compute/d3d_disruption_compute.py"

# MAST. The device has shipped since 0.1.18, but with no skill the agent has
# no MAST vocabulary and cannot be asked about it. The skills we install are
# OURS, correcting upstream's: the upstream pair state the time convention
# backwards (seconds, when MastSignal returns milliseconds) and point at two
# catalog helpers that time out from the pod. Both corrections are asserted,
# because a package upgrade would quietly reinstate the upstream text.
MASTFDP=/home/jovyan/.deepagents/agent/skills/toksearch-mast-fdp/SKILL.md
MASTIMAS=/home/jovyan/.deepagents/agent/skills/toksearch-mast-imas/SKILL.md
check "mast device registered"       "1"  "python -c \"from fdp.catalog import catalog;print(1 if 'mast' in catalog.names() else 0)\" 2>/dev/null"
check "toksearch_mast importable"    "1"  "python -c 'import toksearch_mast' >/dev/null 2>&1 && echo 1 || echo 0"
check "toksearch-mast-fdp skill"     "1"  "test -f $MASTFDP && echo 1 || echo 0"
check "toksearch-mast-imas skill"    "1"  "test -f $MASTIMAS && echo 1 || echo 0"
check "mast skill says MILLISECONDS" "1"  "grep -c 'Times are MILLISECONDS' $MASTFDP"
check "mast skill warns on catalog"  "1"  "grep -c 'not reachable from this environment' $MASTFDP"
# Presence, not an exact count: the phrase is in the description AND the body,
# and a check that breaks when a skill gains a sentence is a check nobody keeps.
check "mast skill says no token"     "1"  "grep -c 'never needs a token' $MASTFDP | awk '{print (\$1>0)?1:0}'"

# The tree rule. An agent asked for the archived confinement time opened the
# wrong tree, hit TreeNODATA, and wrote four tree-walking scripts hunting for
# a node that does not exist for that shot. Both halves of the fix are
# asserted: which tree to ask, and that NODATA from it is the final answer.
SHOTFETCH=/home/jovyan/.deepagents/agent/skills/d3d-shot-fetcher/SKILL.md
check "shot-fetcher has the tree rule"  "1"  "grep -c 'NOT the tree to pass' $SHOTFETCH"
check "tree rule names d3d superset"    "1"  "grep -c 'strict superset' $SHOTFETCH"
check "NODATA is a final answer"        "1"  "grep -c 'there is no data .*for this shot' $SHOTFETCH | awk '{print (\$1>0)?1:0}'"
# Three reductions an agent got wrong on the cross-device confinement run, each
# costing a conclusion rather than an error. Asserted because they are prose,
# and prose is what a skill rewrite drops first.
RELDB=/home/jovyan/.deepagents/agent/skills/d3d-relational-db/SKILL.md
check "chord family documented"         "1"  "grep -c 'one failing is not the quantity failing' $SHOTFETCH"
check "chord sanity range given"        "1"  "grep -c '1e19 to 1e20' $SHOTFETCH"
check "fast trace is averaged"          "1"  "grep -c 'average, do not sample' $SHOTFETCH"
check "modulation named as the cause"   "1"  "grep -c 'square-wave modulated' $SHOTFETCH"
check "unit label is not a guarantee"   "1"  "grep -c 'is a label, not a guarantee' $SHOTFETCH"
check "summaries units caveat"          "1"  "grep -c 'carries no unit guarantee' $RELDB"
check "derived summary column caveat"   "1"  "grep -c 'is a claim, not a measurement' $RELDB"

check "deepagents"                "0.7.5"  "pip show deepagents 2>/dev/null | awk '/^Version:/{print \$2}'"
check "deepagents-code"          "0.1.54"  "pip show deepagents-code 2>/dev/null | awk '/^Version:/{print \$2}'"
check "glm routing patch applied"     "1"  "grep -c 'nrp' /opt/conda/lib/python3.12/site-packages/deepagents_code/config.py | head -1 | awk '{print (\$1>0)?1:0}'"
check "skills installed"              "1"  "test -d /home/jovyan/.deepagents/agent/skills/d3d-materials && echo 1 || echo 0"
check "literature skill baked"        "1"  "test -d /home/jovyan/.deepagents/agent/skills/literature && echo 1 || echo 0"
# The CMF provenance skill. A skill that fails to reach the image is
# indistinguishable from a routing failure when seen from a notebook: the agent
# simply never opens it. The helper is imported rather than grepped, which also
# catches a syntax error or a stdlib import that is missing inside the image.
# No credentials are needed to import it.
CMFSKILL=/home/jovyan/.deepagents/agent/skills/cmf-provenance
check "cmf-provenance skill baked"     "1"  "test -f $CMFSKILL/SKILL.md && echo 1 || echo 0"
check "cmf helper imports in image"    "1"  "python -c 'import sys;sys.path.insert(0,\"$CMFSKILL\");import cmf_client' >/dev/null 2>&1 && echo 1 || echo 0"
check "cmf helper reads KEYCLOAK vars" "1"  "grep -c KEYCLOAK_USERNAME $CMFSKILL/cmf_client.py | awk '{print (\$1>0)?1:0}'"
check "d3d-materials knows literature" "1"  "grep -c literature_scope /home/jovyan/.deepagents/agent/skills/d3d-materials/d3d_materials.py | awk '{print (\$1>0)?1:0}'"
# The ontology reaches the agent only if BOTH halves are baked: the helper that
# calls the lakehouse proxy, and the note that tells the report to use it. These
# live in argus_feder/skills, a tree that has been stale before now.
check "ontology helper baked"          "1"  "grep -c 'def load_mvp_ontology' /home/jovyan/.deepagents/agent/skills/d3d-materials/d3d_materials.py"
check "ontology note in SKILL.md"      "1"  "grep -c \"Give a method or a material the field's name once\" /home/jovyan/.deepagents/agent/skills/d3d-materials/SKILL.md"
check "ABSENT SOURCE RULE in prompt"  "1"  "grep -c 'ABSENT SOURCE RULE' $MAGIC"
# Added after a single %%ask spent 91 tool calls on a lakehouse 401 it had
# correctly diagnosed within the first 30.
check "CREDENTIAL FAILURE RULE"       "1"  "grep -c 'CREDENTIAL FAILURE RULE' $MAGIC"
# %fdp_login is how a scientist with no token, or an expired one, gets a new
# one without a terminal -- `fdp login` shells out to pelican, which needs a
# TTY the kernel does not have. The magic talks to the issuer over HTTP.
check "%fdp_login magic installed"    "1"  "grep -c 'def fdp_login' $PELICAN"
# A line magic's return value IS the cell result, so registering the function
# directly printed a bare `True` under the message. The magic has to be the
# wrapper, which is asserted against the live magics manager, not by grep.
check "%fdp_login echoes nothing"    "1"  "ipython -c \"ip=get_ipython();f=ip.magics_manager.magics['line'].get('fdp_login');print('WRAP',1 if f is ip.user_ns.get('_fdp_login_magic') else 0)\" 2>/dev/null | sed -n 's/^WRAP //p'"
check "%fdp_login discovers issuer"   "1"  "grep -c 'def _fdp_discover' $PELICAN"
# reload_pelican called fdp 0.4.x's mdsplus_d3d_env.py, which 0.11.0 does not
# ship. From 0.1.15 the whole tree-path block was skipped and it reported
# "0 tree paths" as though that were normal. It now asks fdp directly.
check "no stale mdsplus helper call"  "0"  "grep -c 'which(.mdsplus_d3d_env' $PELICAN"
check "tree paths come from fdp env"  "1"  "grep -c '\"fdp\", \"env\"' $PELICAN"
check "fdp env yields tree paths"     "1"  "fdp env -D d3d 2>/dev/null | grep -c default_tree_path"
# A login REPLACES the installed token, and the automated issuer mints 24-hour
# ones while hand-issued tokens can run a month. Without the guard, a user with
# three weeks left who ran %fdp_login out of curiosity would be left with a day.
check "%fdp_login keeps a good token"  "1"  "grep -c '_FDP_KEEP_HOURS' $PELICAN | awk '{print (\$1>0)?1:0}'"
# %reset wipes every name not in sage_magic's _SAGE_RESET_KEEP, and that
# snapshot is taken when 00-sage-magic.py finishes -- before this file runs. A
# manager hit it: %fdp_login after a %reset raised NameError on
# _fdp_remaining_hours, because the registered magic looks its globals up in
# the user namespace that %reset had just emptied. Asserted at RUNTIME rather
# than by grep: this only works if the keep-set really covers these names after
# both startup files have run, in the order the image installs them.
check "%reset keeps the pelican names"  "7"  "ipython -c \"ks=get_ipython().user_ns.get('_SAGE_RESET_KEEP',frozenset());print('KEEP',sum(n in ks for n in ('reload_pelican','fdp_login','_fdp_remaining_hours','_fdp_paths','_fdp_discover','_fdp_post','_FDP_KEEP_HOURS')))\" 2>/dev/null | sed -n 's/^KEEP //p'"
# Three places used to tell a notebook user to run `fdp login`, which needs a
# TTY the kernel does not have, or to paste a token they do not have.
check "startup names %fdp_login"      "1"  "grep -c '%fdp_login' $PELICAN | awk '{print (\$1>0)?1:0}'"
check "lakehouse 401 names %fdp_login" "1"  "grep -c 'fdp_login' /home/jovyan/.deepagents/agent/skills/d3d-materials/d3d_lakehouse.py | awk '{print (\$1>0)?1:0}'"
check "shot-fetcher documents it"      "1"  "grep -c 'fdp_login' /home/jovyan/.deepagents/agent/skills/d3d-shot-fetcher/SKILL.md | awk '{print (\$1>0)?1:0}'"
check "ANSWER FROM THE DATA rule"     "1"  "grep -c 'ANSWER FROM THE DATA RULE' $MAGIC"
check "nrp is the default model"      "1"  "grep -c 'nrp:deepseek-v4-flash' /home/jovyan/.deepagents/config.toml"
check "no external LLM provider baked" "0"  "grep -c 'api.openai.com' /home/jovyan/.deepagents/config.toml"
# Behavioural, not a grep: rc16 passed "MATH RULE in the prompt" while the
# renderer escaped every '$' to '&#36;', so MathJax never saw a delimiter and
# the reader got raw "\$\$ \\sigma_R ... \$\$". This runs the fixer and asserts
# both halves: a formula keeps its literal delimiters, a price keeps its escape.
check "math survives the markdown fixer" "ok" "python -c \"import re,types; src=open('$MAGIC').read(); s=src.index('def _fix_glm_markdown'); e=src.index(chr(10)+'def ',s+10); m=types.ModuleType('m'); m.__dict__['re']=re; exec(compile(src[s:e],'x','exec'),m.__dict__); D=chr(36); t='Cost '+D+'5.'+chr(10)*2+D*2+chr(10)+'R=T/C'+chr(10)+D*2+chr(10); o=m._fix_glm_markdown(t); print('ok' if (D*2 in o and '&#36;5' in o) else 'bad')\""

if [ $fail -ne 0 ]; then
    echo "!!  verification failed — not pushing"
    exit 1
fi

if [ $PUSH -ne 1 ]; then
    echo "==> not pushing (pass --push). Local tags: ${LOCAL}, ${HUB}"
    exit 0
fi

echo "==> pushing ${HUB}"
docker push "$HUB" > "${LOG}.push" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    echo "!!  PUSH FAILED (exit $rc). Last 15 lines:"; tail -15 "${LOG}.push"; exit $rc
fi
grep -o 'digest: sha256:[0-9a-f]*' "${LOG}.push" | tail -1 | sed 's/^/    /'

# --------------------------------------------------------------- cleanup -----
# Delete ONLY the superseded rc tags, by exact name. Never a prune: this is a
# shared machine and other projects' images live in the same daemon.
if [ $KEEP -ne 1 ]; then
    # Matched under BOTH names: if one of the pair was already removed by hand,
    # looking only at the plain name finds nothing and leaves a 7GB orphan
    # behind on a machine other projects share.
    prev=$(docker images --format '{{.Repository}}:{{.Tag}}' \
           | grep -E '^(kaiucsd/)?argus-feder:.*-rc[0-9]+$' \
           | sed 's#^\(kaiucsd/\)\?argus-feder:##' \
           | grep -v "^${VERSION}$" \
           | sort -u \
           | sort -t'c' -k2 -n | tail -1)
    if [ -n "$prev" ]; then
        echo "==> deleting superseded rc ${prev} (both names)"
        docker rmi "argus-feder:${prev}" "kaiucsd/argus-feder:${prev}" >/dev/null 2>&1
        echo "    done"
    fi
fi

echo "==> remaining argus-feder images"
docker images --format '    {{.Repository}}:{{.Tag}}  {{.Size}}' | grep argus-feder | sort -r
