"""Measure recall self-echo: how much of each injected <memory-context> block repeats text already
present earlier in the same session's transcript. Read-only on state.db."""
import re, sqlite3, statistics as st, sys

db = sqlite3.connect("file:%s?mode=ro" % next(
    (a for a in sys.argv[1:] if not a.startswith("--")), "/home/foil/.hermes/state.db"), uri=True)
ITEM = re.compile(r"^\[#\d+ · [^\]]*\] ?", re.M)
PROBE = 160  # chars of an item body used as its fingerprint

def items(block):
    parts = ITEM.split(block)
    heads = ITEM.findall(block)
    return [(h, b.strip()) for h, b in zip(heads, parts[1:])]

sessions = [r[0] for r in db.execute(
    "select distinct session_id from messages where api_content like '%<memory-context>%'")]
LIVE_ONLY = "--live" in sys.argv   # count only messages not since compacted out of context
per_turn = []          # (block_chars, echo_chars, n_items, n_echo)
by_label = {}          # label kind -> [items, echoed]
for sid in sessions:
    seen = ""          # everything visible in context before this turn (raw content, not api_content)
    for role, content, api, compacted in db.execute(
            "select role, content, api_content, compacted from messages where session_id=? order by id",
            (sid,)):
        content = content or ""
        if role == "user" and api and "<memory-context>" in api:
            m = re.search(r"<memory-context>(.*?)</memory-context>", api, re.S)
            block = m.group(1)
            its = items(block)
            echo = []
            for h, b in its:
                kind = "own-session" if sid.lower().replace("_", "-") in h.lower().replace("_", "-") \
                    else ("other-session" if "session." in h else "default")
                hit = len(b) >= 40 and b[:PROBE] in seen
                k = by_label.setdefault(kind, [0, 0]); k[0] += 1; k[1] += hit
                if hit: echo.append(b)
            per_turn.append((len(block), sum(len(b) for b in echo), len(its), len(echo)))
        if not (LIVE_ONLY and compacted):
            seen += "\n" + content

bc = [p[0] for p in per_turn]; ec = [p[1] for p in per_turn]
ni = sum(p[2] for p in per_turn); ne = sum(p[3] for p in per_turn)
print(f"turns with recall: {len(per_turn)} across {len(sessions)} sessions")
print(f"block chars: median {st.median(bc):.0f}, mean {st.mean(bc):.0f}, total {sum(bc)}")
print(f"items: {ni}; already in this session's transcript: {ne} ({100*ne/max(ni,1):.1f}%)")
print(f"echo chars: total {sum(ec)} = {100*sum(ec)/max(sum(bc),1):.1f}% of all recall chars; "
      f"median per turn {st.median(ec):.0f}")
for k, (n, e) in sorted(by_label.items()):
    print(f"  {k}: {e}/{n} echoed")
