"""Score the SOP assistant on the test questions in sample_data/test_questions.json.

    python scripts/eval_sop.py                      # local run (uses ./data)
    docker compose exec app python scripts/eval_sop.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import sop  # noqa: E402
from app.db import init_db  # noqa: E402
from app.evaluate import run  # noqa: E402

init_db()
sop.INDEX.rebuild()
res = run(sys.argv[1] if len(sys.argv) > 1 else None) if len(sys.argv) > 1 else run()
for r in res["rows"]:
    mark = "PASS" if r["passed"] else "FAIL"
    print(f"[{mark}] ({r['lang']}) {r['question']}\n       expected={r['expected']} got={r['got']} mode={r['mode']} "
          f"score={r['score']} {r['seconds']}s\n       {str(r['answer'])[:220]!s}\n       sources: {r['sources']}")
print(f"\nModel: {res['model']} (online={res['ai_online']})")
print(f"Answerable questions correct with source: {res['answerable_passed']}/{res['answerable_total']}")
print(f"Out-of-scope questions sent to the lead:  {res['gaps_caught']}/{res['gaps_total']}")
print(f"Hindi / Gujarati questions:              {res['multilingual_passed']}/{res['multilingual_total']}")
