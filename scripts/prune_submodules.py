"""Drop board.toml submodule entries that the checked-out Aloha tree lacks.

board.toml's [firmware] submodules list was written for one revision of the
Project Aloha tree. Other revisions rename or drop submodules entirely
(2412.74 has no Platforms/CranePkg and no MbedTlsPkg/mbedtls), and
`git submodule update --init -- <paths>` aborts on the first path git does not
know, so the build dies before EDK II ever starts.

usage: python3 prune_submodules.py <uefi_tree_root> [board.toml]
"""
import re
import sys
from pathlib import Path

uefi = Path(sys.argv[1] if len(sys.argv) > 1 else "uefi")
board = Path(sys.argv[2] if len(sys.argv) > 2 else "board.toml")

gitmodules = uefi / ".gitmodules"
known = set()
if gitmodules.is_file():
    known = set(re.findall(r"^\s*path\s*=\s*(\S+)\s*$", gitmodules.read_text(encoding="utf-8"), re.M))
print("submodules declared by the tree: %d" % len(known))

text = board.read_text(encoding="utf-8")
m = re.search(r"^submodules\s*=\s*\[(.*?)^\]", text, re.S | re.M)
if not m:
    print("  no [firmware] submodules block in board.toml - nothing to do")
    sys.exit(0)

entries = re.findall(r'"([^"]+)"', m.group(1))
kept = [e for e in entries if e in known]
dropped = [e for e in entries if e not in known]

if dropped:
    body = "\n".join('  "%s",' % e for e in kept)
    text = text[:m.start()] + "submodules = [\n" + body + "\n]" + text[m.end():]
    board.write_text(text, encoding="utf-8")

print("  kept   : %s" % ", ".join(kept))
print("  dropped: %s" % (", ".join(dropped) or "(none)"))
