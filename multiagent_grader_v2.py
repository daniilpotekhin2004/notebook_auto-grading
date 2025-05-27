#!/usr/bin/env python3
"""
multiagent_grader_v2.py  — расширенная версия
------------------------------------------------

Теперь поддерживает **два сценария**:
1. Grading набора *.ipynb* (как раньше).
2. Grading «широкой» Excel‑таблицы, в которой ответы уже распарсены и расположены
   столбцами `Вопрос 1`, `Ответ 1`, … `Вопрос N`, `Ответ N`.

Дополнительно добавлена функция генерации файла **Streamlit‑дашборда** —
`streamlit_dashboard.py` — для интерактивного просмотра результатов.
Запускается командой:

```bash
streamlit run streamlit_dashboard.py -- --graded graded_results.xlsx
```

Главные новшества
-----------------
* `grade_wide_excel(...)`  — оценка Excel‑таблицы указанного формата.
* Новый CLI‑флаг `--wide <xlsx>`  (или `-w`) — путь к широкой таблице.
* `--generate-dashboard`   — записать готовый файл `streamlit_dashboard.py`.
* В результирующий Excel добавляются пары столбцов `Оценка i`, `Комментарий i`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import pandas as pd
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

# ---------------------------------------------------------------------------
#  Импорт утилиты diff‑парсинга (для .ipynb режима)
# ---------------------------------------------------------------------------
try:
    from m5 import parse_student_notebook_diff
except ImportError:
    parse_student_notebook_diff = None  # not needed for wide‑table mode

# ---------------------------------------------------------------------------
#  Конфигурация
# ---------------------------------------------------------------------------
DEFAULT_MODEL  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPLATE_NOTEBOOK = "Домашнее задание 4 (1).ipynb"
OUTPUT_EXCEL  = "graded_results.xlsx"
OUTPUT_CSV    = "graded_results.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ---------------------------------------------------------------------------
#  Prompt templates
# ---------------------------------------------------------------------------
SYSTEM_EVAL = (
    "You are an assistant for a university course. "
    "Evaluate the student's answer on a 0‑5 scale and provide a short justification. "
    "Return JSON: {\"score\": int, \"comment\": str}"
)
SYSTEM_REVIEW = (
    "You are a second reviewer who double‑checks grading fairness. "
    "If the initial score is reasonable keep it, otherwise adjust. "
    "Return JSON: {\"score\": int, \"comment\": str}"
)

# ---------------------------------------------------------------------------
#  OpenAI helper
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Agent:
    system_prompt: str
    client: OpenAI
    model: str = DEFAULT_MODEL
    temperature: float = 0.2

    @retry(stop=stop_after_attempt(4), wait=wait_random_exponential(multiplier=1, max=20))
    def __call__(self, messages: Sequence[dict]) -> dict:
        """LLM call with strict‑JSON mode."""
        if self.client.api_key is None:
            return {"score": random.randint(0, 5), "comment": "mock (offline)"}

        full = [{"role": "system", "content": self.system_prompt}, *messages]
        res = self.client.chat.completions.create(
            model=self.model,
            messages=full,
            response_format={"type": "json_object"},
            temperature=self.temperature,
            timeout=30,
        )
        return json.loads(res.choices[0].message.content)

# ---------------------------------------------------------------------------
#  Универсальная оценка одного вопроса
# ---------------------------------------------------------------------------

def evaluate(question: str, answer: str | None, examiner: Agent, reviewer: Agent) -> Tuple[int, str]:
    ans_text = answer or "[пусто]"
    # Первичная оценка
    first = examiner([
        {"role": "user", "content": f"ЗАДАНИЕ:\n{question}\n\nОТВЕТ СТУДЕНТА:\n{ans_text}"}
    ])
    # Рецензия
    final = reviewer([
        {"role": "user", "content": (
            f"ЗАДАНИЕ:\n{question}\n\nОТВЕТ СТУДЕНТА:\n{ans_text}\n\n"
            f"ПЕРВИЧНАЯ ОЦЕНКА:\n{json.dumps(first, ensure_ascii=False)}"
        )}
    ])
    return int(final["score"]), str(final["comment"])

# ---------------------------------------------------------------------------
#  Grading «узкого» (ipynb) формата
# ---------------------------------------------------------------------------

def grade_notebook(template: Path, student: Path, examiner: Agent, reviewer: Agent) -> pd.DataFrame:
    if parse_student_notebook_diff is None:
        raise RuntimeError("m5.parse_student_notebook_diff недоступен — ipynb режим невозможен.")
    qs, ans = parse_student_notebook_diff(template, student)
    rows = []
    for q, a in zip(qs, ans):
        score, comment = evaluate(q, a, examiner, reviewer)
        rows.append({"Вопрос": q, "Ответ": a, "Балл": score, "Комментарий": comment})
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
#  Grading широкой Excel‑таблицы
# ---------------------------------------------------------------------------

def _collect_q_a_columns(df: pd.DataFrame) -> List[Tuple[str, str]]:
    """Возвращает упорядоченный список пар («Вопрос i», «Ответ i»)."""
    pairs = []
    for col in df.columns:
        if col.startswith("Вопрос "):
            idx = col.split(" ")[1]
            ans_col = f"Ответ {idx}"
            if ans_col in df.columns:
                pairs.append((col, ans_col))
    pairs.sort(key=lambda p: int(p[0].split()[1]))
    return pairs


def grade_wide_excel(path: Path, examiner: Agent, reviewer: Agent, out_path: Path | None = None) -> Path:
    """Читает Excel с широкой схемой, дописывает оценки, сохраняет новый файл."""
    df = pd.read_excel(path)
    qa_cols = _collect_q_a_columns(df)

    for q_col, a_col in qa_cols:
        score_col = f"Оценка {q_col.split()[1]}"
        comm_col  = f"Комментарий {q_col.split()[1]}"
        scores, comments = [], []
        for q, a in zip(df[q_col], df[a_col]):
            sc, cm = evaluate(str(q), str(a), examiner, reviewer)
            scores.append(sc)
            comments.append(cm)
        df[score_col] = scores
        df[comm_col]  = comments

    target = out_path or path.with_stem(path.stem + "_graded")
    df.to_excel(target, index=False)
    logging.info("Graded wide table saved → %s", target)
    return target

# ---------------------------------------------------------------------------
#  Streamlit dashboard generator
# ---------------------------------------------------------------------------
STREAMLIT_CODE = """"""
import argparse
from pathlib import Path
import pandas as pd
import streamlit as st

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--graded", type=Path, default="graded_results.xlsx")
args, _ = parser.parse_known_args()

@st.cache_data
def load_df(p: Path):
    return pd.read_excel(p)

df = load_df(args.graded)
file_list = df["Файл"].unique().tolist()

st.sidebar.title("Выберите работу")
selected = st.sidebar.selectbox("Студент", file_list)

st.title(f"Результаты: {selected}")
sub = df[df["Файл"] == selected].reset_index(drop=True)

qa_cols = [c for c in sub.columns if c.startswith("Вопрос ")]
for col in qa_cols:
    idx = col.split()[1]
    q = sub.at[0, col]
    a = sub.at[0, f"Ответ {idx}"]
    sc = sub.at[0, f"Оценка {idx}"]
    cm = sub.at[0, f"Комментарий {idx}"]
    with st.expander(f"Вопрос {idx} • Балл: {sc}"):
        st.markdown(f"**Вопрос:**\n{q}")
        st.markdown(f"**Ответ:**\n{a}")
        st.info(cm)
""""""


def write_streamlit_dashboard(filename: str = "streamlit_dashboard.py") -> None:
    Path(filename).write_text(STREAMLIT_CODE, encoding="utf-8")
    logging.info("Streamlit dashboard script written → %s", filename)

# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="multiagent_grader_v2",
        description="Grade student work via OpenAI LLMs (ipynb or wide Excel table)",
    )
    p.add_argument("--dir", "-d", type=Path, default=Path("."), help="Directory with .ipynb files")
    p.add_argument("--template", "-t", type=Path, default=Path(TEMPLATE_NOTEBOOK), help="Template .ipynb with tasks")
    p.add_argument("--wide", "-w", type=Path, help="Path to wide‑format Excel to grade")
    p.add_argument("--model", "-m", type=str, default=DEFAULT_MODEL, help="OpenAI model id")
    p.add_argument("--generate-dashboard", action="store_true", help="Write streamlit_dashboard.py and exit")
    return p

# ---------------------------------------------------------------------------
#  Main entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    args = build_arg_parser().parse_args()

    if args.generate_dashboard:
        write_streamlit_dashboard()
        return

    client = OpenAI()
    examiner = Agent(SYSTEM_EVAL, client=client, model=args.model)
    reviewer = Agent(SYSTEM_REVIEW, client=client, model=args.model)

    if args.wide:  # ---------------- wide table mode ----------------
        grade_wide_excel(args.wide, examiner, reviewer)
        return

    # ---------------- ipynb mode ----------------
    student_files = [f for f in args.dir.glob("*.ipynb") if f.name != args.template.name]
    if not student_files:
        logging.error("No student .ipynb files found in %s", args.dir)
        return

    all_dfs: List[pd.DataFrame] = []
    for nb in student_files:
        logging.info("Grading %s", nb.name)
        df_one = grade_notebook(args.template, nb, examiner, reviewer)
        df_one.insert(0, "Файл", nb.name)
        all_dfs.append(df_one)

    df_total = pd.concat(all_dfs, ignore_index=True)
    df_total.to_excel(OUTPUT_EXCEL, index=False)
    df_total.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logging.info("Results saved → %s / %s", OUTPUT_EXCEL, OUTPUT_CSV)


if __name__ == "__main__":
    main()
