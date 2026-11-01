"""Charts and a Markdown summary from a benchmark run.

Usage: python -m bench.report bench/results/<run-folder>
"""

from __future__ import annotations

import csv
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Validated categorical slots 1 and 2 (light surface), text and grid tokens.
WITHOUT, WITH = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
ARMS = [("without_tool", "Without the tool", WITHOUT), ("with_tool", "With the tool", WITH)]


def _load(run_dir: Path) -> Dict[str, Dict[str, dict]]:
    rows = list(csv.DictReader(open(run_dir / "summary.csv", encoding="utf-8")))
    labels = {t["id"]: t["label"] for t in json.loads(
        (Path(__file__).parent / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
    acc: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        acc[r["task"]][r["arm"]].append(r)
    out: Dict[str, Dict[str, dict]] = {}
    for task, arms in acc.items():
        out[task] = {"label": labels.get(task, task)}
        for arm, rs in arms.items():
            out[task][arm] = {
                "total": mean(int(r["total_tokens"]) for r in rs),
                "model": mean(int(r["model_tokens"]) for r in rs),
                "overhead": mean(int(r["overhead_tokens"]) for r in rs),
                "turns": mean(int(r["turns"]) for r in rs),
                "pass_rate": mean(1.0 if r["passed"] == "True" else 0.0 for r in rs),
            }
    return out


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _bars(data, metric: str, title: str, xlabel: str, path: Path, note: str, fmt: str) -> None:
    tasks = list(data)
    fig, ax = plt.subplots(figsize=(9, 0.75 * len(tasks) + 2.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    h = 0.36
    top = max(data[t][a][metric] for t in tasks for a, _, _ in ARMS if a in data[t]) or 1
    for i, (arm, label, color) in enumerate(ARMS):
        ys = [k - (h / 2 + 0.02) + i * (h + 0.04) for k in range(len(tasks))]
        vals = [data[t].get(arm, {}).get(metric, 0) for t in tasks]
        ax.barh(ys, vals, height=h, color=color, label=label)
        for y, v in zip(ys, vals):
            ax.text(v + top * 0.01, y, format(v, fmt), va="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([data[t]["label"] for t in tasks], color=INK, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, top * 1.15)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    fig.text(0.02, 0.985, title, ha="left", va="top", fontsize=12, color=INK, fontweight="bold")
    fig.text(0.02, 0.945, textwrap.fill(note, 120), ha="left", va="top", fontsize=8, color=INK2)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.02, 0.89), ncol=2, frameon=False,
               fontsize=8.5, labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def make_report(run_dir: Path, dry_run: bool = False) -> str:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")) if (run_dir / "meta.json").exists() else {}
    dry_run = dry_run or meta.get("dry_run", False)
    data = _load(run_dir)
    tot_a = sum(d["without_tool"]["total"] for d in data.values() if "without_tool" in d)
    tot_b = sum(d["with_tool"]["total"] for d in data.values() if "with_tool" in d)
    change = (tot_b - tot_a) / tot_a * 100 if tot_a else 0.0
    direction = "fewer" if change < 0 else "more"
    finding = f"With the tool: {abs(change):.0f}% {direction} tokens in total across {len(data)} tasks"
    model = meta.get("model", "?")
    note = (("DRY RUN with a fake model: NOT real measurements. " if dry_run else "")
            + f"Model {model}. Tokens to reach an acceptable answer, incl. re-sent history, thinking and tool overhead.")

    _bars(data, "total", finding, "Total tokens (average per run)", run_dir / "tokens_by_task.png", note, ".0f")
    _bars(data, "turns", "Turns needed to reach an acceptable answer", "Turns (average per run)",
          run_dir / "turns_by_task.png", note, ".1f")

    lines = [f"# Benchmark results{' (DRY RUN, not real)' if dry_run else ''}", "",
             f"Model: `{model}` · max turns: {meta.get('max_turns')} · repeats: {meta.get('repeats')} · "
             f"run at {meta.get('run_at', '?')}", "", f"**{finding}.**", "",
             "| Task | Tokens without | Tokens with (overhead) | Turns without | Turns with | Pass without | Pass with |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for t, d in data.items():
        a, b = d.get("without_tool", {}), d.get("with_tool", {})
        lines.append(f"| {d['label']} | {a.get('total', 0):.0f} | {b.get('total', 0):.0f} ({b.get('overhead', 0):.0f}) "
                     f"| {a.get('turns', 0):.1f} | {b.get('turns', 0):.1f} | {a.get('pass_rate', 0):.0%} "
                     f"| {b.get('pass_rate', 0):.0%} |")
    lines += ["", "Acceptance checks are mechanical (length, format, item count, required words). "
              "Read a sample of transcripts.json before presenting quality claims."]
    text = "\n".join(lines) + "\n"
    (run_dir / "summary.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(make_report(Path(sys.argv[1])))
