import valkey.asyncio as valkey
from urllib.parse import urlparse
from libs.config import GetConfig

valkey_client = None


def GetValkeyClient():
    config = GetConfig()
    try:
        parsed_uri = urlparse(config['database_uri'])
        if parsed_uri.scheme != 'valkey':
            raise ValueError(f"Unknown database type: {parsed_uri.scheme}")
        return valkey.Valkey(host=parsed_uri.hostname, port=parsed_uri.port, db=parsed_uri.path.split('/')[1])

    except ValueError as e:
        raise ValueError(f"database_uri is incorrect or not defined: {str(e)}")


async def GetValueByKey(key):
    global valkey_client
    if valkey_client is None:
        valkey_client = GetValkeyClient()

    try:
        return await valkey_client.get(key)
    except:
        # second try
        valkey_client = GetValkeyClient()
        return await valkey_client.get(key)


async def SetValueByKey(key, value):
    global valkey_client
    if valkey_client is None:
        valkey_client = GetValkeyClient()

    try:
        return await valkey_client.set(key, value)
    except:
        # second try
        valkey_client = GetValkeyClient()
        return await valkey_client.get(key, value)
