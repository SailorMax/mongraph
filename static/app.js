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

async function LoadAndShowGraph(filename) {
	var graph_text = await LoadFile('/graphs/' + filename);
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

async function MakePageByPathname(node_info) {
	// output Broadcrumb
	var pathname = []
	var breadcrumb = [{'name': '', 'label': 'Root'}];
	for (const path_el of node_info.node_deep) {
		breadcrumb.push(path_el);
		pathname.push(path_el['name'])
	}
	MakeBreadcrumbUI(breadcrumb);
	pathname = '/' + pathname.join('/')

	// output graph
	if (node_info.graph_file) {
		try {
			var svg = await LoadAndShowGraph(node_info.graph_file);
		} catch(e) {
			console.error(e);
		}
	}

	if (!svg) {
		// create graph by config
		console.info('Create graph by config');
		var graph_lines = ['block', 'columns 7']  // no links + possible many blocks => use block-graph
		var nodes = node_info['child_nodes'];
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
	var nodes = node_info['child_nodes'];
	if (nodes) {
		for (const k in nodes) {
			if ('child_nodes' in nodes[k]) {
				const el = mm_control.GetSvgNodeById(svg, k);
				mm_control.SetupLink(el, `${pathname}/${k}`);
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
