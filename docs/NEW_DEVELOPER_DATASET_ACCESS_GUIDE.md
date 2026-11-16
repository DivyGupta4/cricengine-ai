# CricEngine AI — New Developer Guide
## Step-by-Step Instructions to Navigate the Repository, Download the Dataset and Get Started

Welcome to **CricEngine AI**.

This guide is designed for developers who are accessing the project for the first time. You do not need prior knowledge of the project architecture to follow it.

By the end, you should be able to:

1. Open and navigate the public GitHub repository.
2. Understand what each important folder contains.
3. Download the complete published dataset.
4. Verify that the downloaded files are intact.
5. Open and query the canonical DuckDB database.
6. Inspect the Feature Store, Rating Store and Predictive Store.
7. Run the available project demo.
8. Start exploring the codebase and contributing.

---

# PART 1 — Understand Where Everything Lives

CricEngine AI uses two primary platforms.

| Platform | What it contains | Link |
|---|---|---|
| GitHub | Source code, scripts, documentation and tests | https://github.com/DivyGupta4/cricengine-ai |
| Hugging Face | Published dataset and downloadable data assets | https://huggingface.co/datasets/divii1304/cricengine-ai-dataset |

**Important distinction:**

- GitHub is where you explore the software and collaborate on the project.
- Hugging Face is where you obtain the published dataset.
- Your computer is where you download and work with the project.

You do not need to manually download individual Parquet files from the Hugging Face website. The project includes a download utility designed to retrieve the dataset components.

## Step 1 — Open the GitHub repository

Open:

https://github.com/DivyGupta4/cricengine-ai

You will land on the repository's main page.

The main sections you should understand are:

| GitHub section | What it means |
|---|---|
| Code | Browse project files and folders |
| Issues | Report bugs or suggest improvements |
| Pull requests | Propose code changes |
| README.md | Main project introduction and documentation |
| requirements.txt | Python dependencies |
| docs/ | Detailed technical documentation |
| src/ | Main application and modelling code |
| etl/ | Data extraction and transformation scripts |
| tests/ | Automated tests |

### What should you read first?

Read these in order:

1. `README.md` — understand what CricEngine AI does.
2. `docs/` — explore the detailed technical documentation.
3. `requirements.txt` — understand the software dependencies.
4. `src/` — explore the implemented engines.
5. `tests/` — understand how project functionality is tested.

Do not start by executing random Python files. First understand the repository structure.

---

# PART 2 — Set Up Your Computer

## Step 2 — Install the prerequisites

The following instructions are intended for macOS and Linux.

You need:

- Python 3.12
- Git
- Git LFS
- A terminal
- An internet connection

### 2.1 Check whether Python is installed

Open Terminal.

On macOS, press:

`Command + Space`

Type:

`Terminal`

Press Enter.

Now type:

```bash
python3 --version
```

You should have Python 3.12 or a compatible version supported by the project.

If Python 3.12 is not installed on macOS and you use Homebrew:

```bash
brew install python@3.12
```

Check again:

```bash
python3.12 --version
```

### 2.2 Check Git

```bash
git --version
```

If Git is missing on macOS, install Apple's command-line developer tools:

```bash
xcode-select --install
```

### 2.3 Install Git LFS

```bash
brew install git-lfs
```

Initialize Git LFS:

```bash
git lfs install
```

Git LFS is used for large files in repositories that track them.

---

# PART 3 — Download the GitHub Repository

## Step 3 — Clone the repository

Choose a folder on your computer where you want to keep the project.

For example, to keep it on your Desktop:

```bash
cd ~/Desktop
```

Now clone the repository:

```bash
git clone https://github.com/DivyGupta4/cricengine-ai.git
```

This downloads the GitHub project.

Enter the downloaded folder:

```bash
cd cricengine-ai
```

You are now inside the project directory.

To confirm your location:

```bash
pwd
```

To see the files:

```bash
ls -la
```

You should see the repository's main files and folders.

**What just happened?**

You downloaded the source code and project documentation. This is not necessarily the same as downloading the complete Hugging Face dataset.

The dataset download is the next step.

---

# PART 4 — Understand the Repository Structure

## Step 4 — Explore the important folders

Run:

```bash
ls
```

The following are the main areas you should understand.

### `src/`

Contains the main project implementation.

Important areas include:

- `src/ratings/` — player rating engine.
- `src/predictive/` — predictive modelling components.
- `src/data/` — dataset download and data-access utilities.

### `etl/`

Contains data engineering and extraction pipelines.

Examples include:

- Data downloading.
- Parsing.
- Canonical database ingestion.
- Feature engineering.

These scripts are generally intended for building or rebuilding data assets. A new developer should not execute them simply to access the published dataset.

### `config/`

Contains configuration files and project settings.

### `tests/`

Contains automated tests for checking project behaviour.

### `docs/`

Contains project documentation, design decisions, technical reports and developer instructions.

### `requirements.txt`

Contains Python packages required by the project.

**Important:** The published dataset is downloaded separately from Hugging Face. Do not assume that every data component is already present after cloning GitHub.

---

# PART 5 — Create Your Python Environment

## Step 5 — Create a virtual environment

Make sure you are inside the `cricengine-ai` folder.

Run:

```bash
python3.12 -m venv .venv
```

This creates an isolated Python environment for the project.

Activate it:

```bash
source .venv/bin/activate
```

Your terminal should now show something similar to:

```text
(.venv) developer@computer cricengine-ai %
```

This means the virtual environment is active.

### Step 5.1 — Upgrade pip

```bash
python -m pip install --upgrade pip
```

### Step 5.2 — Install project dependencies

```bash
pip install -r requirements.txt
```

Wait for the installation to finish.

### Step 5.3 — Check that Python is using the virtual environment

```bash
which python
```

The output should point to:

```text
cricengine-ai/.venv/bin/python
```

You are now ready to use the project.

---

# PART 6 — Download the Complete Dataset

## Step 6 — Open the Hugging Face dataset page

Open:

https://huggingface.co/datasets/divii1304/cricengine-ai-dataset

This is the published CricEngine AI dataset repository.

The current release is:

`v1.0.0`

The published release is approximately 528 MB.

It contains four major data components:

| Component | Approximate size | Purpose |
|---|---:|---|
| Canonical Database | 401.6 MB | Relational cricket database |
| Feature Store | 117 MB | Engineered historical features |
| Rating Store | 12.5 MB | Player ratings and historical snapshots |
| Predictive Store | 2.8 MB | Predictions, intervals and VORP |

The release also contains schemas, manifests and checksum files.

## Step 7 — Download the dataset using the project utility

You do not need to download each component manually.

The repository includes:

`src/data/download_dataset.py`

This utility is designed to retrieve the published dataset from Hugging Face.

First, make sure you are in the project root:

```bash
cd ~/Desktop/cricengine-ai
```

Activate your virtual environment if it is not already active:

```bash
source .venv/bin/activate
```

### 7.1 Download only the canonical database

```bash
python -m src.data.download_dataset --component database
```

This retrieves the canonical DuckDB database.

### 7.2 Download the Feature Store

```bash
python -m src.data.download_dataset --component features
```

This retrieves the engineered feature datasets.

### 7.3 Download the Rating Store

```bash
python -m src.data.download_dataset --component ratings
```

This retrieves the player rating datasets.

### 7.4 Download the Predictive Store

```bash
python -m src.data.download_dataset --component predictions
```

This retrieves the predictive datasets.

### 7.5 Download everything

If you want the complete dataset, run:

```bash
python -m src.data.download_dataset --component all
```

**Recommended for a first-time developer:** Use the `all` command if you have sufficient disk space and want to explore the complete project.

The download utility uses the repository's configured Hugging Face dataset ID. The public dataset should not require you to paste a token or password.

If the utility reports an authentication or permission error, check the dataset's public access settings and the utility configuration. Never share access tokens in GitHub issues or chat messages.

---

# PART 7 — Verify Your Download

## Step 8 — Run the verification utility

After downloading the dataset, run:

```bash
python -m src.data.download_dataset --component all --verify-only
```

This is intended to verify the downloaded components against their published checksums without downloading them again.

A successful verification means the files match the expected integrity records.

The release also contains:

- `dataset_manifest.json`
- `SHA256SUMS`
- Component-level `_manifest.json` files

These records help identify missing or corrupted files.

### 8.1 Manually verify the canonical database

On macOS:

```bash
shasum -a 256 data/datalake/curated/cricengine.duckdb
```

Expected SHA-256:

```text
a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae
```

If the hash differs, do not assume the database is valid. Check the download logs and manifest before using it.

### 8.2 Verify the component manifests

```bash
shasum -a 256 data/datalake/feature_store_v3b/_manifest.json
shasum -a 256 data/datalake/rating_store_v4/_manifest.json
shasum -a 256 data/datalake/predictive_store_v4c/_manifest.json
```

Use the published manifests as the authoritative reference for the individual files.

---

# PART 8 — Find the Downloaded Data on Your Computer

## Step 9 — Navigate to the data directory

The project uses the following logical data locations:

```text
data/
└── datalake/
    ├── curated/
    │   └── cricengine.duckdb
    │
    ├── feature_store_v3b/
    │
    ├── rating_store_v4/
    │
    └── predictive_store_v4c/
```

These are the expected project paths described by the repository architecture. The download utility's actual output location should be checked after downloading.

To inspect the data directories:

```bash
find data/datalake -maxdepth 2 -type d
```

To inspect the database:

```bash
ls -lh data/datalake/curated/
```

To inspect the feature store:

```bash
ls data/datalake/feature_store_v3b/
```

To inspect the rating store:

```bash
ls data/datalake/rating_store_v4/
```

To inspect the predictive store:

```bash
ls data/datalake/predictive_store_v4c/
```

If a directory is missing, first check the download utility's output and logs. Do not run the ingestion or feature-generation pipelines just to recreate a missing downloaded folder.

---

# PART 9 — Explore the Canonical Database

## Step 10 — Understand DuckDB

The canonical database is:

`cricengine.duckdb`

It is a relational analytical database containing historical cricket data.

Reported database contents:

- 14 relational tables.
- 9,085 matches.
- 4,383,700 deliveries.
- 7,014 canonical player records.

DuckDB lets you query the database using SQL without setting up a separate database server.

## Step 11 — Open the database using Python

Create a new Python file called:

`explore_database.py`

Paste the following code:

```python
import duckdb

DB_PATH = "data/datalake/curated/cricengine.duckdb"

# Connect in read-only mode.
con = duckdb.connect(DB_PATH, read_only=True)

# Display all database tables.
tables = con.execute("SHOW TABLES").df()

print("\nDATABASE TABLES")
print(tables)

con.close()
```

Run:

```bash
python explore_database.py
```

You should see the database table names.

## Step 12 — Run your first SQL query

Create a file called:

`first_query.py`

Paste:

```python
import duckdb

DB_PATH = "data/datalake/curated/cricengine.duckdb"

con = duckdb.connect(DB_PATH, read_only=True)

query = """
SELECT
    match_format,
    COUNT(*) AS total_matches
FROM dim_match
GROUP BY match_format
ORDER BY total_matches DESC;
"""

result = con.execute(query).df()

print(result)

con.close()
```

Run:

```bash
python first_query.py
```

This query counts the matches by format.

## Step 13 — Inspect a database table

Try:

```python
import duckdb

con = duckdb.connect(
    "data/datalake/curated/cricengine.duckdb",
    read_only=True
)

result = con.execute("""
    SELECT *
    FROM dim_match
    LIMIT 10
""").df()

print(result)

con.close()
```

This displays the first ten records in the match dimension table.

### Important database safety rule

Always use:

```python
read_only=True
```

when exploring the canonical database.

Do not run ingestion scripts or write SQL commands against the canonical database unless you are explicitly working on an approved database-development task.

---

# PART 10 — Explore the Feature Store

## Step 14 — Understand what the Feature Store contains

The Feature Store contains engineered historical player and match features.

It is designed to make analytical and modelling tasks easier without repeatedly processing millions of deliveries.

Examples of feature categories include:

- Batting performance.
- Bowling performance.
- Fielding contributions.
- Rolling match statistics.
- Rolling time-window statistics.
- Contextual and venue baselines.

The feature data is stored in Parquet files.

Parquet is a columnar storage format commonly used in analytics and data engineering.

## Step 15 — Read a Parquet file using Python

Make sure dependencies are installed.

```bash
pip install pandas pyarrow
```

Create a file called:

`explore_features.py`

Paste:

```python
import pandas as pd
from pathlib import Path

FEATURE_DIR = Path("data/datalake/feature_store_v3b")

# Find available Parquet files.
files = list(FEATURE_DIR.rglob("*.parquet"))

print("Number of Parquet files:", len(files))

if files:
    sample_file = files[0]

    print("\nSample file:")
    print(sample_file)

    df = pd.read_parquet(sample_file)

    print("\nFirst five records:")
    print(df.head())

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nDataset dimensions:")
    print(df.shape)
else:
    print("No Parquet files found. Check the download location.")
```

Run:

```bash
python explore_features.py
```

You have now accessed the Feature Store.

**Note:** The first Parquet file found is simply a sample. It is not guaranteed to represent the entire feature dataset.

---

# PART 11 — Explore the Rating Store

## Step 16 — Understand player ratings

The Rating Store contains outputs from the CA-HBSS player rating engine.

It includes:

- Current player-format ratings.
- Historical rating checkpoints.
- Pre-match rating snapshots.

The pre-match snapshots are particularly important because they preserve the rating information available before a match.

This supports point-in-time analysis and helps prevent future information from leaking into historical predictions.

## Step 17 — Inspect rating files

Use Python:

```python
import pandas as pd
from pathlib import Path

RATING_DIR = Path("data/datalake/rating_store_v4")

files = list(RATING_DIR.rglob("*.parquet"))

print("Rating Parquet files:", len(files))

if files:
    df = pd.read_parquet(files[0])

    print(df.head())
    print(df.columns.tolist())
    print(df.shape)
```

Save this as `explore_ratings.py` and run:

```bash
python explore_ratings.py
```

---

# PART 12 — Explore the Predictive Store

## Step 18 — Understand the predictions

The Predictive Store contains outputs from the Phase 4C predictive modelling system.

It includes:

- Batting predictions.
- Bowling predictions.
- Fielding predictions.
- Player-match VORP.
- Evaluation metrics.

Predictions are stored with uncertainty information where available.

This means you should not treat every prediction as a guaranteed outcome. Expected performance and uncertainty intervals should be considered together.

## Step 19 — Inspect predictive files

Create `explore_predictions.py`:

```python
import pandas as pd
from pathlib import Path

PREDICTIVE_DIR = Path(
    "data/datalake/predictive_store_v4c"
)

files = list(PREDICTIVE_DIR.rglob("*.parquet"))

print("Predictive Parquet files:", len(files))

if files:
    df = pd.read_parquet(files[0])

    print("\nSample predictions:")
    print(df.head())

    print("\nAvailable columns:")
    print(df.columns.tolist())

    print("\nShape:")
    print(df.shape)
```

Run:

```bash
python explore_predictions.py
```

---

# PART 13 — Run the Project Demo

## Step 20 — Locate the demo files

If you have received the separate professor demo package, locate its `professor_demo/` folder.

The reported package includes:

```text
professor_demo/
├── START_HERE.md
├── run_demo_walkthrough.py
├── explore_database.py
├── explore_features.py
├── sample_queries.sql
└── dataset_inventory.md
```

This folder is a separate demo package. It may not be included in every GitHub clone.

Read `START_HERE.md` first.

## Step 21 — Run the walkthrough

If the demo package is present in the project root, run:

```bash
python professor_demo/run_demo_walkthrough.py
```

The walkthrough is intended to demonstrate how to inspect the database and the downloaded analytical data.

If you receive a file-not-found error, check that the demo package has been obtained and that its expected data paths exist.

---

# PART 14 — Start Exploring the Code

Once you have successfully downloaded and inspected the dataset, you can begin understanding the implementation.

A recommended exploration order is:

| Order | Area | What to understand |
|---|---|---|
| 1 | `config/` | Project settings and configuration |
| 2 | `etl/` | Data extraction and feature-generation pipelines |
| 3 | `src/ratings/` | Bayesian player rating implementation |
| 4 | `src/predictive/` | Predictive modelling |
| 5 | `src/data/` | Dataset access and download utilities |
| 6 | `tests/` | Automated validation and expected behaviour |

Do not rebuild any of the published data stores merely to understand them.

Start by reading the code, inspecting the existing outputs and running safe queries.

---

# PART 15 — Common Problems and Solutions

## Problem 1: `python3.12: command not found`

Python 3.12 is not available in your terminal.

On macOS:

```bash
brew install python@3.12
```

Then check:

```bash
python3.12 --version
```

## Problem 2: `No module named duckdb`

Install the dependencies:

```bash
pip install -r requirements.txt
```

Or install DuckDB directly:

```bash
pip install duckdb
```

## Problem 3: `No module named pyarrow`

Run:

```bash
pip install pyarrow pandas
```

## Problem 4: `No such file or directory`

You may not be in the project root.

Check:

```bash
pwd
```

Then navigate to the repository:

```bash
cd ~/Desktop/cricengine-ai
```

Adjust the path if you cloned it somewhere else.

## Problem 5: Hugging Face download fails

Check:

1. Whether your internet connection works.
2. Whether the public dataset page opens.
3. Whether you are using the latest repository version.
4. Whether the download utility reports an HTTP, permission or checksum error.

Do not assume that an HTTP 403 or 404 is a corrupted dataset. It may indicate an access or repository configuration issue.

## Problem 6: Checksum mismatch

Do not use a file that fails integrity verification.

Try:

1. Read the download error.
2. Check available disk space.
3. Remove only the incomplete downloaded component, if the utility documentation confirms that it is safe to do so.
4. Download it again.
5. Re-run verification.

Do not delete or overwrite the original canonical database or other frozen data assets as a troubleshooting shortcut.

## Problem 7: Git LFS files look unusually small

If a large file appears to contain a short text pointer instead of the actual data, check whether Git LFS is installed and initialized.

```bash
git lfs install
git lfs pull
```

This applies to files tracked through Git LFS. It is separate from downloading the Hugging Face dataset through the project utility.

---

# PART 16 — Important Rules for New Contributors

Before making changes to CricEngine AI, follow these rules.

### Data integrity

- Do not modify the canonical DuckDB database during ordinary exploration.
- Do not overwrite frozen Feature Store, Rating Store or Predictive Store assets.
- Use read-only connections for database inspection.
- Verify downloaded data using SHA-256 manifests.

### Modelling integrity

- Preserve point-in-time data constraints.
- Never introduce future information into historical features or pre-match ratings.
- Do not treat missing data as zero without checking its meaning.
- Do not merge player identities based only on matching names.
- Preserve uncertainty information when analysing predictions.

### Repository collaboration

- Create a separate branch for your work.
- Avoid modifying unrelated files.
- Run relevant tests before submitting a pull request.
- Document your changes and the reasoning behind them.
- Do not commit API keys, tokens, passwords or other credentials.

### Source data and licensing

- Follow the source-data attribution and licensing requirements.
- Do not redistribute raw Cricsheet files outside the permitted terms.
- Check the dataset card and licence documents before reusing or redistributing data.

---

# PART 17 — Your First-Time Developer Checklist

Use this checklist to confirm that you have completed the setup.

- [ ] Opened the GitHub repository.
- [ ] Read the main README.
- [ ] Installed Python 3.12.
- [ ] Installed Git and Git LFS.
- [ ] Cloned the repository.
- [ ] Created and activated a virtual environment.
- [ ] Installed project dependencies.
- [ ] Opened the Hugging Face dataset page.
- [ ] Downloaded the complete dataset.
- [ ] Ran the dataset verification utility.
- [ ] Opened the DuckDB database in read-only mode.
- [ ] Listed the 14 database tables.
- [ ] Read a sample Feature Store Parquet file.
- [ ] Inspected a Rating Store Parquet file.
- [ ] Inspected a Predictive Store Parquet file.
- [ ] Read the available demo instructions.
- [ ] Understood the repository contribution workflow.

---

# Final — Useful Links

| Resource | Link |
|---|---|
| GitHub Repository | https://github.com/DivyGupta4/cricengine-ai |
| Hugging Face Dataset | https://huggingface.co/datasets/divii1304/cricengine-ai-dataset |
| GitHub Issues | https://github.com/DivyGupta4/cricengine-ai/issues |
| GitHub Pull Requests | https://github.com/DivyGupta4/cricengine-ai/pulls |

**Welcome to CricEngine AI.**

Start by downloading the published dataset, verifying its integrity and exploring the canonical database. Once you understand the data architecture, move on to the feature engineering, rating and predictive modelling implementations.

The goal is not just to run the project. It is to understand how the data moves through the system and how each analytical layer is constructed.
