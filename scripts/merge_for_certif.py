"""Assemble le notebook de rendu : le cas d'usage suivi du journal de bord.

Usage : python -m scripts.merge_for_certif
"""
import json
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CAS_USAGE = RACINE / "cas_usage_bank_marketing.ipynb"
JOURNAL = RACINE / "journal-de-bord.ipynb"
RENDU = RACINE / "rendu_certif.ipynb"


def source(cellule):
    return "".join(cellule["source"])


def cellules_du_journal(journal):
    debut = next(i for i, c in enumerate(journal["cells"]) if source(c).startswith("## 📅"))
    return [
        {**c, "id": c.get("id") or uuid.uuid4().hex[:16]}
        for c in journal["cells"][debut:]
        if source(c).strip()
    ]


def main():
    cas_usage = json.loads(CAS_USAGE.read_text(encoding="utf-8"))
    journal = json.loads(JOURNAL.read_text(encoding="utf-8"))
    titre = {"cell_type": "markdown", "id": "journal-de-bord", "metadata": {}, "source": ["---\n", "# Journal de bord"]}
    rendu = {**cas_usage, "cells": cas_usage["cells"] + [titre] + cellules_du_journal(journal)}
    RENDU.write_text(json.dumps(rendu, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{RENDU.name} : {len(rendu['cells'])} cellules, dont {len(rendu['cells']) - len(cas_usage['cells'])} du journal")


if __name__ == "__main__":
    main()
