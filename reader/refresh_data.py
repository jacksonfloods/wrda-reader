"""refresh_data.py -- copy rebuilt structure files into the reader's data folder.

Run:  python refresh_data.py FOLDER_WITH_STRUCTURE_FILES

The data folder beside this file holds the acts the reader shows when it is started with no folder
(that is what the public site shows). After the acts are rebuilt, this copies every *.structure.json
that is new or has changed, and says what it did. A file that is in the data folder but no longer in
FOLDER is reported and left alone.
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SUFFIX = ".structure.json"


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__)
        return 1
    src = sys.argv[1]
    names = sorted(n for n in os.listdir(src) if n.endswith(SUFFIX) and not n.startswith("."))
    if not names:
        print(f"No files ending in {SUFFIX} in {src}")
        return 1
    os.makedirs(DATA, exist_ok=True)
    counts = {"new": 0, "changed": 0, "same": 0}
    for n in names:
        a, b = os.path.join(src, n), os.path.join(DATA, n)
        what = "new" if not os.path.exists(b) else ("same" if sha(a) == sha(b) else "changed")
        counts[what] += 1
        if what != "same":
            shutil.copyfile(a, b)
            print(f"{what:8}{n}")
    for n in sorted(os.listdir(DATA)):
        if n.endswith(SUFFIX) and n not in names:
            print(f"left alone: {n} is in the data folder but not in {src}")
    print(f"{len(names)} files: {counts['new']} new, {counts['changed']} changed, {counts['same']} already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
