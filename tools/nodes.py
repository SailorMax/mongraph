def getNodesMetrics():
    return {
        'app-server-cpu': {'status': 'normal', 'value': '70%'},
        'app-server-memory': {'status': 'warning', 'value': '95%'},
        'app-server-disk-free': {'status': 'danger', 'value': '500MB'},
        'app-valkey': {'status': 'normal', 'value': 'http-code: 200'},
        'internet': {'status': 'normal', 'value': 'http-code: 200'},
    }
