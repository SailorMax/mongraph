import re
import yaml

allow4web_keys = [
    r'/label$',
    r'/graph_file$',
    r'/(nodes|child_nodes)$',
    r'/(nodes|child_nodes)/[^/]+$',
]

config = {}


def LoadConfig():
    global config
    with open("config/config.yml", "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)


def collectWebconfig(config_node: dict = {}, deep=[]):
    if len(config_node.items()) == 0:
        config_node = config

    deep_str = '/' + '/'.join(deep)
    web_config_node = {}
    for k, v in config_node.items():
        if not any(re.search(pattern, f"{deep_str}/{k}") for pattern in allow4web_keys):
            continue

        if type(v) is dict:
            web_config_node[k] = collectWebconfig(config_node[k], deep + [k])
        else:
            web_config_node[k] = v
    return web_config_node


def getWebConfig():
    LoadConfig()
    return collectWebconfig()


if __name__ == '__main__':
    print(getWebConfig())
