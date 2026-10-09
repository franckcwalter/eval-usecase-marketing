"""Assemble le notebook de rendu : le cas d'usage suivi du journal de bord.

Usage : python -m scripts.merge_for_certif
"""
import json
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CAS_USAGE = RACINE / "cas_usage_bank_marketing.ipynb"
JOURNAL = RACINE / "journal-de-bord.ipynb"
RENDU = RACINE / "rendu" / "rendu_certif.ipynb"


def source(cellule):
    return "".join(cellule["source"])


def depuis_rendu(cellule):
    # Le rendu est un niveau plus bas que les notebooks sources : les images de assets/ remontent d'un dossier.
    if cellule["cell_type"] != "markdown":
        return cellule
    return {**cellule, "source": [ligne.replace("](assets/", "](../assets/") for ligne in cellule["source"]]}


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
    cellules = cas_usage["cells"] + [titre] + cellules_du_journal(journal)
    rendu = {**cas_usage, "cells": [depuis_rendu(c) for c in cellules]}
    RENDU.write_text(json.dumps(rendu, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{RENDU.name} : {len(rendu['cells'])} cellules, dont {len(rendu['cells']) - len(cas_usage['cells'])} du journal")


if __name__ == "__main__":
    main()
