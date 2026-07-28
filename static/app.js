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

async function LoadFile(filename) {
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

function GetChildNamesForGraph(node_info, graph_type='flowchart') {
	var node_name = []
	var nodes = node_info['child_nodes'];
	if (nodes) {
		for (const k in nodes) {
			if (nodes[k]['label'])
				node_name.push(`${mm_control.EncodeBlockName(k, graph_type)}["${nodes[k]['label']}"]`);
			else
				node_name.push(`${mm_control.EncodeBlockName(k, graph_type)}["${k}"]`);
		}
	}
	return node_name;
}

function GetDefaultGraphByConfig(node_info) {
	console.info('Create graph by config');
	var graph_lines = ['block', 'columns 7']  // no links + possible many blocks => use block-graph
	graph_lines.push(...GetChildNamesForGraph(node_info, 'block'))
	console.log(graph_lines.join("\n"));

	return graph_lines.join("\n")
}

async function LoadAndShowGraph(node_info) {
	var graph_text = await LoadFile('/graphs/' + node_info.graph_file);
	if (graph_text) {
		// readd all nodes from config to do not miss something
		graph_text += "\n\n" + GetChildNamesForGraph(node_info).join("\n");
	} else {
		graph_text = GetDefaultGraphByConfig(node_info);
	}
	console.log(graph_text);
	var svg = ShowGraph(graph_text);
	return svg;
}

function MakeBreadcrumbUI(breadcrumb) {
	var bc_node = document.querySelector('#breadcrumb OL');
	bc_node.replaceChildren();

	var names_list = [];
	for (const el of breadcrumb) {
		const label = el['label'] !== '' ? el['label'] : el['name'];
		names_list.push(el['name']);
		let path = '/';
		if (names_list.length > 1)
			path = names_list.join('/');

		if (names_list.length >= breadcrumb.length)
			bc_node.insertAdjacentHTML('beforeend', `<li><span aria-current="page">${label}</span></li>`);
		else
			bc_node.insertAdjacentHTML('beforeend', `<li><a href="${path}">${label}</a></li>`);
	}
}

function CollectHistory(child_nodes, parents=[]) {
	var history = [];
	var attention_statuses = ['warning', 'danger']
	for (const node_name in child_nodes) {
		const child_node_metric = child_nodes[node_name]['metric'];
		if (child_node_metric && child_node_metric['history']) {
			let row_nr = 0;
			for (const hst_row of child_node_metric['history']) {
				const history_item = {
					node_parents: parents,
					node_name: node_name,
					in_focus: !row_nr && attention_statuses.indexOf(hst_row['status']) >= 0,
					...hst_row
				};
				history.push(history_item);
				row_nr++;
			}
		}

		if (child_nodes[node_name]['child_nodes'])
			history.push(...CollectHistory(child_nodes[node_name]['child_nodes'], [...parents, node_name]));
	}
	return history;
}

function FillHistoryTable(node_info) {
	var history = CollectHistory(node_info['child_nodes'])
	history.sort((a, b) => b['in_focus'] != a['in_focus'] ? (b['in_focus'] - a['in_focus']) : (b['ts'] - a['ts']))

	var history_table = document.getElementById('history');
	var durationFormatter = new Intl.DurationFormat('en-US', { style: 'short' });

	const now = new Date();
	for (const hst_row of history) {
		const row_dt = new Date(hst_row['ts']*1000);
		let delta = now - row_dt;

		if (hst_row['in_focus']) {
			const delta_days = Math.floor(delta / 24*60*60*1000);
			delta %= (24*60*60*1000);
			const delta_hours = Math.floor(delta / 60*60*1000)
			delta %= (60*60*1000);
			const delta_minutes = Math.floor(delta / 60*1000)

			let time_since = durationFormatter.format({
				days: delta_days,
				hours: delta_hours,
				minutes: delta_minutes
			});
			console.log([row_dt, time_since]);
		}

		const new_row = history_table.insertRow(-1);
		new_row.insertCell(0).textContent = (new Date(hst_row['ts']*1000)).toISOString() + "\n" + hst_row['status'];
		new_row.insertCell(1).textContent = hst_row['node_name'];
		new_row.insertCell(2).textContent = hst_row['details'];

		mm_control.SetupAttention(new_row, hst_row['status']);
	}
}

function GetPreparedPathName(el_name) {
	if (el_name.indexOf('/') >= 0)
		return `base64,${btoa(el_name).replaceAll('+', '-').replaceAll('/', '_')}`
	return el_name;
}

async function MakePageByPathname(node_info) {
	// project name
	document.getElementsByTagName('H1')[0].innerText = node_info.project_name;

	// output Broadcrumb
	var pathname = []
	var breadcrumb = [{'name': '', 'label': 'Root'}];
	for (const path_el of node_info.node_deep) {
		breadcrumb.push(path_el);
		pathname.push(GetPreparedPathName(path_el['name']))
	}
	MakeBreadcrumbUI(breadcrumb);
	if (pathname.length) {
		pathname.unshift('');	// slash before path
		pathname = pathname.join('/');
	} else {
		pathname = '';
	}

	// output history table
	FillHistoryTable(node_info)

	// output graph
	if (node_info.graph_file) {
		try {
			var svg = await LoadAndShowGraph(node_info);
		} catch(e) {
			console.error(e);
		}
	}

	if (!svg) {
		// create graph by config
		var svg = await ShowGraph(GetDefaultGraphByConfig(node_info));
	}

	// add links to nodes
	var nodes = node_info['child_nodes'];
	if (nodes) {
		for (const k in nodes) {
			if ('child_nodes' in nodes[k]) {
				const el = mm_control.GetSvgNodeById(svg, k);
				console.log(`${pathname}/${GetPreparedPathName(k)}`);
				mm_control.SetupLink(el, `${pathname}/${GetPreparedPathName(k)}`);
			}
		}
	}

	svg['myConfig'] = node_info;
	return svg;
}

async function LoadNodeInfo()
{
	const node_info_text = await LoadFile('/node_info' + window.location.pathname);
	return JSON.parse(node_info_text);
}

async function RefreshMetrics(svg, node_info=null)
{
	if (!node_info)
		node_info = await LoadNodeInfo();

	if (node_info['child_nodes'])
	{
		for (const [el_name, node] of Object.entries(node_info['child_nodes'])) {
			const sv_node = mm_control.GetSvgNodeById(svg, el_name);
			if (sv_node) {
				const metric = node['metric'];
				mm_control.SetupAttention(sv_node, metric['status'], metric['details']);
			}
		}
	}

	window.setTimeout(()=>RefreshMetrics(svg), 5000);
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
const node_info = await LoadNodeInfo();
const svg = await MakePageByPathname(node_info);
RefreshMetrics(svg, node_info);

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
