'''First, intall the 'beautifulsoup4' in VS Code environment. In terminal run:
pip install beautifulsoup4 requests
'''
from urllib.request import urlopen, Request
from bs4 import BeautifulSoup
import requests


# Specify URL

url = 'https://precoscombustiveis.dgeg.gov.pt/estatistica/postos/'

# Package the request, send the request and catch the response: r

r = requests.get(url)

# Extracts the response as html: html_doc

html_doc = r.text

# Create a BeautifulSoup object from the HTML: soup - note: BeautifulSoup 
# supports several parsers (html.parser, lxml, html5lib, etc.)
soup = BeautifulSoup(html_doc, 'html.parser')
# Print the title of the webpage, DGEG combustiveis
preços_combustiveis_online_title = soup.title

print(preços_combustiveis_online_title)

# Get preços_combustiveis_online's text

preços_combustiveis_online_text = soup.get_text()

print(preços_combustiveis_online_text)

'''
Note: 
The results table is empty in the raw HTML
 (| # | Nome do Posto | ... | with no rows underneath), 
 and there's a "Procurar" (Search) button and filter dropdowns 
 for Distrito, Município, Marca, etc.

That means this page loads its data dynamically via JavaScript/AJAX after 
you select filters and click search — requests.get() only gets you the 
initial page skeleton, not the actual station/price data. 

BeautifulSoup.get_text() on this page will basically just 
give you nav links, labels, and footer boilerplate — never the 
pricing table itself, no matter how you filter your parsing.
'''