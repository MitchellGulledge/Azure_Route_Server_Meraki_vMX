import requests 
import json 
import time
import meraki
import logging
import os
import azure.functions as func


#from pprint import pprint as pp

# Azure authentication credentials are listed below
AZURE_MGMT_URL = "https://management.azure.com"
BLOB_HOST_URL = "blob.core.windows.net"
SUBSCRIPTION_ID = os.environ['subscription_id']
RESOURCE_GROUP = os.environ['resource_group']
ROUTE_SERVER_NAME = os.environ['route_server_name']
AZURE_TOKEN = {"Authorization": "Bearer "} 



# Defining your API key as a variable in source code is not recommended
API_KEY = os.environ['meraki_api_key'].lower()
# Instead, use an environment variable as shown under the Usage section
# @ https://github.com/meraki/dashboard-api-python/
# creating variable for org name to later map the org ID
org_name = os.environ['meraki_org_name']
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


def get_bearer_token(resource_uri):
    access_token = None
    try:
        identity_endpoint = os.environ['IDENTITY_ENDPOINT']
        identity_header = os.environ['IDENTITY_HEADER']
    except:
        logging.error("Could not obtain authentication token for Azure. Please ensure "
                      "System Assigned identities have been enabled on the Azure Function.")
        return None

    token_auth_uri = f"{identity_endpoint}?resource={resource_uri}&api-version=2017-09-01"
    head_msi = {'secret': identity_header}
    try:
        resp = requests.get(token_auth_uri, headers=head_msi)
        access_token = resp.json()['access_token']
    except Exception as e:
        logging.error("Could not obtain access token to manage other Azure resources.")
        logging.error(e)

    return access_token


access_token = get_bearer_token(AZURE_MGMT_URL)
AZURE_TOKEN = {'Authorization': f'Bearer {access_token}'}

def get_microsoft_network_base_url(AZURE_MGMT_URL, SUBSCRIPTION_ID, rg_name=None, provider="Microsoft.Network"):
    if rg_name:
        return "{0}/subscriptions/{1}/resourceGroups/{2}/providers/{3}".format(AZURE_MGMT_URL, SUBSCRIPTION_ID, rg_name, provider)

    return "{0}/subscriptions/{1}/providers/{2}".format(AZURE_MGMT_URL, SUBSCRIPTION_ID, provider)

# function to obtain the route server information, we would need the routeserver asn and IP to peer with the vMXs. 
def get_route_server(AZURE_MGMT_URL, SUBSCRIPTION_ID, RESOURCE_GROUP, ROUTE_SERVER_NAME, AZURE_TOKEN):
    endpoint_url = get_microsoft_network_base_url(AZURE_MGMT_URL,
                                                   SUBSCRIPTION_ID, RESOURCE_GROUP) + f"/virtualHubs/{ROUTE_SERVER_NAME}?api-version=2020-07-01"
    route_server_list = requests.get(endpoint_url, headers=AZURE_TOKEN)
    route_server_info = route_server_list.json()
    #print(route_server_info)
    routeserver_bgp_dict_info = {
        'routeserver_asn': route_server_info['properties']['virtualRouterAsn'],
        'routeserver_ips': route_server_info['properties']['virtualRouterIps']
    }
    #pp(routeserver_bgp_dict_info)

    return routeserver_bgp_dict_info

def get_route_server_bgp_connections(RESOURCE_GROUP, ROUTE_SERVER_NAME, AZURE_TOKEN):
    endpoint_url = get_microsoft_network_base_url(AZURE_MGMT_URL,
                                                   SUBSCRIPTION_ID, RESOURCE_GROUP) + f"/virtualHubs/{ROUTE_SERVER_NAME}/bgpConnections?api-version=2020-07-01"
    route_server_bgp_connections_list = requests.get(endpoint_url, headers=AZURE_TOKEN)
    route_server_bgp_connections_info = route_server_bgp_connections_list.json()

    return route_server_bgp_connections_info

# function to update the routeserver bgp config
def update_route_server_bgp_connections(RESOURCE_GROUP, ROUTE_SERVER_NAME, connection_name, \
                        peer_ip, peer_asn, AZURE_TOKEN):
    endpoint_url = get_microsoft_network_base_url(AZURE_MGMT_URL,
                                                  SUBSCRIPTION_ID, RESOURCE_GROUP) + \
                                                  f"/virtualHubs/{ROUTE_SERVER_NAME}/bgpConnections/{connection_name}?api-version=2020-07-01"

    peer_config = {
            "properties": {
                "peerIp": peer_ip,
                 "peerAsn": peer_asn
            }
        }

    route_server_bgp_update = requests.put(endpoint_url, headers=AZURE_TOKEN, json=peer_config)

    return route_server_bgp_update
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
    route_server_config = get_route_server(AZURE_MGMT_URL, SUBSCRIPTION_ID, RESOURCE_GROUP, ROUTE_SERVER_NAME, AZURE_TOKEN)
    route_server_ips_to_add = []
    enabled = True
 
    for ips in route_server_config['routeserver_ips']:
        route_server_ips_to_add.append(ips)  
    
    # executing API call to obtain BGP configuration for specified network ID
    network_bgp_config = meraki_dashboard_sdk_auth.appliance.getNetworkApplianceVpnBgp(
        network_id
    )
    # conditional statement to ensure BGP is enabled for the tagged network, if not we will
    # update the BGP config for the network ID that we already put to function and return the config
    if network_bgp_config['enabled'] == False:
        # enabling BGP config for network
        enable_bgp_response = meraki_dashboard_sdk_auth.appliance.updateNetworkApplianceVpnBgp(
            network_id, enabled, 
            ibgpHoldTimer=180
        )
        update_bgp_config = meraki_dashboard_sdk_auth.appliance.updateNetworkApplianceVpnBgp(
                    network_id, enabled, 
                    ibgpHoldTimer=180,
                    neighbors=[{'ip': route_server_ips_to_add[0], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}, \
                            {'ip': route_server_ips_to_add[1], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}]
                )

    elif network_bgp_config['enabled'] == True and 'neighbors' in network_bgp_config:
        for ip in route_server_config['routeserver_ips']:
            if ip not in network_bgp_config['neighbors'][0]['ip']:
                update_bgp_config = meraki_dashboard_sdk_auth.appliance.updateNetworkApplianceVpnBgp(
                        network_id, enabled, 
                        ibgpHoldTimer=180,
                        neighbors=[{'ip': route_server_ips_to_add[0], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}, \
                                {'ip': route_server_ips_to_add[1], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}]
                    )

    elif network_bgp_config['enabled'] == True and 'neighbors' not in network_bgp_config:
        update_bgp_config = meraki_dashboard_sdk_auth.appliance.updateNetworkApplianceVpnBgp(
                network_id, enabled, 
                ibgpHoldTimer=180,
                neighbors=[{'ip': route_server_ips_to_add[0], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}, \
                           {'ip': route_server_ips_to_add[1], 'remoteAsNumber': route_server_config['routeserver_asn'], 'receiveLimit': 150, 'allowTransit': True, 'ebgpHoldTimer': 180, 'ebgpMultihop': 2}]
            )

    # performing get request to Meraki API to obtain the local subnets inside the VPN. 
    # This is needed so that we can resolve next hops for MultiHop EBGP
    get_network_meraki_vpn_config = meraki_dashboard_sdk_auth.appliance.getNetworkApplianceVpnSiteToSiteVpn(
        network_id
    )

    # using list comprehension to fetch all local subnets from the list of subnets
    local_subnet_list = [x['localSubnet'] for x in get_network_meraki_vpn_config['subnets'] if x['useVpn'] == True]

    # creating variable for local subnets to add to the vpn config for the hub
    local_subnets_to_add = []

    for network in local_subnet_list:

        for neighbor_ip in get_network_meraki_vpn_config['subnets']:

            logging.info(str(network)[0:-3])

            logging.info(str(neighbor_ip['localSubnet'])[0:-3])

            if str(network)[0:-3] in str(neighbor_ip['localSubnet'])[0:-3]:

                logging.info("local network configured for BGP neighbor")

            else:

                logging.info(f"local network not detected in vpn config, adding: {network}")

                # appending the network to the list local_subnets_to_add to later update VPN config
                local_subnets_to_add.append(network)

    # updating Meraki VPN config if the length of the local_subnets_to_add is greater than 0
    # setting to 100 so we never execute function
    if len(local_subnets_to_add) > 100:

        # executing function to update the local networks for the Azure vMX
        # setting the mode to hub as this is acting as a vpn concentrator
        mode = 'hub'

        # executing api call to update meraki vpn config
        update_local_networks_response = meraki_dashboard_sdk_auth.appliance.updateNetworkApplianceVpnSiteToSiteVpn(
            network_id, mode, 
            subnets=[{'localSubnet': local_subnets_to_add[0], 'useVpn': True}, {'localSubnet': local_subnets_to_add[1], 'useVpn': True}]
        )

        # logging the status of updating the site to site vpn config for the network
        logging.info(update_local_networks_response)



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


def main(MerakiTimer: func.TimerRequest) -> None:
    # executing function to obtain the device statuses so we can later obtain the inside IP of the vMXs
    meraki_device_status = get_org_meraki_device_status()

    # creating variable that is a list of all meraki networks inside the org
    org_networks = get_tagged_networks()

    # using list comprehension to obtain all networks containing the tag_prefix variable under the 
    # tags key in the list of dictionaries
    tagged_networks = [x for x in org_networks if str(tag_prefix) in str(x['tags'])[1:-1]]
    logging.info("Tagged Networks {0}".format(tagged_networks))

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

        if 'neighbors' in network_bgp_info:

            bgp_neighbors = [{'peer_ip' : x['ip'], 'peer_asn' : x['remoteAsNumber']} for x in network_bgp_info['neighbors']]

        else:

            bgp_neighbors = []
        
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
            'bgp_neighbors': bgp_neighbors
        }

        # appending the vmx_bgp_dict_info dictionary to the list list_of_meraki_vmx_bgp_config to 
        # make a list of dictionaries to be referenced when updating the Azure config
        list_of_meraki_vmx_bgp_config.append(vmx_bgp_dict_info)


    azure_route_server_bgp_connection_info = get_route_server_bgp_connections(RESOURCE_GROUP, \
        ROUTE_SERVER_NAME, AZURE_TOKEN)

    # now we need to compare the two dictionaries for Azure and Meraki (list_of_meraki_vmx_bgp_config and azure_route_server_bgp_connection_info['value'])
    azure_route_server_local_bgp_config = get_route_server(AZURE_MGMT_URL, SUBSCRIPTION_ID, RESOURCE_GROUP, ROUTE_SERVER_NAME, AZURE_TOKEN)

    #iterating through meraki bgp config
    for meraki_peers in list_of_meraki_vmx_bgp_config:

        # iterate over azure bgp connections
        for azure_peers in azure_route_server_bgp_connection_info['value']: 

            logging.info(meraki_peers)
            

            # Check if meraki uplink matches the azure routeserver peer ip, peer_asn and provisioning state
            if meraki_peers['uplink_ip'] == azure_peers['properties']['peerIp'] and \
                meraki_peers['bgp_asn'] == azure_peers['properties']['peerAsn'] and \
                    azure_peers['properties']['provisioningState'] == 'Succeeded':

                        # iterate over the meraki dict for bgp peers
                        for peers in meraki_peers['bgp_neighbors']:

                            # Match if meraki peer_asn, peer_ip matches the routeserver local asn and ip
                            if int(peers['peer_asn']) == int(azure_route_server_local_bgp_config['routeserver_asn']) and \
                                str(peers['peer_ip']) in azure_route_server_local_bgp_config['routeserver_ips']:
                                    logging.info("Network:{0} configured correctly and no new connections to configure".format([meraki_peers['network_name']]))
                                    
            # might have to un indent this one more time could be causing double puts to azure
            else:


                # if not update the routeserver config for the meraki peer 
                update_route_server_bgp_connections(RESOURCE_GROUP, ROUTE_SERVER_NAME, meraki_peers['network_name'], meraki_peers['uplink_ip'], meraki_peers['bgp_asn'], AZURE_TOKEN)
                logging.info("Updated route_server config for peer {0}".format(meraki_peers['network_name']))
