# Azure Route Server and Cisco Meraki vMX Deployment Guide (Preview not production ready)

Authors: Simarbir Singh, Mitchell Gulledge

# Solution Overview

This document encompasses a detailed step by step guide on deploying the Azure Route Server (Currently in Preview) and Cisco Meraki vMXs hosted in the Azure cloud. BGP is utilized to provide resiliency, symmetry and load sharing across vMXs in the Azure cloud.

# Solution Architecture
![Test Image 1](RouteServerTopology.png)

In the above diagram, the branch MX connects to a pair of vMXs deployed in the same VNET across different Availability Zones for redundancy. EBGP has been configured across the vMXs to the route server virtualRouterIps that will be discussed further later. IBGP is formed on top of Auto VPN directly from the Branch to the respective vMXs in the Azure cloud. AS Path manipulation is used to ensure symmetry for the route to Azure and the route back from Azure, this is done in accordance with the concentrator priority that is configured at the branch MX site to site vpn settings. 

# Step 1) Deploy Cisco Meraki Network Virtual Appliances (vMXs) from Azure Marketplace

The steps for deploying virtual MXs from the Azure marketplace are out of scope for this document. For more information on deploying virtual MXs from the Azure marketplace please reference the following link:
https://documentation.meraki.com/MX/MX_Installation_Guides/vMX_Setup_Guide_for_Microsoft_Azure

# Step 2) Prep Azure  Route Server Environment (CLI Reference)

For additional ways to automate or configure through the Azure portal please refer to the Azure Route Server Documentation here:
https://docs.microsoft.com/en-us/azure/route-server/overview

The steps for deploying the route server via the CLI are as follows:

1) Login to your Azure account:

```
az login
```

2) Ensure you are in the correct subscription in Azure

```
az account list
```

3) For the Azure Route Server, a VNET is need in order to host the service. Use the follow command to create a resource group and virtual network. (Use these if you do not already have a virtual network) Below snippets were taken directly from Azure documentation: https://docs.microsoft.com/en-us/azure/route-server/quickstart-configure-route-server-cli

```
az group create -n “RouteServerRG” -l “westus” 
az network vnet create -g “RouteServerRG” -n “myVirtualNetwork” --address-prefix “10.0.0.0/16” 
```

4) Next we must create a subnet inside the VNET to host the route server and obtain the subnet ID. Below are the commands to create the subnet followed by the command to obtain the subnet ID.

```
az network vnet subnet create -g “RouteServerRG” --vnet-name “myVirtualNetwork” --name “RouteServerSubnet” --address-prefix “10.0.0.0/24”  
az network vnet subnet show -n “RouteServerSubnet” --vnet-name “myVirtualNetwork” -g “RouteServerRG” --query id -o tsv
```

# Step 3) Deploy Azure Route Server (CLI Reference)

Now that the Azure Resource Group, VNET, Subnets etc have all been created, the next step is to configure the route server. Below is the CLI command for creating the server:

```
az network routeserver create -n “myRouteServer” -g “RouteServerRG” --hosted-subnet $subnet_id  
```

From Azure: "The location needs to match the location of your virtual network. The HostedSubnet is the RouteServerSubnet ID you obtained in the previous section."


