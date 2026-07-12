# import sys
import mimetypes
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from tools.config import getWebConfig
from tools.nodes import getNodesMetrics

# detect pytest
# is_pytest = sys.argv[0].endswith('pytest')

# init web server
app = FastAPI()


@app.get('/config')
async def get_config():
    return getWebConfig()


@app.get('/metrics')
async def get_nodes_metrics():
    return getNodesMetrics()


@app.get('/static/{file_path:path}')
async def get_static(file_path: str, request: Request):
    default_container = './static/'
    if request.url.path[:8] != '/static/':
        default_container = './'

    prepared_file_path = f"./static/custom/{file_path}"
    if not Path(prepared_file_path).is_file():
        prepared_file_path = f"{default_container}{file_path}"

    if Path(prepared_file_path).is_file():
        content = Path(prepared_file_path).read_text()
        return Response(content=content, media_type=mimetypes.guess_type(file_path)[0])

    return Response(content='Not found', status_code=404)


@app.get('/{node_path:path}')
async def index_html(request: Request):
    return await get_static(file_path='index.html', request=request)


# start point defined in docker-compose
# here it can conflict with pytest (slow tests)
# if __name__ == '__main__':
#     uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)  # do not reload on dir changes
