import os
import re
import sys
from pathlib import Path

# pip index version boto3
# 1.23.6-0
# 1.22.13-0
# 1.21.46-0

name = "boto3"
MAJOR = 1
MINOR = 21
MICRO = 1, 22

reqfile = Path("_test.in")

for micro in range(MICRO[1], MICRO[0] - 1, -1):
    version = f"{MAJOR}.{MINOR}.{micro}"
    constraint = f"{name}=={version}"

    print("TESTING", f"{constraint}...")

    # replace
    reqfile.write_text(re.sub(r"==([\d\.]+)", f"=={version}", reqfile.read_text()))

    # compile & check
    if os.system(f"make reqs upgrade={constraint}") == os.EX_OK:
        print(f"{constraint} PASSED")
        ans = input("Continue? (y/[n])") or "n"
        if ans == "n":
            sys.exit(os.EX_OK)
    else:
        print(f"{constraint} ", "FAILED", "-" * 10)
