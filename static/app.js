import * as mm_control from './mermaid-control.js';

// https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.16.0/mermaid.min.js
// import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
// import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
// https://cdn.jsdelivr.net/npm/mermaid@latest/dist/
mermaid.initialize({
	startOnLoad: false,
	theme: 'default',
	securityLevel: 'strict'
});

const config_text = await loadFile('config');
const config = JSON.parse(config_text);


async function drawDiagram(graphDefinition)
{
	const outputBox = document.getElementById('graph');
	try {
		// Generate a unique ID for the SVG injection
		const id = 'mermaid-' + Math.floor(Math.random() * 10000);

		// Render the diagram to an SVG string
		const { diagramType, svg } = await mermaid.render(id, graphDefinition);

		// Insert the SVG into your DOM
		outputBox.innerHTML = svg;
		outputBox.childNodes[0]['myDiagramType'] = diagramType;
		return outputBox.childNodes[0];
	} catch (error) {
		console.error("Mermaid rendering failed:", error);
	}
}

async function loadFile(filename) {
	try {
		const response = await fetch(filename);
		if (!response.ok)
			throw new Error(`Error status: ${response.status}`);
		return await response.text();

	} catch (error) {
		console.error(`Failed to load graph ${filename}:`, error);
	}
	return null
}

async function ShowGraph(graph_text) {
	var svg = await drawDiagram(graph_text);
	return svg;
}

async function LoadAndShowGraph(filename) {
	var graph_text = await loadFile('config/graphs/' + filename);
	if (!graph_text)
		return null;
	var svg = ShowGraph(graph_text);
	return svg;
}

function MakeBreadcrumbUI(breadcrumb) {
	var bc_node = document.querySelector('#breadcrumb OL');
	bc_node.replaceChildren();

	var names_list = [''];
	for (const el of breadcrumb) {
		const label = el['label'] !== '' ? el['label'] : el['name'];
		names_list.push(el['name']);
		const path = names_list.join('/');
		if (names_list.length > breadcrumb.length)
			bc_node.insertAdjacentHTML('beforeend', `<li><span aria-current="page">${label}</span></li>`);
		else
			bc_node.insertAdjacentHTML('beforeend', `<li><a href="${path}">${label}</a></li>`);
	}
}

async function MakePageByPathname(pathname, config) {
	// find current node config
	var breadcrumb = [{'name': '', 'label': 'Root'}];
	var path_els = pathname.split('/').slice(1);
	for (const path_el of path_els) {
		if (path_el === '')
			break;

		if (config['child_nodes'] && path_el in config['child_nodes'])
			config = config['child_nodes'][path_el];
		else if (config['nodes'] && path_el in config['nodes'])
			config = config['nodes'][path_el];
		else
			break;

		breadcrumb.push({'name': path_el, 'label': config['label']});
	}

	// output Broadcrumb
	MakeBreadcrumbUI(breadcrumb);

	// output graph
	if (config.graph_file) {
		try {
			var svg = await LoadAndShowGraph(config.graph_file);
		} catch(e) {
			console.error(e);
		}
	}

	if (!svg) {
		// create graph by config
		console.info('Create graph by config');
		var graph_lines = ['block', 'columns 7']  // no links + possible many blocks => use block-graph
		var nodes = ('nodes' in config ? config['nodes'] : config['child_nodes']);
		if (nodes) {
			for (const k in nodes) {
				if (nodes[k]['label'])
					graph_lines.push(`${k.replaceAll('-', '≡')}["${nodes[k]['label']}"]`);
				else
					graph_lines.push(`${k.replaceAll('-', '≡')}["${k}"]`);
			}
		}
		var svg = await ShowGraph(graph_lines.join("\n"));
	}

	// add links to nodes
	var nodes = ('nodes' in config ? config['nodes'] : config['child_nodes']);
	if (nodes) {
		for (const k in nodes) {
			if ('child_nodes' in nodes[k]) {
				const el = mm_control.GetSvgNodeById(svg, k);
				mm_control.SetupLink(el, `${pathname}${k}`);
			}
		}
	}

	svg['myConfig'] = config;
	return svg;
}

function AssignMetricsToConfig(metrics, config)
{
	var abnormal_statuses = {};
	var config_nodes = ('nodes' in config ? config['nodes'] : config['child_nodes']);
	if (config_nodes) {
		for (const k in config_nodes) {
			if (metrics[k]) {
				config_nodes[k]['latest_metrics'] = metrics[k];
				if (['warning', 'danger'].indexOf(metrics[k]['status']) >= 0)
					abnormal_statuses[k] = metrics[k];
			}
			const child_abnormal_metrics = AssignMetricsToConfig(metrics, config_nodes[k]);
			config_nodes[k]['child_abnormal_metrics'] = child_abnormal_metrics;
			Object.assign(abnormal_statuses, child_abnormal_metrics);
		}
	}
	return abnormal_statuses;
}

async function RefreshMetrics(svg, config)
{
	var metrics_text = await loadFile('metrics');
	if (!metrics_text)
		return null;

	var metrics = JSON.parse(metrics_text);
	if (metrics)
	{
		const abnormal_statuses = AssignMetricsToConfig(metrics, config);
		if (Object.keys(abnormal_statuses).length > 0) {
			// additional highlight the problem in the project
		}
		for (const el_name in metrics) {
			const node = mm_control.GetSvgNodeById(svg, el_name);
			if (node) {
				mm_control.SetupAttention(node, metrics[el_name].status, metrics[el_name].value);
			}
		}

		var config_nodes = ('nodes' in svg['myConfig'] ? svg['myConfig']['nodes'] : svg['myConfig']['child_nodes']);
		if (config_nodes) {
			for (const k in config_nodes) {
				if (!config_nodes[k]['latest_metrics'] && config_nodes[k]['child_abnormal_metrics']) {
					const node = mm_control.GetSvgNodeById(svg, k);
					if (node) {
						const child_abnormal_metrics = config_nodes[k]['child_abnormal_metrics'];
						const status2idx = {
							'normal': 0,
							'warning': 1,
							'danger': 2,
						}
						const sorted_abnormal_keys = Object.keys(child_abnormal_metrics).sort(
							(a,b) => status2idx[child_abnormal_metrics[b]['status']]-status2idx[child_abnormal_metrics[a]['status']]
						);
						let worst_status = 'warning';
						let abnormal_metrics = [];
						for (const name of sorted_abnormal_keys) {
							if (status2idx[worst_status] < status2idx[child_abnormal_metrics[name]['status']])
								worst_status = child_abnormal_metrics[name]['status'];
							abnormal_metrics.push(`${name}: ${child_abnormal_metrics[name]['value']}`);
						}
						mm_control.SetupAttention(node, worst_status, abnormal_metrics.join('\n'));
					}
				}
			}
		}
	}

	window.setTimeout(()=>RefreshMetrics(svg, config), 5000);
}

// window.addEventListener('popstate', async function(event) {
//     // Check if state data exists
// 	console.log(event.state);
// 	console.log(window.location.pathname);
//     if (event.state) {
// 		await MakePageByPathname(window.location.pathname, config);
//     }
// });

// 1. Initial draw on page load
const svg = await MakePageByPathname(window.location.pathname, config)
RefreshMetrics(svg, config);

/*
var el = mm_control.GetSvgNodeById(svg, 'test1')
mm_control.SetupAttention(el, 'warning');
var el = mm_control.GetSvgNodeById(svg, 'test2')
mm_control.SetupAttention(el, 'danger', "something wrong!");
var el = mm_control.GetSvgNodeById(svg, 'test3')
mm_control.SetupAttention(el, 'normal');


var els = mm_control.GetSvgConnectionById(svg, 'L_test1_test2')
mm_control.SetupAttention(els, 'warning');
var els = mm_control.GetSvgConnectionById(svg, 'L_test2_test3')
mm_control.SetupAttention(els, 'danger', 'something wrong!');
//mm_control.SetupAttention(els);
*/
/*
console.log(el);
var box = el.querySelector('rect.label-container')
box.style.fill = "red";
var label = el.querySelector('span.nodeLabel')
label.setAttribute('title', 'zzzzzzzzzz');
*/
/*
// 2. Change text dynamically and re-render
function updateBlockText() {
	const updatedGraph = `
	flowchart TD
		A[Brand New Text Here] --> B(Step 2)
	`;

	// Re-run the draw function to update the block text in the DOM
	drawDiagram(updatedGraph);
}
*/
