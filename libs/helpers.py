import re
import json
import libs.config
from urllib.parse import urlparse, parse_qs
from libs.db import GetValkeyClient
from libs.config import LoadConfig
from simpleeval import simple_eval


async def GetStoredProviderMetrics(config):
    global valkey_client
    valkey_client = GetValkeyClient()

    provider_metrics = {}
    providers = config['providers']
    for provider_name, provider_data in providers.items():
        provider_metrics[provider_name] = {}
        match provider_data['type']:
            case 'prometeus':
                for metric_name in provider_data['metrics']:

                    db_key = f"providers / {provider_data['type']} / {metric_name}"
                    # airflow01.atlas.mchs.ru--memory-free
                    item_metrics = None
                    if valkey_client:
                        item_metrics = await valkey_client.get(db_key)
                    if item_metrics is None:
                        item_metrics = {
                            'last_check_ts': 0,
                            'metrics': []
                        }
                    else:
                        item_metrics = json.loads(item_metrics)

                    provider_metrics[provider_name][metric_name] = item_metrics

    return provider_metrics


async def CollectNodesOfCursor(config_cursor, provider_metrics, providers_config):
    if 'nodes' in config_cursor:
        nodes = config_cursor['nodes']
    elif 'child_nodes' in config_cursor:
        nodes = config_cursor['child_nodes']
    else:
        nodes = {}

    if 'child_nodes_from_provider' in config_cursor:
        # generate virtual childs and collect data for them from provider's data
        virtual_node_names = {}
        for provider_nodes_uri in config_cursor['child_nodes_from_provider']:
            parsed_uri = urlparse(provider_nodes_uri)
            parsed_query = parse_qs(parsed_uri.query)

            node_name_attr = 'instance'
            metric_filter = 'true'
            if 'node_name_attr' in parsed_query:
                node_name_attr = parsed_query['node_name_attr'][0]
            if 'filter' in parsed_query:
                metric_filter = parsed_query['filter'][0]

            match parsed_uri.scheme:
                case 'provider':
                    if parsed_uri.netloc in providers_config:
                        provider_name = parsed_uri.netloc
                        provider_config = providers_config[provider_name]

                        if provider_name in provider_metrics:
                            current_provider_metrics = provider_metrics[provider_name]

                            for provider_metric_name in provider_config['metrics']:
                                if provider_metric_name in current_provider_metrics:
                                    current_provider_metrics_list = current_provider_metrics[provider_metric_name]['metrics']

                                    for metric_row in current_provider_metrics_list:
                                        if node_name_attr not in metric_row['metric']:
                                            provider_path = f"{parsed_uri.netloc} / {provider_metric_name}"
                                            print(f"(!) attr '{node_name_attr}' not found in metrics of provider {provider_path}: {metric_row}")
                                            continue
                                        node_name = metric_row['metric'][node_name_attr]
                                        if simple_eval(metric_filter, names=metric_row['metric']):
                                            if node_name not in virtual_node_names:
                                                virtual_node_names[node_name] = {'virtual': True, 'child_nodes': {}}
                                            node_metric_name = f"{node_name}--{provider_metric_name}"
                                            if node_metric_name not in virtual_node_names[node_name]['child_nodes']:
                                                node_metric_filter = f"{metric_filter} and {node_name_attr} == '{node_name}'"
                                                virtual_node_names[node_name]['child_nodes'][node_metric_name] = {
                                                    'virtual': True,
                                                    'label': provider_metric_name,
                                                    'metric_source': f"metrics+provider://{provider_name}/{provider_metric_name}?filter={node_metric_filter}",
                                                    'metric_data': []
                                                }
                                            virtual_node_names[node_name]['child_nodes'][node_metric_name]['metric_data'].append(metric_row)
                    else:
                        print(f"(!) Provider '{parsed_uri.netloc}' not found from uri {provider_nodes_uri}")

        for node_name in virtual_node_names:
            nodes[node_name] = virtual_node_names[node_name]

    return nodes


async def collectWebConfig(config, provider_metrics, config_node: dict = {}, deep=[]):
    if len(config_node.items()) == 0:
        config_node = config

    deep_str = '/' + '/'.join(deep)
    web_config_node = {}
    for k, v in config_node.items():
        if not any(re.search(pattern, f"{deep_str}/{k}") for pattern in libs.config.allow4web_keys):
            continue

        if type(v) is dict:
            web_config_node[k] = await collectWebConfig(config, provider_metrics, config_node[k], deep + [k])
        else:
            web_config_node[k] = v

    # fill by virtual nodes
    child_nodes = await CollectNodesOfCursor(config_node, provider_metrics, config['providers'])
    if len(child_nodes.items()) > 0:
        if 'child_nodes' not in web_config_node:
            web_config_node['child_nodes'] = {}
        for vk, vv in child_nodes.items():
            web_config_node['child_nodes'][vk] = vv

    return web_config_node


async def GetWebConfig():
    config = LoadConfig()
    provider_metrics = await GetStoredProviderMetrics(config)
    return await collectWebConfig(config, provider_metrics)
