import json
from libs.config import GetConfig
from libs.db import GetValkeyClient
from libs.metrics import GetStoredProviderMetrics, CollectNodesOfCursor


async def GetNodesDbNames(config_node, provider_metrics, config=None):
    node_names = []
    nodes_list = await CollectNodesOfCursor(config_node, provider_metrics, GetConfig())
    for k, node in nodes_list.items():
        node_names.append(k)

        if 'nodes' in config_node:
            child_node_config = config_node['nodes'][k]
        elif 'child_nodes' in config_node:
            child_node_config = config_node['child_nodes'][k]
        else:
            child_node_config = None
            if 'child_nodes' in node:  # virtual node, without config
                for vk in node['child_nodes']:
                    node_names.append(vk)

        if child_node_config is not None:
            node_names.extend(await GetNodesDbNames(child_node_config, provider_metrics, config or config_node))

    return node_names


async def GetNodesMetrics():
    config = GetConfig()
    provider_metrics = await GetStoredProviderMetrics(config)
    node_names = await GetNodesDbNames(config, provider_metrics)

    node_metrics = {}
    valkey_client = GetValkeyClient()
    for name in node_names:
        stored_metrics = await valkey_client.get(name)
        if stored_metrics is not None:
            node_metrics[name] = json.loads(stored_metrics)

    return node_metrics
