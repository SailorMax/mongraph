import time
import json
import re
import asyncio
import httpx
import valkey.asyncio as valkey
from urllib.parse import urlparse, parse_qs
from libs.config import getConfig


valkey_client = None
provider_metrics = {}


def getValkeyClient(config):
    try:
        parsed_uri = urlparse(config['database_uri'])
        if parsed_uri.scheme != 'valkey':
            raise ValueError(f"Unknown database type: {parsed_uri.scheme}")
        return valkey.Valkey(host=parsed_uri.hostname, port=parsed_uri.port, db=parsed_uri.path.split('/')[1])

    except ValueError as e:
        raise ValueError(f"database_uri is incorrect or not defined: {str(e)}")


def GetStatusByValue(value, node_config, config):
    status, description = 'unknown', ''

    if value is None:
        description = 'Could not receive data'
    elif 'value_source' in node_config and node_config['value_source'] == 'http-code':
        status = 'normal' if value == node_config['normal_level'] else 'danger'
        description = f"{node_config['value_source']}: {value}"
    else:
        level_direction = node_config['level_direction'] if 'level_direction' in node_config else config['defaults']['level_direction']
        warning_level = node_config['warning_level'] if 'warning_level' in node_config else config['defaults']['warning_level']
        danger_level = node_config['danger_level'] if 'danger_level' in node_config else config['defaults']['danger_level']
        measurement = node_config['measurement'] if 'measurement' in node_config else config['defaults']['measurement']

        if type(value) is list:
            values = sorted(value, key=lambda item: float(item[1]), reverse=(level_direction != 'down'))
            value = values[0][1]
            description = "\n".join([f"{float(item[1]): >14,.2f}{measurement}  {item[0]}" for item in values])
        else:
            description = value + measurement

        try:
            value = float(value)
            if level_direction == 'down':
                if value <= danger_level:
                    status = 'danger'
                elif value <= warning_level:
                    status = 'warning'
                else:
                    status = 'normal'
            else:
                if value >= danger_level:
                    status = 'danger'
                elif value >= warning_level:
                    status = 'warning'
                else:
                    status = 'normal'
        except:
            status = 'danger'

    return status, description

def AppendLogFreshMetrics(logs, metrics):
    if len(logs) > 0:
        logs.sort(key=lambda x: x['ts'], reverse=True)
        if logs[0]['status'] == metrics['status']:
            return logs

    logs.append(metrics)
    if len(logs) > 9:
        logs = logs[0:9]
    return logs


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
                    item_metrics = await valkey_client.get(db_key)
                    if item_metrics is None:
                        item_metrics = {
                            'last_check_ts': 0,
                            'metrics': []
                        }
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
                                    else:
                                        print(f"{provider_name} / {metric_name} / Response has unknown resultType: {resp_json['resultType']}")
                                else:
                                    print(f"{provider_name} / {metric_name} / Response has unknown status: {resp_json['status']}")
                        except Exception as e:
                            print(f"{provider_name} / {metric_name} / {str(e)}")

                    provider_metrics[provider_name][metric_name] = item_metrics
            case _:
                print(f"(!) {provider_name} / Provider type '{provider_data['type']}' is unknown.")

    return provider_metrics


async def RefreshNodeMetrics(name, node_config, config):
    if 'metric_source' not in node_config:
        return False
    update_interval = node_config['update_interval'] if 'update_interval' in node_config else config['defaults']['update_interval']

    node_metrics = None
    if valkey_client:
        node_metrics = await valkey_client.get(name)

    if node_metrics is None:
        node_metrics = {
            'last_check_ts': 0,
            'last_check_status': 'unknown',
            'metrics_log': []
        }
    else:
        node_metrics = json.loads(node_metrics)

    now = int(time.time())
    if node_metrics['last_check_ts'] + update_interval < now:
        latest_metrics = None
        value = None
        source_type, cmd = node_config['metric_source'].split('://')
        match source_type:
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
        latest_metrics = {
            'ts': now,
            'status': status,
            'description': description
        }

        node_metrics['last_check_ts'] = latest_metrics['ts']
        node_metrics['last_check_status'] = latest_metrics['status']
        node_metrics['metrics_log'] = AppendLogFreshMetrics(node_metrics['metrics_log'], latest_metrics)

        if valkey_client:
            await valkey_client.set(name, json.dumps(node_metrics))
        # print(json.dumps(node_metrics, indent=2))
    return


def GetNodesOfCursor(config_cursor, provider_metrics, config):
    if 'nodes' in config_cursor:
        nodes = config_cursor['nodes']
    elif 'child_nodes' in config_cursor:
        nodes = config_cursor['child_nodes']
    else:
        nodes = {}

    if 'child_nodes_from_provider' in config_cursor:
        for provider_nodes_uri in config_cursor['child_nodes_from_provider']:
            parsed_uri = urlparse(provider_nodes_uri)
            parsed_query = parse_qs(parsed_uri.query)
            print(parsed_uri)
            print(parsed_query)
            # TODO: generate virtual childs and collect data for them from provider's data
            match parsed_uri.scheme:
                case 'provider':
                    if parsed_uri.netloc in config['providers']:
                        provider_config = config['providers'][parsed_uri.netloc]
                        for provider_metric_name in provider_config:
                            print(provider_metric_name)
                            print(provider_metrics)
                            # filter data
                            # data in global provider_metrics
                    else:
                        print(f"(!) Provider '{parsed_uri.netloc}' not found from uri {provider_nodes_uri}")

    return nodes

async def RefreshMetricsByConfig(config, provider_metrics, node_config=None):
    if node_config is None:
        node_config = config
    config_nodes = GetNodesOfCursor(node_config, provider_metrics, config)
    for k, v in config_nodes.items():
        await RefreshNodeMetrics(k, v, config)
        await RefreshMetricsByConfig(config, provider_metrics, v)
    return


async def RefreshMetrics():
    global valkey_client
    global provider_metrics

    config = getConfig()
    valkey_client = getValkeyClient(config)

    provider_metrics = await RefreshProviderMetrics(config)
    await RefreshMetricsByConfig(config, provider_metrics)
    return
