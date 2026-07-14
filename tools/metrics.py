import time
import json
import re
import asyncio
import httpx
import valkey.asyncio as valkey
from urllib.parse import urlparse
from tools.config import getConfig


def getValkeyClient(config):
    try:
        parsed_uri = urlparse(config['database_uri'])
        if parsed_uri.scheme != 'valkey':
            raise ValueError(f"Unknown database type: {parsed_uri.scheme}")
        return valkey.Valkey(host=parsed_uri.hostname, port=parsed_uri.port, db=parsed_uri.path.split('/')[1])

    except ValueError as e:
        raise ValueError(f"database_uri is incorrect or not defined: {str(e)}")


def GetStatusByValue(value, node_config, config):
    status, description = 'normal', ''

    if 'value_source' in node_config and node_config['value_source'] == 'http-code':
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
                if value <= warning_level:
                    status = 'warning'
            else:
                if value >= danger_level:
                    status = 'danger'
                if value >= warning_level:
                    status = 'warning'
        except:
            status = 'danger'

    return status, description


async def LoadNodeMetrics(name, node_config, config):
    if 'metric_source' not in node_config:
        return False
    update_interval = node_config['update_interval'] if 'update_interval' in node_config else config['defaults']['update_interval']

    if valkey_client:
        node_metrics = await valkey_client.get(name)

    node_metrics = None
    if node_metrics is None:
        node_metrics = {
            'last_check_ts': 0,
            'metrics_log': []
        }
    else:
        node_metrics = json.loads(node_metrics)

    now = int(time.time())
    if node_metrics['last_check_ts'] + update_interval < now:
        print(node_config)
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
                req = None
                try:
                    async with httpx.AsyncClient(timeout=1.0) as client:
                        req = await client.get(node_config['metric_source'], follow_redirects=True)
                        if node_config['value_source'] == 'http-code':
                            value = req.status_code
                except httpx.TimeoutException:
                    value = 408
                except httpx.RequestError:
                    value = 500
                except httpx.HTTPStatusError as exc:
                    value = exc.response.status_code

        status, description = GetStatusByValue(value, node_config, config)
        latest_metrics = {
            'ts': now,
            'status': status,
            'description': description
        }

        if valkey_client:
            await valkey_client.set(name, json.dumps(node_metrics))
        print(latest_metrics)
    return


async def LoadMetricsByConfig(config, node_config=None):
    if node_config is None:
        node_config = config
    config_nodes = node_config['nodes'] if 'nodes' in node_config else node_config['child_nodes'] if 'child_nodes' in node_config else {}
    for k, v in config_nodes.items():
        await LoadNodeMetrics(k, v, config)
        await LoadMetricsByConfig(config, v)
    return


async def RefreshMetrics():
    global valkey_client

    config = getConfig()
    valkey_client = getValkeyClient(config)

    await LoadMetricsByConfig(config)
    return
