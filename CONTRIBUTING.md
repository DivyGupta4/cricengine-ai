# Contributing to CricEngine AI

Thank you for your interest in contributing to **CricEngine AI**! We welcome contributions from data engineers, sports analytics researchers, and machine learning practitioners.

---

## 1. Code of Conduct & Core Engineering Principles

1. **Zero Data Fabrication:** We value empirical correctness over superficial completeness. Never synthesize fake match records or impute synthetic ball-by-ball scorecards.
2. **Strict Point-in-Time Integrity:** Never introduce forward-looking features into feature engineering, player ratings, or predictive models. Any pull request introducing temporal data leakage will be rejected.
3. **Reproducibility First:** All pipelines, schemas, and queries must be fully verifiable against canonical database checkpoints and manifests.

---

## 2. Setting Up Your Development Environment

### Prerequisites
- macOS or Linux
- Python 3.12+
- Git and Git LFS

### Step-by-Step Setup
1. **Fork and Clone the Repository:**
   ```bash
   git clone https://github.com/DivyGupta4/cricengine-ai.git
   cd cricengine-ai
   ```

2. **Create and Activate Virtual Environment:**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Download the Canonical Database and Feature Stores:**
   ```bash
   # Download the 3NF DuckDB database (383 MB)
   python -m src.data.download_dataset --component database

   # (Optional) Download Feature Store, Ratings, and Predictions
   python -m src.data.download_dataset --component all
   ```

5. **Verify Dataset Integrity:**
   ```bash
   python -m src.data.download_dataset --component database --verify-only
   ```

---

## 3. Running the Test Suite

Because DuckDB scans multi-file partitioned Parquet directories, ensure your operating system's open-file limit is raised before running tests:

```bash
# Raise file descriptor limit and run test suite
ulimit -n 4096 && pytest tests/ -v
```

---

## 4. Development & Contribution Workflow

1. **Create a Feature Branch:**
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Follow Code Quality Standards:**
   - Adhere to **PEP 8** style guidelines.
   - Include clear type annotations and docstrings.
   - Do not commit binary databases, huge Parquet outputs, or personal `.env` files.
3. **Verify Documentation & Schemas:**
   - If adding or modifying relational tables or feature definitions, update `schemas/`, `DATA_DICTIONARY.md`, and `DATA_LINEAGE.md`.
4. **Submit a Pull Request:**
   - Open a PR against the `main` branch.
   - Provide a clear summary of changes, rationale, and reproduction evidence.

---

## 5. Licensing and Intellectual Property

By submitting a pull request to CricEngine AI:
- You agree that your contributed code is licensed under the **MIT License**.
- You agree that any derived dataset structures respect the **Open Data Commons ODbL v1.0** and **CC BY-SA 4.0** attribution terms of the underlying Cricsheet data.
