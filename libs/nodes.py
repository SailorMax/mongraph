import json
from libs.config import GetConfig
from libs.db import GetValkeyClient
from libs.metrics import CollectNodesOfCursor
from libs.helpers import GetStoredProviderMetrics


async def GetNodesDbNames(config_node, provider_metrics, config=None):
    node_names = []
    nodes_list = await CollectNodesOfCursor(config_node, provider_metrics, GetConfig()['providers'])
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


async def GetMetricOfNode(node_config, provider_metrics, providers_config):
    sub_nodes = await CollectNodesOfCursor(node_config, provider_metrics, providers_config)
    print(json.dumps(sub_nodes, indent=2))
    # if has metric_data => use it
    # if no => look at childs
    # if no => look at DB
    return {
        'ts': 0,
        'status': '',
        'log': []
    }


async def GetNodeInfo(node_path: str):
    # TODO:
    # - project_name
    # - label
    # - graph_file
    # - child_nodes
    # - - name: label, metrics
    config = GetConfig()
    provider_metrics = await GetStoredProviderMetrics(config)

    # find config_node
    node_deep = []
    config_node = config
    if node_path != '':
        path_els = node_path.split('/')
        for node_name in path_els:
            if 'nodes' in config_node:
                config_node = config_node['nodes'][node_name]
            elif 'child_nodes' in config_node:
                config_node = config_node['child_nodes'][node_name]
            else:
                break

            node_deep.append({
                'name': node_name,
                'label': config_node['label']
            })

    # collect childs
    child_nodes = {}
    child_nodes_config = await CollectNodesOfCursor(config_node, provider_metrics, config['providers'])
    for name, node_config in child_nodes_config.items():
        child_nodes[name] = {
            'label': node_config['label'] if 'label' in node_config else name,
            'metric': await GetMetricOfNode(node_config, provider_metrics, config['providers'])
        }

    # collect info
    node_info = {
        'project_name': config['label'],
        'graph_file': config_node['graph_file'] if 'graph_file' in config_node else '',
        'node_deep': node_deep,
        'child_nodes': child_nodes
    }

    return node_info
