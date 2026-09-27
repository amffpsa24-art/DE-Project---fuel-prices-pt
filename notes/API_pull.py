# Import package
import requests

# Assign URL to variable: url

url = 'https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/GetMunicipios'
# Always include a descriptive User-Agent (Wikipedia requires this)
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
r = requests.get(url, headers=headers)

# Package the request, send the request and catch the response: r
r = requests.get(url)

# Decode the JSON data into a dictionary: json_data
json_data = r.json()

# Print the Wikipedia page extract
precoscombustiveis_1 = json_data['resultado'][0]['Distrito']['Descritivo']
print(precoscombustiveis_1)
print(r.status_code)   # is it 200?
print(r.text[:300])    # is it actually JSON, or an HTML error page?