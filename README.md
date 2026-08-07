# IN DEVELOPMENT

# Mongraph
Monitor infrastructure nodes and visualize it as graph

## How to start
1. setup `config/config.yml`
2. (optional) setup `static/graphs/root.mermaid` and other mermaid-files based on links from config-file
2. start the server by `docker compose up`
3. open in browser

### Supported chart types
- flowchart
- block

### config:

#### `metric_source`-block description
- `data_source`: url to source
- `request_timeout`
- `update_interval`: to do not too frequently
- `mask_re`: perl regular expression with possible to extract: `datetime`, `name`, `value`, `location` and `details`
- `datetime_format`: datetime pattern
- `rows_filter`: condition
