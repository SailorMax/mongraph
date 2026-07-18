import valkey.asyncio as valkey
from urllib.parse import urlparse
from libs.config import GetConfig


def GetValkeyClient():
    config = GetConfig()
    try:
        parsed_uri = urlparse(config['database_uri'])
        if parsed_uri.scheme != 'valkey':
            raise ValueError(f"Unknown database type: {parsed_uri.scheme}")
        return valkey.Valkey(host=parsed_uri.hostname, port=parsed_uri.port, db=parsed_uri.path.split('/')[1])

    except ValueError as e:
        raise ValueError(f"database_uri is incorrect or not defined: {str(e)}")
