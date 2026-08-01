# import sys
import mimetypes
from pathlib import Path
import falcon
import falcon.asgi

from libs.helpers import GetWebConfig
from libs.nodes import GetNodeInfo, GetNodesMetrics

# detect pytest
# is_pytest = sys.argv[0].endswith('pytest')


class MongraphResource:
    # async def on_get_config(self, req, resp):
    #     resp.media = await GetWebConfig()

    # async def on_get_metrics(self, req, resp):
    #     resp.media = await GetNodesMetrics()

    async def on_get_node_info(self, req, resp, node_path):
        resp.media = await GetNodeInfo(node_path)

    async def on_get_static(self, req, resp, file_path):
        # prepare file_path data
        if file_path == '':
            file_path = 'index.html'
            default_dir = ''
        elif file_path[0] == '/':
            file_path = file_path[1:]
            default_dir = ''
        else:
            request_path = str(req.path)
            file_path_pos = request_path.find(file_path)
            default_dir = (request_path[1:file_path_pos] if file_path_pos >= 0 else request_path[1:])

        # check access
        allow_extensions_list = [
            '.html',
            '.css',
            '.js',
            '.ico',
            '.mermaid'
        ]
        if Path(file_path).suffix not in allow_extensions_list:
            resp.text = 'Forbidden'
            resp.status_code = 403
            return

        # try to use custom file versions
        prepared_file_path = f"./static/custom/{file_path}"
        if not Path(prepared_file_path).is_file():
            prepared_file_path = f"{default_dir}{file_path}"

        # read file
        if Path(prepared_file_path).is_file():
            resp.data = Path(prepared_file_path).read_bytes()
            resp.content_type = mimetypes.guess_type(file_path)[0]
            return

        resp.text = 'Not found'
        resp.status_code = 404

    async def on_get_graph(self, req, resp, file_path):
        await self.on_get_static(req, resp, file_path=f"/config/graphs/{file_path}")

    async def on_get_node(self, req, resp, node_path):
        await self.on_get_static(req, resp, file_path='')


# init web server
app = falcon.asgi.App()

mongraph = MongraphResource()
# app.add_route('/config', mongraph, suffix='config')
# app.add_route('/metrics', mongraph, suffix='metrics')
app.add_route('/node_info/{node_path:path}', mongraph, suffix='node_info')
app.add_route('/static/{file_path:path}', mongraph, suffix='static')
app.add_route('/graphs/{file_path:path}', mongraph, suffix='graph')
app.add_route('/{node_path:path}', mongraph, suffix='node')


# start point defined in docker-compose
# here it can conflict with pytest (slow tests)
# if __name__ == '__main__':
#     uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)  # do not reload on dir changes
