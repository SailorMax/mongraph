import time
import json
import re
import asyncio
import httpx
import libs.config as cfg
import libs.db as db
import libs.helpers as helpers
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from simpleeval import simple_eval

status2idx = {
    'unknown': -1,
    'normal': 0,
    'warning': 1,
    'danger': 2,
}
status_pripority_names = list(reversed(list(status2idx.keys())[1:])) or []  # without 'unknown'

provider_metrics = {}


def GetUserFriendlyValue(value, levels_config):
    measurement = levels_config['measurement'] if 'measurement' in levels_config else ''
    try:
        if float(value) >= 1000:
            return f"{float(value): >14,.2f}{measurement}"
    except:
        return f"?{measurement}"

    return f"{value}{measurement}"


def GetStatusByValue(value, node_config, config):
    status, details = 'unknown', ''
    levels_config = node_config['levels'] if 'levels' in node_config else config['defaults']['levels']

    if not value:
        details = 'Could not detect status. Value is empty.'
    else:
        levels_config['direction'] = 'up'
        if ('danger' in levels_config
            and re.search(r'(value\s*<=?|>=?\s*value)', levels_config['danger'])
            ):
            levels_config['direction'] = 'down'

        # sort values and get `worst_value`
        values = []
        worst_value = value
        if type(value) is list:
            values = sorted(value, key=lambda item: float(item[0]), reverse=(levels_config['direction'] != 'down'))
            worst_value = values[0]  # take worst value for status

        # collect details from sorted `values`
        if len(worst_value) > 1:  # values has names
            details = "\n".join([f"{GetUserFriendlyValue(item[0], levels_config)}  {item[1]}" for item in values])
        else:
            details = "\n".join([GetUserFriendlyValue(item[0], levels_config) for item in values])
        # get value from worst_value (without names)
        worst_value = worst_value[0]

        # prepare `worst_value` to calcs
        try:
            worst_value = int(worst_value)
        except Exception:
            try:
                worst_value = float(worst_value)
            except Exception:
                pass  # leave as is

        # prepare details for single value
        if len(values) == 1:
            details = details.strip()

        # levels based on normal
        if 'normal' in levels_config and levels_config['normal']:
            try:
                status = 'normal' if simple_eval(levels_config['normal'], names={'value': worst_value}) else 'danger'
            except Exception as e:
                print(e)
                status = 'danger'

            if 'value_source' in node_config:
                details = f"{node_config['value_source']}: {worst_value}"
            elif worst_value != '':
                details = f"{worst_value}"
            else:
                details = f"value: {worst_value}"

            if status2idx[status] > 0:
                if status in levels_config:
                    details += f"\n({status}: {levels_config[status]})"
                else:
                    details += f"\n(normal: {levels_config['normal']})"
        # levels based on danger/warning
        else:
            try:
                status = 'normal'
                for level_name in status_pripority_names:
                    if (level_name in levels_config
                        and type(levels_config[level_name]) is str
                        and simple_eval(levels_config[level_name], names={'value': worst_value})
                        ):
                        status = level_name
                        break
            except Exception as e:
                print(e)
                status = 'danger'

            if status2idx[status] > 0:
                details += f"\n({status}: {levels_config[status]})"

    return status, details


async def RefreshProviderMetrics(config):
    now = int(time.time())
    provider_metrics = {}
    providers = config['providers']
    for provider_name, provider_cfg in providers.items():
        if not provider_cfg or 'type' not in provider_cfg:
            print(f"(!) Provider '{provider_name}' has not 'type' attribute.")
            continue

        provider_metrics[provider_name] = {}
        match provider_cfg['type']:
            case 'plaintext':
                # check update interval
                db_key = f"providers / {provider_name}"
                provider_stored_data = await db.GetValueByKey(db_key)
                if provider_stored_data is None:
                    provider_stored_data = {
                        'last_check_ts': 0,
                    }
                else:
                    provider_stored_data = json.loads(provider_stored_data)
                update_interval = provider_cfg.get('update_interval', config['defaults']['update_interval'])
                if provider_stored_data['last_check_ts'] + update_interval < now:
                    continue
                else:
                    provider_stored_data['last_check_ts'] = now
                    await db.SetValueByKey(db_key, provider_stored_data)

                # collect raw metrics
                raw_metrics = []
                metric_rows_cursor = MetricSourceRowsGenerator(provider_cfg)
                async for row_values in metric_rows_cursor:
                    if type(row_values) is dict:
                        raw_metrics.append(row_values)
                    else:
                        raw_metrics.append({'value': row_values})

                # group metrics
                for metric_name, metric_cfg in provider_cfg['metrics'].items():
                    # load old metrics
                    db_key = f"providers / {provider_name} / {metric_name}"
                    item_metrics = await db.GetValueByKey(db_key)
                    if item_metrics is None:
                        item_metrics = {
                            'last_check_ts': 0,
                            'metrics': []
                        }
                    else:
                        item_metrics = json.loads(item_metrics)

                    # refresh
                    metric_source = metric_cfg.get('metric_source', {})
                    values_list = []
                    for row_data in raw_metrics:
                        value = FilterMetricValue(row_data, metric_source)
                        if value:
                            values_list.append(value)
                    print(metric_name)
                    print(values_list)


            case 'prometeus':
                provider_base_url = provider_cfg['base_url']
                for metric_name, metric_cfg in provider_cfg['metrics'].items():
                    # load old metrics
                    db_key = f"providers / {provider_cfg['type']} / {metric_name}"
                    item_metrics = await db.GetValueByKey(db_key)
                    if item_metrics is None:
                        item_metrics = {
                            'last_check_ts': 0,
                            'metrics': []
                        }
                    else:
                        item_metrics = json.loads(item_metrics)

                    # refresh
                    update_interval = metric_cfg.get('update_interval', config['defaults']['update_interval'])
                    if item_metrics['last_check_ts'] + update_interval < now:
                        try:
                            async with httpx.AsyncClient(timeout=3.0) as client:
                                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                                content = f"query={metric_cfg['query']}"
                                response = await client.post(provider_base_url, headers=headers, content=content, follow_redirects=True)
                                resp_json = response.json()
                                if resp_json['status'] == 'success':
                                    if resp_json['data']['resultType'] == 'vector':
                                        item_metrics['last_check_ts'] = now
                                        item_metrics['metrics'] = resp_json['data']['result']
                                        await db.SetValueByKey(db_key, json.dumps(item_metrics))
                                        print(f"{provider_name} / {metric_name} / refreshed as '{db_key}'")
                                    else:
                                        print(f"(!) {provider_name} / {metric_name} / Response has unknown resultType: {resp_json['resultType']}")
                                else:
                                    print(f"(!) {provider_name} / {metric_name} / Response has unknown status: {resp_json['status']}")
                        except Exception as e:
                            print(f"(!) {provider_name} / {metric_name} / {str(e)}")

                    provider_metrics[provider_name][metric_name] = item_metrics
            case _:
                print(f"(!) {provider_name} / Provider type '{provider_cfg['type']}' is unknown.")

    return provider_metrics


async def GetStoredNodeMetrics(node_name):
    node_metrics = await db.GetValueByKey(node_name)
    if node_metrics is None:
        node_metrics = {
            'ts': 0,
            'status': 'unknown',
            'details': '',
            'history': []
        }
    else:
        node_metrics = json.loads(node_metrics)

    return node_metrics


def AppendLogFreshMetrics(history, metrics):
    if len(history) > 0:
        history.sort(key=lambda x: x['ts'], reverse=True)
        if history[0]['status'] == metrics['status']:
            # actual values do not put in history to do not duplicate statuses + to see real history values between statuses
            return history

    history.insert(0, metrics)  # add to begin of list
    if len(history) > 9:  # history limit
        history = history[0:9]
    return history


async def NotifyAboutNewStatus(node_name, node_metrics, config):
    if 'notifications' in config:
        last_metric = node_metrics['history'][0]
        delay = config.get('delay', 0)

        if (not last_metric.get('notified', False)
            and status2idx[node_metrics['status']] > 0
            and last_metric['ts'] + delay < int(time.time())
        ):
            print('Notify about new status:')
            status2prefix = {
                'normal': '😌',   # (-)
                'warning': '⚠️',  # (!?)
                'danger': '🔥'    # (!)
            }
            msg_prefix = status2prefix[node_metrics['status']]

            message = f"{msg_prefix} {node_name} in {node_metrics['status']}: {node_metrics['details']}"
            print(message)

            recipients = config.get('recipients', [])
            for recipient in recipients:
                recipient_params = urlparse(recipient)
                recipient_type_prefix, recipient_type = recipient_params.netloc.split('+', 1)
                recipient_args = parse_qs(recipient_params.query)

                match recipient_type:
                    case 'mailto':
                        try:
                            email = EmailMessage()
                            email["Subject"] = message.split("\n", 1)[0]
                            email["From"] = recipient_args["from"]
                            email["To"] = recipient_args["to"]
                            email.set_content(message)

                            if status2idx[node_metrics['status']] > 0:
                                email["X-Priority"] = "1"
                                email["X-MSMail-Priority"] = "High"       # For Microsoft Outlook/Exchange clients
                                email["Importance"] = "High"              # General standard text classification

                            with smtplib.SMTP_SSL(recipient_params.hostname, recipient_params.port) as server:
                                if recipient_type_prefix == 'tls':
                                    server.starttls()
                                server.login(recipient_params.username, recipient_params.password)
                                server.send_message(email)

                            print("sent")
                            # node_metrics['history'][0]['notified'] = True
                        except Exception as e:
                            print(f"(!) Failed to send email. Error: {e}")

                    case 'shell':
                        cmd = recipient.split('://', maxsplit=1)[1]
                        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        stdout, stderr = await proc.communicate()
                        if len(stderr) > 0:
                            print(f"(!) {stderr.decode('utf-8')}")
                        elif await proc.wait() != 0:
                            print(f"(!) Failed send notification via: {cmd}")

                    case _:
                        print(f"(!) Recipient type '{recipient_type}' is unknown.")

    return node_metrics


async def StoreNodeStatus(node_name, status, details, node_metrics, config):

    # latest data separately to do not duplicate same status in history
    latest_metrics = {
        'ts': int(time.time()),
        'status': status,
        'details': details
    }

    node_metrics.update(latest_metrics)
    node_metrics['history'] = AppendLogFreshMetrics(node_metrics['history'], latest_metrics)

    node_metrics = await NotifyAboutNewStatus(node_name, node_metrics, config)

    # print('store:')
    # print([node_name, json.dumps(node_metrics)])
    stored = await db.SetValueByKey(node_name, json.dumps(node_metrics))
    return stored, node_metrics


def GetNodeLevels(node_config, config):
    if 'levels' in node_config:
        return node_config['levels']

    data_source = ''
    if type(node_config['metric_source']) is str:
        data_source = node_config['metric_source']
    else:
        data_source = node_config['metric_source']['data_source']

    source_type, cmd = data_source.split('://', maxsplit=1)
    match source_type:
        case 'metrics+provider':
            path = cmd.split('?', 2)[0]
            provider_name, metric_name = path.split('/', 2)
            provider_metric_config = config['providers'][provider_name]['metrics'][metric_name]
            if 'levels' in provider_metric_config:
                return provider_metric_config['levels']

    return config['defaults']['levels']


def Datetime2Ts(dt_str, metric_source):
    # https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
    dt_formats = [
        "%d-%m-%Y %H:%M:%S",    # 31-01-2026
        "%Y-%m-%d %H:%M:%S",    # 2026-01-31
        "%d/%m/%Y %H:%M:%S",    # 31/01/2026
        "%Y/%m/%d %H:%M:%S",    # 2026/01/31
        "%d %B %Y %H:%M:%S",    # 31 January 2026
        "%B %d, %Y %H:%M:%S",   # January 31, 2026
        "%b %d %H:%M:%S",       # Jan 31
    ]
    if 'datetime_format' in metric_source:
        dt_formats = [metric_source['datetime_format']]

    for fmt in dt_formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue

    print('(!) Unknown format of datetime: dt_str')
    return None


def FilterMetricValue(orig_value, metric_source):
    if type(metric_source) is str:
        return orig_value

    mask_re = metric_source.get('mask_re', None)
    rows_filter = metric_source.get('rows_filter', None)
    named_values = {}

    if mask_re:
        match = re.search(rf"{mask_re}", orig_value)
        if match:
            named_values = match.groupdict()

    if rows_filter:
        if 'value' not in named_values:
            named_values['value'] = orig_value
        funcs = {
            'now': lambda: int(time.time()),
            'timestamp': lambda dt: Datetime2Ts(dt, metric_source),
        }

        try:
            if not simple_eval(rows_filter, names=named_values, functions=funcs):
                return None
        except Exception as e:
            print(e)
            return None

    if named_values:
        return named_values
    return orig_value


async def MetricSourceRowsGenerator(node_config):
    metric_source = node_config['metric_source']
    data_source = metric_source
    if type(metric_source) is dict:
        data_source = metric_source['data_source']
    else:
        metric_source = {'data_source': metric_source}

    source_type, cmd = data_source.split('://', maxsplit=1)
    match source_type:
        case 'metrics+provider':
            value = FilterMetricValue(node_config['metric_data'][0]['value'][1], metric_source)  # first item has latest metrics
            yield value

        case 'shell':
            proc = await asyncio.create_subprocess_shell(cmd,
                                                         stdout=asyncio.subprocess.PIPE,
                                                         stderr=asyncio.subprocess.PIPE
                                                         )
            if 'value_source' in node_config and node_config['value_source'] == 'exit-code':
                yield await proc.wait()
            else:
                while True:
                    if not proc.stdout:
                        break

                    row = await proc.stdout.readline()
                    if not row:  # EOF
                        break

                    value = FilterMetricValue(row.decode('utf-8').rstrip(), metric_source)
                    if value:
                        yield value

                _, stderr = await proc.communicate()
                if len(stderr) > 0:
                    yield stderr.decode('utf-8')

        case 'https' | 'http':
            value_source = node_config.get('value_source', 'response')
            try:
                request_timeout = metric_source.get('timeout', 1)
                async with httpx.AsyncClient(timeout=request_timeout) as client:
                    async with client.stream("GET", data_source, follow_redirects=True) as response:
                        if value_source == 'http-code':
                            yield response.status_code
                        else:
                            async for row in response.aiter_lines():
                                value = FilterMetricValue(row.rstrip(), metric_source)
                                if value:
                                    yield value
            except httpx.TimeoutException:
                if value_source == 'http-code':
                    yield 408
                else:
                    print(f"(!) {data_source}: timeout")
            except httpx.RequestError as e:
                if value_source == 'http-code':
                    yield 500
                else:
                    print(f"(!) {str(e)}")
            except httpx.HTTPStatusError as e:
                if value_source == 'http-code':
                    yield e.response.status_code
                else:
                    print(f"(!) {str(e)}")
            except Exception as e:
                print(f"(!) {str(e)}")

        case 'file':
            try:
                with open(cmd, "r") as file:
                    for row in file:
                        value = FilterMetricValue(row, metric_source)
                        if value:
                            yield value

            except Exception as e:
                print(f"(!) {str(e)}")

        case _:
            print(f"(!) Metric source '{source_type}' is unknown.")
    return


async def RefreshNodeMetrics(node_name, node_config, config, provider_metrics):
    if 'metric_source' not in node_config:
        return False

    node_metrics = await GetStoredNodeMetrics(node_name)
    update_interval = node_config['update_interval'] if 'update_interval' in node_config else config['defaults']['update_interval']

    if node_metrics['ts'] + update_interval < int(time.time()):
        if 'levels' not in node_config:
            node_config['levels'] = GetNodeLevels(node_config, config)

        values_rows = []
        metric_rows_cursor = MetricSourceRowsGenerator(node_config)
        async for row in metric_rows_cursor:
            if type(row) is dict:
                values_rows.append((row.get('value', ''), row.get('name', '')))
            else:
                values_rows.append((row,))
        value = values_rows

        status, details = GetStatusByValue(value, node_config, config)
        stored, node_metrics = await StoreNodeStatus(node_name, status, details, node_metrics, config)
        # print(json.dumps(node_metrics, indent=2))

    return True


async def RefreshMetricsByConfig(config, provider_metrics, node_config=None):
    if node_config is None:
        node_config = config
    config_nodes = await helpers.CollectNodesOfCursor(node_config, provider_metrics, config['providers'])

    for k, v in config_nodes.items():
        await RefreshNodeMetrics(k, v, config, provider_metrics)
        await RefreshMetricsByConfig(config, provider_metrics, v)
    return


async def RefreshMetrics():
    global provider_metrics

    config = cfg.GetConfig()
    provider_metrics = await RefreshProviderMetrics(config)
    await RefreshMetricsByConfig(config, provider_metrics)
    return
