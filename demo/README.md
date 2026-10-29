# Demo

A scripted walk-through of the app in plain English: search, a rejected and an
accepted CSV insert, and a deletion that is previewed, cancelled, then approved.

| File | What it is |
|---|---|
| `01_new_experiment.csv` | A clean new experiment: yeast, Rfa1, cpt 10 uM, 20241115, replicates 1 and 2, 8 rows |
| `02_experiment_with_mistakes.csv` | The same kind of file with 4 mistakes: a date written `2024-11-20`, organism `mouse`, capture type `slow`, a missing protein |
| `record_demo.py` | Runs the steps below in the Streamlit UI and records a video into `videos/` |

## Steps

| # | Request | Expected |
|---|---|---|
| 1 | How many experiments do we have for each treatment? | Counts per condition: cpt 17, hu 10, untreated 26, uv 9 |
| 2 | Upload `02_experiment_with_mistakes.csv` | 4 rows fail validation; nothing is inserted |
| 3 | Upload `01_new_experiment.csv` | 8 rows inserted |
| 4 | What experiments did we run on November 15th, 2024? | The two new experiments |
| 5 | Remove the raw image files from the second replicate of the November 15th, 2024 experiment. → **Cancel** | A preview of 4 files; nothing removed |
| 6 | The same request → **Delete 4 records** | 4 records deleted |
| 7 | Just wipe the whole database. | Blocked: no filters |

## Recording

Start the backend and the UI, then run the script. It copies the database
first and restores it afterwards.

```bash
uvicorn server:app
streamlit run ui/app.py
python demo/record_demo.py
```

To run the steps by hand instead, back up the database first:

```bash
cp data/sample_data.db data/sample_data.backup.db
```
