import re
import yaml
from pathlib import Path

allow4web_keys = [
    r'/label$',
    r'/graph_file$',
    r'/(nodes|child_nodes)$',
    r'/(nodes|child_nodes)/[^/]+$',
]


def LoadConfig():
    with open(f"{Path(__file__).parent.parent}/config/config.yml", "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)
    return {}


def GetConfigNodeNames(config_node, deep=[]):
    node_names = []
    deep_str = '/' + '/'.join(deep)

    for k, v in config_node.items():
        if not any(re.search(pattern, f"{deep_str}/{k}") for pattern in allow4web_keys):
            continue

        if type(v) is dict:
            if len(deep) > 0:
                node_names.append(k)
            node_names.extend(GetConfigNodeNames(v, deep + [k]))

    return node_names


def GetConfig():
    return LoadConfig()
