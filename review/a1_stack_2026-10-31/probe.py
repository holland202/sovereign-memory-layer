"""A1-STACK probe: one outcome line for json.loads on D-deep nesting in this process."""
import json, sys
D = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
try:
    json.loads("[" * D + "]" * D)
    print(f"python={sys.version.split()[0]} D={D} OUTCOME=OK")
except RecursionError:
    print(f"python={sys.version.split()[0]} D={D} OUTCOME=RecursionError")
except Exception as e:  # noqa: BLE001
    print(f"python={sys.version.split()[0]} D={D} OUTCOME=other:{type(e).__name__}")
