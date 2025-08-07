import json

# Read and verify JSON structure
with open('scraped_data_20250807_222803.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('JSON structure verification:')
print(f'Total jobs in JSON: {len(data)}')
print()

if data:
    print('Sample job structure:')
    sample_job = data[0]
    for key, value in sample_job.items():
        print(f'  {key}: {repr(value)}')
    
    print()
    print('First 3 jobs summary:')
    for i, job in enumerate(data[:3]):
        print(f'{i+1}. ID: {job["id"]}')
        print(f'   Title: {job["title"][:50]}...')
        print(f'   Company: {job["company"]}')
        print(f'   Email: {job["applyEmail"]}')
        print(f'   Closing: {job["closingDate"]}')
        print()

print('JSON file validation: SUCCESS')
