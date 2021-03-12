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

# creating function to obtain BGP config for tagged networks along with uplink information
def get_tagged_networks_bgp_data(network_id):

    # executing API call to obtain BGP configuration for specified network ID
    network_bgp_config = meraki_dashboard_sdk_auth.appliance.getNetworkApplianceVpnBgp(
        network_id
    )

    return network_bgp_config



# creating function to obtain the device status for all devices in the org, this will allow us to
# obtain the lan IP (Azures private IP) so we can later create peerings on the route server
def get_org_meraki_device_status():

    # using SDK to fetch the device status for every Meraki box in org
    device_status_response = meraki_dashboard_sdk_auth.organizations.getOrganizationDevicesStatuses(
        org_id, total_pages='all'
    )

    return device_status_response


# executing function to obtain the device statuses so we can later obtain the inside IP of the vMXs
meraki_device_status = get_org_meraki_device_status()

# creating variable that is a list of all meraki networks inside the org
org_networks = get_tagged_networks()

# using list comprehension to obtain all networks containing the tag_prefix variable under the 
# tags key in the list of dictionaries
tagged_networks = [x for x in org_networks if str(tag_prefix) in str(x['tags'])[1:-1]]

# creating list that will be list of dictionaries containing all the Meraki BGP information
# including the Uplink IP, Local ASN and current configured BGP peers
list_of_meraki_vmx_bgp_config = []

# using list comprehension to fetch the network IDs from the list of networks in the tagged_networks
# variable with all the Azure vMXs that were tagged
network_ids = [[x['name'], x['id'], x['tags']] for x in tagged_networks]

# iterating through list of network_ids and obtaining the BGP config for each vMX
for networks in network_ids:

    # executing function to fetch BGP config for given network ID, the network ID is going to be
    # indexed as networks[1] since the data is packed in a list ordered as name, id
    network_bgp_info = get_tagged_networks_bgp_data(networks[1])

    # now that we have the network ID and BGP information we need to obtain the inside IP of the vMX
    vmx_lan_ip = [x['lanIp'] for x in meraki_device_status if x['networkId'] == networks[1]]
    
    # creating master dictionary with relevant information to append to list_of_meraki_vmx_bgp_config
    # so that the Azure config can be updated with the appropriate BGP configuration
    vmx_bgp_dict_info = {
        'network_name': networks[0],
        'network_id': networks[1],
        'uplink_ip': vmx_lan_ip[0],
        # using list comprehension to pick out the specific tag within the list of tags that matches
        # the configured route server in Azure, with networks[2] being the list of tags
        'network_tags': [x for x in networks[2] if tag_prefix in x], 
        'bgp_enabled': network_bgp_info['enabled'], # this will have to be a check or something we get rid of
        'bgp_asn': network_bgp_info['asNumber'],
        'bgp_neighbors': network_bgp_info['neighbors']
    }

    # appending the vmx_bgp_dict_info dictionary to the list list_of_meraki_vmx_bgp_config to 
    # make a list of dictionaries to be referenced when updating the Azure config
    list_of_meraki_vmx_bgp_config.append(vmx_bgp_dict_info)


print(list_of_meraki_vmx_bgp_config)
