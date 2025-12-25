import requests
import json

# Check status of existing conversation
conv_id = "bb0c5af9-10c0-43da-aeb9-2e354d9ce5fb"
url = f"https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat/{conv_id}/status"

response = requests.get(url)
data = response.json()

print(f"Status: {data['status']}")
print(f"Progress: {data['progress']['percentage']}%")
print(f"Answer length: {len(data['final_answer'])}")

if "no data" in data['final_answer'].lower():
    print("\n❌ Still NO DATA")
    if data.get('databricks_jobs'):
        job = data['databricks_jobs'][0]
        print(f"Job run_id: {job['run_id']}, status: {job['status']}, result: {job.get('result', {}).get('result_state', 'N/A')}")
else:
    print("\n✅ SUCCESS - GOT REAL DATA!")
    print(f"\nFirst 300 chars:\n{data['final_answer'][:300]}")
