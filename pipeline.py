# PIPELINE: entry point that runs the full ETL in sequence
# Created: 27/09/2026
# Usage (from the project root, with .venv active):  python pipeline.py

from etl.extract import extract
from etl.load import load
from etl.transform import transform


def run():
    # 1. Get the raw records from the DGEG API
    registos = extract()
    print(f"Extract complete: {len(registos)} records\n")

    # 2. Clean them into a DataFrame
    df = transform(registos)
    print(f"Transform complete: {df.shape[0]} rows, {df.shape[1]} columns\n")

    # 3. Save the result to disk
    load(df)
    print("Pipeline finished.")


# Only runs when this file is executed directly ("python pipeline.py"),
# not when another file imports it
if __name__ == "__main__":
    run()