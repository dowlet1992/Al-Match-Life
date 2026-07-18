import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import build_production_readiness_report


def main():
    parser = argparse.ArgumentParser(description="Check production configuration readiness.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_production_readiness_report()
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
