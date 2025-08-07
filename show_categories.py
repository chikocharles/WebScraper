import pandas as pd

# Read the CSV file
df = pd.read_csv('scraped_data.csv')

print("Sample categorizations:")
for _, row in df.head(8).iterrows():
    title = row['Job Title'][:50] + "..." if len(row['Job Title']) > 50 else row['Job Title']
    print(f"- {title} -> {row['Category']}")

print(f"\nTotal jobs: {len(df)}")
print("\nCategory distribution:")
print(df['Category'].value_counts())
