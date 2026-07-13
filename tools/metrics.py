import time
import json
import re
import asyncio
import httpx
import valkey.asyncio as valkey
from tools.config import getConfig

# valkey_client = valkey.Valkey(host='valkey', port=6379, db=0)


def GetStatusByValue(value, node_config, config):
    if 'value_source' in node_config and node_config['value_source'] == 'http-code':
        return 'normal' if value == node_config['normal_level'] else 'danger'

    try:
        value = float(value)
    except:
        return 'danger'

    level_direction = node_config['level_direction'] if 'level_direction' in node_config else config['defaults']['level_direction']
    warning_level = node_config['warning_level'] if 'warning_level' in node_config else config['defaults']['warning_level']
    danger_level = node_config['danger_level'] if 'danger_level' in node_config else config['defaults']['danger_level']
    if level_direction == 'down':
        if value <= danger_level:
            return 'danger'
        if value <= warning_level:
            return 'warning'
    else:
        if value >= danger_level:
            return 'danger'
        if value >= warning_level:
            return 'warning'

    return 'normal'


async def LoadNodeMetrics(name, node_config, config):
    if 'metric_source' not in node_config:
        return False
    update_interval = node_config['update_interval'] if 'update_interval' in node_config else config['defaults']['update_interval']

    # node_metrics = await valkey_client.get(name)
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
                    matches = re.findall(rf"\b{node_config['metric_mask_re']}\b", stdout.decode('utf-8'))
                    for row in matches:
                        print(row)
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

        latest_metrics = {
            'ts': now,
            'status': GetStatusByValue(value, node_config, config),
            'value': value
        }

        # await valkey_client.set(name, json.dumps(node_metrics))
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
    config = getConfig()
    await LoadMetricsByConfig(config)
    return
