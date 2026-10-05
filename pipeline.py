# Main ETL pipeline
# Created: 27/09/2026
# Run from the project root with: python pipeline.py

from etl.extract import extract
from etl.transform import transform
from etl.load import load


def run():
    # Extract data from the DGEG API
    registos = extract()
    print(f"Extract complete: {len(registos)} records\n")

    # Transform the extracted data
    df = transform(registos)
    print(f"Transform complete: {df.shape[0]} rows, {df.shape[1]} columns\n")

    # Load the transformed data
    load(df)
    print("Pipeline finished.")

# Only runs when this file is executed directly
if __name__ == "__main__":
    run()