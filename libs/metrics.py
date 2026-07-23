import time
import json
import re
import asyncio
import httpx
from urllib.parse import urlparse, parse_qs
from libs.config import GetConfig
from libs.db import GetValkeyClient
from libs.helpers import CollectNodesOfCursor
from simpleeval import simple_eval

status2idx = {
    'unknown': -1,
    'normal': 0,
    'warning': 1,
    'danger': 2,
}
status_pripority_names = list(reversed(list(status2idx.keys())[1:])) or []  # without 'unknown'

valkey_client = None
provider_metrics = {}


def GetStatusByValue(value, node_config, config):
    status, description = 'unknown', ''

    if value is None:
        description = 'Could not detect status. Value is empty.'
    elif 'value_source' in node_config:
        status = 'normal' if value == node_config['normal_level'] else 'danger'
        description = f"{node_config['value_source']}: {value}"
    else:
        levels_config = node_config['levels'] if 'levels' in node_config else config['defaults']['levels']
        levels_config['direction'] = 'up'
        if ('danger' in levels_config
            and re.search(r'(value\s*<=?|>=?\s*value)', levels_config['danger'])
            ):
            levels_config['direction'] = 'down'
        print(levels_config)

        if type(value) is list:
            values = sorted(value, key=lambda item: float(item[1]), reverse=(levels_config['direction'] != 'down'))
            value = values[0][1]
            description = "\n".join([f"{float(item[1]): >14,.2f}{levels_config['measurement']}  {item[0]}" for item in values])
        else:
            description = f"{value}{levels_config['measurement']}"

        try:
            value = float(value)
            status = 'normal'
            for level_name in status_pripority_names:
                if (level_name in levels_config
                    and type(levels_config[level_name]) is str
                    and simple_eval(levels_config[level_name], names={'value': value})
                    ):
                    status = level_name
                    break
        except Exception as e:
            print(e)
            status = 'danger'

    return status, description


async def RefreshProviderMetrics(config):
    now = int(time.time())
    provider_metrics = {}
    providers = config['providers']
    for provider_name, provider_data in providers.items():
        provider_metrics[provider_name] = {}
        provider_base_url = provider_data['base_url']
        match provider_data['type']:
            case 'prometeus':
                for metric_name, metric_data in provider_data['metrics'].items():

                    db_key = f"providers / {provider_data['type']} / {metric_name}"
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

                    update_interval = metric_data['update_interval'] if 'update_interval' in metric_data else config['defaults']['update_interval']
                    if item_metrics['last_check_ts'] + update_interval < now:
                        try:
                            async with httpx.AsyncClient(timeout=3.0) as client:
                                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                                content = f"query={metric_data['query']}"
                                response = await client.post(provider_base_url, headers=headers, content=content, follow_redirects=True)
                                resp_json = response.json()
                                if resp_json['status'] == 'success':
                                    if resp_json['data']['resultType'] == 'vector':
                                        item_metrics['last_check_ts'] = now
                                        item_metrics['metrics'] = resp_json['data']['result']
                                        if valkey_client:
                                            await valkey_client.set(db_key, json.dumps(item_metrics))
                                            print(f"{provider_name} / {metric_name} / refreshed as '{db_key}'")
                                    else:
                                        print(f"(!) {provider_name} / {metric_name} / Response has unknown resultType: {resp_json['resultType']}")
                                else:
                                    print(f"(!) {provider_name} / {metric_name} / Response has unknown status: {resp_json['status']}")
                        except Exception as e:
                            print(f"(!) {provider_name} / {metric_name} / {str(e)}")

                    provider_metrics[provider_name][metric_name] = item_metrics
            case _:
                print(f"(!) {provider_name} / Provider type '{provider_data['type']}' is unknown.")

    return provider_metrics


async def GetStoredNodeMetrics(node_name):
    node_metrics = None
    if valkey_client:
        node_metrics = await valkey_client.get(node_name)

    if node_metrics is None:
        node_metrics = {
            'ts': 0,
            'status': 'unknown',
            'description': '',
            'history': []
        }
    else:
        node_metrics = json.loads(node_metrics)
    return node_metrics


def AppendLogFreshMetrics(history, metrics):
    if len(history) > 0:
        history.sort(key=lambda x: x['ts'], reverse=True)
        if history[0]['status'] == metrics['status']:
            return history

    history.append(metrics)
    if len(history) > 9:
        history = history[0:9]
    return history


async def StoreNodeStatus(node_name, status, description, node_metrics=None):
    if node_metrics is None:
        node_metrics = await GetStoredNodeMetrics(node_name)

    latest_metrics = {
        'ts': int(time.time()),
        'status': status,
        'description': description
    }

    node_metrics.update(latest_metrics)
    node_metrics['history'] = AppendLogFreshMetrics(node_metrics['history'], latest_metrics)

    if valkey_client:
        print('store:')
        print([node_name, json.dumps(node_metrics)])
        await valkey_client.set(node_name, json.dumps(node_metrics))


async def RefreshNodeMetrics(node_name, node_config, config, provider_metrics):
    if 'metric_source' not in node_config:
        return False

    node_metrics = await GetStoredNodeMetrics(node_name)
    update_interval = node_config['update_interval'] if 'update_interval' in node_config else config['defaults']['update_interval']

    if node_metrics['ts'] + update_interval < int(time.time()):
        value = None
        source_type, cmd = node_config['metric_source'].split('://')
        match source_type:
            case 'metrics+provider':
                path, query = cmd.split('?', 2)
                parsed_query = parse_qs(query)

                provider_name, metric_name = path.split('/', 2)
                metric_filter = parsed_query['filter'][0]
                # print([provider_name, metric_name, node_name, metric_filter])

                # current_provider_metrics = provider_metrics[provider_name]
                # metrics_obj = current_provider_metrics[metric_name]

                # TODO: get provider metrics and pass it to GetStatusByValue()

                values = []
                # for metric_row in metrics_obj['metrics']:
                #     try:
                #         if simple_eval(metric_filter, names=metric_row['metric']):
                #             values.append(metric_row['value'][1])
                #     except Exception as e:
                #         print(e)
                for metric_row in node_config['metric_data']:
                    values.append(metric_row['value'])

                value = values[0][1]  # first item has latest meterics

            case 'shell':
                proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await proc.communicate()
                if len(stderr) > 0:
                    value = stderr.decode('utf-8')
                elif 'metric_mask_re' in node_config:
                    matches = re.finditer(rf"{node_config['metric_mask_re']}", stdout.decode('utf-8'), re.MULTILINE)
                    value = [(match.group('name'), match.group('value')) for match in matches]
                else:
                    value = stdout.decode('utf-8').strip()

            case 'https' | 'http':
                try:
                    async with httpx.AsyncClient(timeout=1.0) as client:
                        response = await client.get(node_config['metric_source'], follow_redirects=True)
                        if node_config['value_source'] == 'http-code':
                            value = response.status_code
                except httpx.TimeoutException:
                    value = 408
                except httpx.RequestError:
                    value = 500
                except httpx.HTTPStatusError as exc:
                    value = exc.response.status_code
                except Exception as e:
                    print(e)
                    value = None

            case _:
                print(f"(!) Metric source '{source_type}' is unknown.")

        status, description = GetStatusByValue(value, node_config, config)
        await StoreNodeStatus(node_name, status, description, node_metrics)
        # print(json.dumps(node_metrics, indent=2))
    return


async def RefreshMetricsByConfig(config, provider_metrics, node_config=None):
    if node_config is None:
        node_config = config
    config_nodes = await CollectNodesOfCursor(node_config, provider_metrics, config['providers'])

    for k, v in config_nodes.items():
        await RefreshNodeMetrics(k, v, config, provider_metrics)
        await RefreshMetricsByConfig(config, provider_metrics, v)
    return


async def RefreshMetrics():
    global valkey_client
    global provider_metrics

    valkey_client = GetValkeyClient()

    config = GetConfig()
    provider_metrics = await RefreshProviderMetrics(config)
    await RefreshMetricsByConfig(config, provider_metrics)
    return
