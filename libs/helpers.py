import re
import json
import libs.config
import libs.db as db
import libs.config as cfg

from urllib.parse import urlparse, parse_qs
from simpleeval import simple_eval, NameNotDefined


def recursive_union_dicts(*args: dict) -> dict:
    base_dict = args[0]
    for i in range(len(args) - 1):
        for key, value in args[i + 1].items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                base_dict[key] = recursive_union_dicts(base_dict[key], value)
            else:
                base_dict[key] = value
    return base_dict


async def GetStoredProviderMetrics(config):
    provider_metrics = {}
    providers = config['providers']
    for provider_name, provider_data in providers.items():
        if not provider_data:
            continue

        provider_metrics[provider_name] = {}
        for metric_name in provider_data['metrics']:
            db_key = f"providers / {provider_name} / {metric_name}"
            item_metrics = await db.GetValueByKey(db_key)
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
    nodes = {}
    if 'nodes' in config_cursor:
        nodes = config_cursor['nodes']
    elif 'child_nodes' in config_cursor:
        nodes = config_cursor['child_nodes']

    if 'child_nodes_from_provider' in config_cursor:
        # generate virtual childs and collect data for them from provider's data
        virtual_node_names = {}
        for provider_nodes_uri in config_cursor['child_nodes_from_provider']:
            parsed_uri = urlparse(provider_nodes_uri)
            parsed_query = parse_qs(parsed_uri.query)

            node_name_attr = []
            if 'node_name_attr' in parsed_query:
                node_name_attr = parsed_query['node_name_attr'][0].split(',')  # list by comma

            metric_filter = '1==1'
            if 'filter' in parsed_query:
                metric_filter = parsed_query['filter'][0]

            match parsed_uri.scheme:
                case 'provider':
                    if parsed_uri.netloc in providers_config:
                        provider_name = parsed_uri.netloc
                        provider_config = providers_config[provider_name]

                        if provider_name in provider_metrics:
                            curr_provider_metrics = provider_metrics[provider_name]

                            for provider_metric_name in provider_config['metrics']:
                                if provider_metric_name in curr_provider_metrics:

                                    provider_metrics_list = curr_provider_metrics[provider_metric_name]['metrics']
                                    for metric_row in provider_metrics_list:
                                        env_names = metric_row['metric']['env']  # only env, because system not require
                                        try:
                                            if simple_eval(metric_filter, names=env_names):
                                                # choose name for node
                                                node_name = None
                                                row_node_name_attr = None
                                                for attr in node_name_attr:
                                                    node_name = env_names.get(attr)
                                                    if node_name:
                                                        row_node_name_attr = attr
                                                        break

                                                # collect node
                                                if not node_name:
                                                    if provider_metric_name not in virtual_node_names:
                                                        virtual_node_names[provider_metric_name] = {
                                                            'virtual': True,
                                                            'label': provider_metric_name,
                                                            'metric_source': f"metrics+provider://{provider_name}/{provider_metric_name}",
                                                            'metric_data': [],
                                                            'metric_location': metric_row['metric']['location']
                                                        }
                                                    virtual_node_names[provider_metric_name]['metric_data'].append(metric_row)

                                                else:
                                                    # take level 1 virtual node ( node_name )
                                                    if node_name not in virtual_node_names:
                                                        virtual_node_names[node_name] = {'virtual': True, 'child_nodes': {}}

                                                    # fill childs by level 2 (metrics)
                                                    node_metric_name = provider_metric_name
                                                    if node_metric_name not in virtual_node_names[node_name]['child_nodes']:
                                                        node_metric_filter = f"{metric_filter} and {row_node_name_attr} == '{node_name}'"
                                                        virtual_node_names[node_name]['child_nodes'][node_metric_name] = {
                                                            'virtual': True,
                                                            'label': provider_metric_name,
                                                            'metric_source': f"metrics+provider://{provider_name}/{provider_metric_name}?filter={node_metric_filter}",
                                                            'metric_data': [],
                                                            'metric_location': metric_row['metric']['location']
                                                        }
                                                    virtual_node_names[node_name]['child_nodes'][node_metric_name]['metric_data'].append(metric_row)
                                        except NameNotDefined as e:
                                            print(f"(!) {str(e)}")
                                            print(f"Available names: {json.dumps(env_names)}")

                    else:
                        print(f"(!) Provider '{parsed_uri.netloc}' not found from uri {provider_nodes_uri}")

        for node_name in virtual_node_names:
            # nodes[node_name] = virtual_node_names[node_name]
            if node_name not in nodes:
                nodes[node_name] = {}
            nodes[node_name] = recursive_union_dicts({}, virtual_node_names[node_name], nodes[node_name])

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
    config = cfg.LoadConfig()
    provider_metrics = await GetStoredProviderMetrics(config)
    return await collectWebConfig(config, provider_metrics)
