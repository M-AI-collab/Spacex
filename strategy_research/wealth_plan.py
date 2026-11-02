"""Part 3: realistic path to $30,000 of trading profit per year.

$30k/year of profit needs capital = 30,000 / annual return. This computes how long it takes to get
there from $1,000 plus monthly contributions, under return assumptions taken from the
out-of-sample results of Part 1 (not from in-sample backtests).
"""

from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "results"
START = 1_000.0
TARGET_PROFIT = 30_000.0
USD_AED = 3.6725
RETURNS = {
    "10%/yr (stock index long-run, or bot in a weak period)": 0.10,
    "15%/yr (bot, wide 10-coin universe, out-of-sample)": 0.15,
    "25%/yr (bot, mid-case of out-of-sample results)": 0.25,
    "35%/yr (bot, optimistic: matches best out-of-sample run)": 0.35,
}
CONTRIBUTIONS = [250, 500, 1_000, 2_000, 3_000]


def months_to_goal(monthly: float, annual_r: float, cap_months: int = 600):
    r = (1 + annual_r) ** (1 / 12) - 1
    need = TARGET_PROFIT / annual_r
    bal, invested = START, START
    for m in range(1, cap_months + 1):
        bal = bal * (1 + r) + monthly
        invested += monthly
        if bal >= need:
            return m, invested, bal
    return None, invested, bal


def main():
    L = ["# Part 3: a realistic path to $30,000 a year of trading profit", "",
         "Annual profit = capital x return, so **$30k/year needs capital of $30,000 / return**:", "",
         "| Expected return | Capital needed for $30k/yr profit |", "|---|---|"]
    for name, r in RETURNS.items():
        L.append(f"| {name} | ${TARGET_PROFIT / r:,.0f} (AED {TARGET_PROFIT / r * USD_AED:,.0f}) |")
    L += ["", "## Time to reach it from $1,000 + monthly contributions", "",
          "Years until the account is big enough to make $30k/yr (total you put in, in brackets):", "",
          "| Monthly contribution | " + " | ".join(n.split(" (")[0] for n in RETURNS) + " |",
          "|---" * (len(RETURNS) + 1) + "|"]
    for c in CONTRIBUTIONS:
        cells = []
        for r in RETURNS.values():
            m, invested, _ = months_to_goal(c, r)
            cells.append(f"{m / 12:.1f} yrs (${invested:,.0f})" if m else "50+ yrs")
        L.append(f"| ${c:,}/month (AED {c * USD_AED:,.0f}) | " + " | ".join(cells) + " |")
    L += ["", "Assumes returns are earned smoothly every year. Real returns arrive in lumps, with -40% to -60% "
          "drawdowns along the way (see Part 1), so treat these as averages, not promises.", ""]
    (OUT / "WEALTH_PLAN.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
