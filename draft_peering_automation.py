import requests 
import json 
import time
import meraki

# Defining your API key as a variable in source code is not recommended
API_KEY = ''
# Instead, use an environment variable as shown under the Usage section
# @ https://github.com/meraki/dashboard-api-python/

# creating variable for org name to later map the org ID
org_name = ''

# creating tag prefix variable in order for the meraki dashboard to indicate to the Azure Function 
# that is needs to establish a peering session between the NVA and the route server
tag_prefix = 'ARS-'

# creating authentication variable for the Meraki SDK
meraki_dashboard_sdk_auth = meraki.DashboardAPI(API_KEY)

# writing function to obtain org ID via linking ORG name
result_org_id = meraki_dashboard_sdk_auth.organizations.getOrganizations()
for org in result_org_id:
    if org['name'] == org_name:
        org_id = org['id']


# When the function kicks off, the first thing we will do is grab all tagged networks 
# in Meraki dashboard via the sdk, below is the function to return all tagged networks
def get_tagged_networks():
    
    # executing API call to obtain all Meraki networks in the organization
    organization_networks_response = meraki_dashboard_sdk_auth.organizations.getOrganizationNetworks(
        org_id, total_pages='all'
    )

    return organization_networks_response

# creating variable that is a list of all meraki networks inside the org
org_networks = get_tagged_networks()

# using list comprehension to obtain all networks containing the tag_prefix variable under the 
# tags key in the list of dictionaries
tagged_networks = [x for x in org_networks if str(tag_prefix) in str(x['tags'])[1:-1]]

print(tagged_networks)
