import json
import base64
import libs.config as cfg
import libs.db as db
import libs.metrics as metrics
import libs.helpers as helpers


async def GetNodesDbNames(config_node, provider_metrics, config=None):
    node_names = []
    nodes_list = await helpers.CollectNodesOfCursor(config_node, provider_metrics, cfg.GetConfig()['providers'])
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
    config = cfg.GetConfig()
    provider_metrics = await helpers.GetStoredProviderMetrics(config)
    node_names = await GetNodesDbNames(config, provider_metrics)

    node_metrics = {}
    for name in node_names:
        stored_metrics = await db.GetValueByKey(name)
        if stored_metrics is not None:
            node_metrics[name] = json.loads(stored_metrics)

    return node_metrics


async def GetMetricOfNode(node_name, node_config, child_nodes):
    status2idx = {
        'unknown': -1,
        'normal': 0,
        'warning': 1,
        'danger': 2,
    }
    node_worst_metric_data = {
        'ts': 0,
        'status': 'unknown',
    }
    # print(node_name)
    # print(json.dumps(node_config, indent=2))
    # print(json.dumps(child_nodes, indent=2))
    if 'metric_source' in node_config:
        # print(f'< get metrics by source "{node_name}"')
        node_metrics = await metrics.GetStoredNodeMetrics(node_name)
        node_worst_metric_data = node_metrics
    else:
        for node_name, node in child_nodes.items():
            metric_data = None
            if 'metric' in node:
                # print(f"< get node metric: {node_name} -- {json.dumps(node, indent=2)}")
                metric_data = node['metric']
            elif 'child_nodes' in node:
                # print(f"< get metric of childs: {node_name} -- {node['child_nodes'].keys()}")
                metric_data = await GetMetricOfNode(node_name, node_config, node['child_nodes'])
            else:
                # print(f"< get data from db: {node_name}")
                metric_data = await db.GetValueByKey(node_name)  # TODO: read from DB?

            if metric_data is not None:
                if status2idx[node_worst_metric_data['status']] < status2idx[metric_data['status']]:
                    node_worst_metric_data['ts'] = metric_data['ts']
                    node_worst_metric_data['status'] = metric_data['status']
                    node_worst_metric_data['details'] = f"{node_name}: {metric_data['details']}"  # add prefix to detect source of metric

        # worst value without history
        node_worst_metric_data = {
            'ts': node_worst_metric_data['ts'],
            'status': node_worst_metric_data['status'],
            'details': node_worst_metric_data['details'] if 'details' in node_worst_metric_data else ''
        }
        if node_worst_metric_data['status'] == 'normal':
            node_worst_metric_data['details'] = ''

    return node_worst_metric_data


async def CollectNodesMetricSubTree(node_config, provider_metrics, providers_config):
    child_nodes = {}
    # print(f"1. {node_config['label'] if 'label' in node_config else node_config}")
    child_nodes_config = await helpers.CollectNodesOfCursor(node_config, provider_metrics, providers_config)
    # print(child_nodes_config.keys())
    for child_name, child_node_config in child_nodes_config.items():
        # print(f"2. {child_name}: {json.dumps(child_node_config, indent=2)}")
        sub_child_nodes = await CollectNodesMetricSubTree(child_node_config, provider_metrics, providers_config)
        child_nodes[child_name] = {
            'label': child_node_config['label'] if 'label' in child_node_config else child_name,
            'metric': await GetMetricOfNode(child_name, child_node_config, sub_child_nodes),
            'metric_node': child_node_config['metric_node'] if 'metric_node' in child_node_config else None
        }
        if sub_child_nodes:
            child_nodes[child_name]['child_nodes'] = sub_child_nodes
    return child_nodes


async def GetNodeInfo(node_path: str):
    # TODO:
    # - project_name
    # - label
    # - graph_file
    # - child_nodes
    # - - name: label, metrics
    config = cfg.GetConfig()

    # collect childs
    provider_metrics = await helpers.GetStoredProviderMetrics(config)
    child_nodes = await CollectNodesMetricSubTree(config, provider_metrics, config['providers'])

    # find config_node
    node_deep = []
    node_config = {'child_nodes': child_nodes}
    if node_path == '':
        node_config['graph_file'] = config['graph_file']
    else:
        path_els = node_path.split('/')

        for node_name in path_els:
            if node_name[:7] == 'base64,':
                node_name = base64.urlsafe_b64decode(node_name[7:]).decode('utf-8')

            if 'child_nodes' in node_config:
                node_config = node_config['child_nodes'][node_name]
            else:
                break

            node_deep.append({
                'name': node_name,
                'label': node_config['label']
            })

    # collect info
    node_info = {
        'project_name': config['label'],
        'ui_update_interval': config['ui_update_interval'],

        'graph_file': node_config['graph_file'] if 'graph_file' in node_config else '',
        'node_deep': node_deep,
        'child_nodes': node_config['child_nodes'] if 'child_nodes' in node_config else []
    }

    return node_info
