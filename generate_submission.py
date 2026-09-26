"""
Generate canonical submission.jsonl (30 test pairs)
===================================================

Reads test_pairs.json, composes messages using composer.py,
and outputs formatted submission.jsonl.
"""

from __future__ import annotations
import json
from pathlib import Path
from composer import compose

def main():
    base_dir = Path(__file__).parent
    dataset_dir = base_dir / "dataset"
    test_pairs_path = dataset_dir / "test_pairs.json"
    
    if not test_pairs_path.exists():
        print(f"Error: {test_pairs_path} not found")
        return

    with open(test_pairs_path, "r", encoding="utf-8") as f:
        pairs = json.load(f).get("pairs", [])

    print(f"Processing {len(pairs)} test pairs...")
    output_lines = []

    for item in pairs:
        test_id = item["test_id"]
        tid = item["trigger_id"]
        mid = item["merchant_id"]
        cid = item.get("customer_id")

        trg_path = dataset_dir / "triggers" / f"{tid}.json"
        merch_path = dataset_dir / "merchants" / f"{mid}.json"

        with open(trg_path, "r", encoding="utf-8") as f:
            trigger = json.load(f)
        with open(merch_path, "r", encoding="utf-8") as f:
            merchant = json.load(f)

        cat_slug = merchant.get("category_slug")
        cat_path = dataset_dir / "categories" / f"{cat_slug}.json"
        with open(cat_path, "r", encoding="utf-8") as f:
            category = json.load(f)

        customer = None
        if cid:
            cust_path = dataset_dir / "customers" / f"{cid}.json"
            if cust_path.exists():
                with open(cust_path, "r", encoding="utf-8") as f:
                    customer = json.load(f)

        composed = compose(category, merchant, trigger, customer)

        record = {
            "test_id": test_id,
            "body": composed["body"],
            "cta": composed["cta"],
            "send_as": composed["send_as"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"]
        }
        output_lines.append(json.dumps(record, ensure_ascii=False))

    out_file = base_dir / "submission.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"Successfully generated {len(output_lines)} lines in {out_file}")

if __name__ == "__main__":
    main()
