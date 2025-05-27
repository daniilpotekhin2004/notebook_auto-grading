````markdown
# YandexGPT Assignment Grader 🚀

*A multi-agent, explainable, and Streamlit-powered platform for automatic
assessment of Jupyter-notebook programming assignments.*

<div align="center">
  <img src="docs/architecture_flowchart.png" width="640" alt="System architecture – diff parser, dual LLM agents, Excel & Streamlit output"/>
</div>

---

## ✨ Key Features
| Feature | Description |
|---------|-------------|
| **Diff-based Notebook Parsing** | Extracts Q & A pairs by comparing every student notebook to a reference template. |
| **Dual LLM Agents** | *Examiner* assigns an initial 0-5 score & justification; *Reviewer* audits and adjusts for fairness. |
| **Explainable Feedback** | Every score is shipped with a short human-readable comment (JSON-formatted). |
| **One-click Reports** | Saves graded results to Excel/CSV, and (optionally) pushes directly to Google Sheets. |
| **Interactive Dashboard** | Streamlit app for browsing each student’s answers, scores, and comments. |
| **Pluggable Prompts** | Instructors can edit system/user prompts in the UI before launching a run. |
| **Container-ready** | Dockerfile & GitHub Actions for seamless cloud deployment (Render / Fly / GCR / HF Spaces). |

---

## 🖥  Quick Start

```bash
# 1. Clone & install
git clone https://github.com/your-org/yandexgpt-grader.git
cd yandexgpt-grader
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your LLM API key
export OPENAI_API_KEY="sk-..."

# 3A. Grade raw notebooks (narrow mode)
python multiagent_grader_v2.py \
      --dir notebooks/ \
      --template "Домашнее задание 4 (1).ipynb"

# 3B. OR grade a pre-parsed wide Excel table
python multiagent_grader_v2.py --wide parsed_answers.xlsx

# 4. Peek at the results
streamlit run streamlit_dashboard.py -- --graded graded_results.xlsx
````

> **Need Google Sheets export?**
> Run the dashboard, click **Export to Sheets**, sign in with Google, and your grades appear online.

---

## 📂 Repository Layout

```
.
├── m5.py                     # diff-based notebook parser
├── multiagent_grader_v2.py   # CLI entrypoint, dual LLM logic
├── streamlit_dashboard.py    # interactive dashboard
├── Dockerfile                # container spec
├── requirements.txt
└── docs/
    └── architecture_flowchart.png
```

---

## 🔌 Configuration

| Variable         | Purpose                                                              |
| ---------------- | -------------------------------------------------------------------- |
| `OPENAI_API_KEY` | Key for GPT-4-series (or set `YANDEX_GPT_KEY` if you swap providers) |
| `OPENAI_MODEL`   | Override default model (e.g. `gpt-4o-mini`)                          |
| `MAX_TOKENS`     | Hard limit for a single agent call                                   |

All settings may also be passed via CLI flags – see `python multiagent_grader_v2.py -h`.

---

## 🛠  Roadmap

1. **Enhanced UI** – file uploads, real-time progress, editable prompts.
2. **Global Hosting** – automated CI/CD to Hugging Face Spaces & Render.
3. **Deeper LMS integration** – Moodle & Canvas grade-book push.

See the full *Plan for Future Work* in `docs/roadmap.md`.

---

## 🤝 Contributing

1. Fork the repo & create a feature branch.
2. Write tests (`pytest -q`).
3. Open a PR describing **what** and **why**.
4. Respect the [code of conduct](CODE_OF_CONDUCT.md).

We love issues & feature suggestions!

---

## 📄 License

Released under the **MIT License** – see `LICENSE`.

---

## 📚 Cite Us

If this tool helped your course or research, please cite:

```
@misc{potekhin2025grader,
  author       = {Daniil Potekhin and Dmitry Pavlov},
  title        = {YandexGPT for Student Assignment Evaluation},
  year         = {2025},
  howpublished = {\url{https://github.com/your-org/yandexgpt-grader}}
}
```

Happy grading! 🎓

```
```
