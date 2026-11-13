# Claude Code skills for this repository

Claude Code loads every folder here as a project skill (a `SKILL.md` with instructions, plus references and
scripts) and uses one when a task matches its description. They are copied from open-source collections, each
with its license file kept in its folder. Each was reviewed before adding: its scripts run locally, and none
calls a network service unless you give it a URL (`seo-audit --url`) or runs `claude` itself (`skill-creator`).

| Skill | Use it for | From | License |
|---|---|---|---|
| `exploratory-data-analysis` | First look at a data file: profiles, missingness, leakage and outlier audits | K-Dense | MIT |
| `statistical-analysis` | Choosing and reporting tests: assumptions, effect sizes, power | K-Dense | MIT |
| `statistical-power` | Sample size and power calculations | K-Dense | MIT |
| `experimental-design` | Designing experiments and A/B tests before collecting data | K-Dense | MIT |
| `statsmodels` | Regression, time series, GLMs with proper inference | K-Dense | MIT |
| `pymc` | Bayesian models | K-Dense | MIT |
| `scikit-learn` | Classical machine learning pipelines and validation | K-Dense | MIT |
| `shap` | Explaining model predictions | K-Dense | MIT |
| `scikit-survival` | Survival / time-to-event models (churn, failures) | K-Dense | MIT |
| `polars` | Fast DataFrame work on large tables | K-Dense | MIT |
| `dask` | Out-of-core and parallel processing of big data | K-Dense | MIT |
| `geopandas` | Maps and spatial joins (provinces, ports, hotspots) | K-Dense | MIT |
| `networkx` | Graphs and networks (e.g. anime franchise links, shipping routes) | K-Dense | MIT |
| `simpy` | Discrete-event simulation (queues, supply chains, operations) | K-Dense | MIT |
| `pymoo` | Multi-objective optimization | K-Dense | MIT |
| `matplotlib` | Publication-quality static charts | K-Dense | MIT |
| `seaborn` | Statistical charts | K-Dense | MIT |
| `scientific-visualization` | Figure design: color palettes, layouts, accessibility | K-Dense | MIT |
| `process-mapper` | Mapping a business process, cycle times and bottlenecks | alirezarezvani | MIT |
| `capacity-planner` | Staffing and capacity with queueing (Erlang C) models | alirezarezvani | MIT |
| `seo-audit` | Why a page does not rank: technical and on-page SEO | alirezarezvani | MIT |
| `systematic-debugging` | Finding the root cause of a bug before fixing it | obra/superpowers | MIT |
| `test-driven-development` | Writing the failing test first | obra/superpowers | MIT |
| `verification-before-completion` | Running checks before claiming work is done | obra/superpowers | MIT |
| `receiving-code-review` | Weighing review feedback instead of applying it blindly | obra/superpowers | MIT |
| `webapp-testing` | Testing web pages with Playwright (e.g. the Vision Lab site) | Anthropic | Apache 2.0 |
| `skill-creator` | Writing and testing new skills for this repo | Anthropic | Apache 2.0 |

## Sources

| Collection | Repository | Commit copied |
|---|---|---|
| K-Dense | https://github.com/K-Dense-AI/claude-scientific-skills | `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5` |
| obra/superpowers | https://github.com/obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` |
| Anthropic | https://github.com/anthropics/skills | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` |
| alirezarezvani | https://github.com/alirezarezvani/claude-skills | `08cd8a9fc86cc370e2c0d448e8171fbcfdbc5a30` |

Changes from upstream: in the four obra/superpowers skills, references written as `superpowers:<skill>` were
shortened to the skill's plain name (they are project skills here), and one reference to a skill not copied
here (`writing-skills`) now names its source. Nothing else was changed.

Not included on purpose: Anthropic's `docx`, `pdf`, `pptx` and `xlsx` skills (source-available, not open
source) and superpowers' `brainstorming` (its description makes it run before any creative task).

To update a skill, copy its folder again from the repository above and update the commit in this table.
