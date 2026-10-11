"""AC-11 golden test set: python -m app.golden yale  (reads golden/<collection>.yaml)."""
import json
import sys
import urllib.request

import yaml

from app.config import settings
from app.services.urls import normalize


def hit(citations: list[dict], expected_url: str, expected_t: int | None, tolerance: int) -> bool:
    want = normalize(expected_url)
    for c in citations:
        if normalize(c["deep_link"].split("#")[0]) != want:
            continue
        if expected_t is None or c["source_type"] == "web":
            return True
        if c["start_s"] - tolerance <= expected_t <= c["end_s"] + tolerance:
            return True
    return False


def main(slug: str) -> int:
    path = settings.golden_dir / f"{slug}.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    tolerance = int(spec.get("tolerance_s", 60))
    cases = [q for q in spec.get("questions", []) if q.get("expected_url") and q["expected_url"] != "TODO"]
    if not cases:
        sys.exit(f"{path}: no questions with an expected_url yet (AJ fills these in)")
    passed = 0
    for q in cases:
        req = urllib.request.Request(f"{settings.api_url}/collections/{slug}/ask", method="POST",
                                     data=json.dumps({"question": q["question"]}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            answer = json.loads(resp.read())
        ok = hit(answer["citations"], q["expected_url"], q.get("expected_t"), tolerance)
        passed += ok
        cited = ", ".join(f"{c['source_title']} {c['label']}" for c in answer["citations"]) or "nothing"
        print(f"{'PASS' if ok else 'FAIL'}  {q['question']}\n      cited: {cited}")
    print(f"\n{passed}/{len(cases)} cite the expected moment (target: at least 80%)")
    return 0 if passed >= 0.8 * len(cases) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.golden <collection>")
    sys.exit(main(sys.argv[1]))
