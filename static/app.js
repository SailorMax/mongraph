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
		console.error("Mermaid rendering failed:" + error);
		console.log(graphDefinition);
	}
}

var sleepAsync = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function LoadFile(filename) {
	while (true)
	{
		try {
			const response = await fetch(filename);
			if (!response.ok)
				throw new Error(`Error status: ${response.status}`);
			var response_text = await response.text();
			document.querySelector('#loader').classList.remove('error');
			return response_text;

		} catch (error) {
			console.error(`Failed to load graph ${filename}:`, error);
			document.querySelector('#loader').classList.add('error');
		}

		await sleepAsync(1000);
	}
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
			// history data
			let row_nr = 0;
			for (const hst_row of child_node_metric['history']) {
				let in_focus = !row_nr && attention_statuses.indexOf(hst_row['status']) >= 0
				const history_item = {
					node_parents: parents,
					node_name: node_name,
					metric_node: child_nodes[node_name]['metric_node'],
					in_focus: in_focus,
					is_actual: false,

					ts: hst_row['ts'],
					status: hst_row['status'],
					details: in_focus ? child_node_metric['details'] : hst_row['details'],
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

function GetDurationBetweenDates(dt1, dt2) {
	var delta = (dt2 - dt1) / (60*1000);
	var delta_days = Math.floor(delta / (24*60));
	delta %= (24*60);
	var delta_hours = Math.floor(delta / 60)
	delta %= (60);
	var delta_minutes = Math.floor(delta)

	var durationFormatter = new Intl.DurationFormat('en-US', { style: 'short' });
	return durationFormatter.format({
		days: delta_days,
		hours: delta_hours,
		minutes: delta_minutes
	});
}

function FilterHistoryTable(filter_value) {
	var history_filter = document.getElementById('history-filter');

	if (filter_value) {
		history_filter.value = filter_value;
		history_filter.focus();
	}

	history_filter.dispatchEvent(new Event('input', { bubbles: true }));
}

function GetReadableDatetime(dt) {
	if (!dt)
		dt = new Date();
	else if (typeof dt === "number")
		dt = new Date(dt*1000);
	return dt.toISOString().replace('T', ' ').replace(/.\d{3}Z/, ' UTC')
}

// dialog
document.querySelector('#msgRowDetails').addEventListener('close', () => {
	ContinueRefreshTimer();
});
document.querySelector('#msgRowDetails #msgRowDetailsClose').addEventListener('click', () => {
	document.querySelector("#msgRowDetails").close();
});

function ShowRowDetailsDialog(hst_row, node_details) {
	StopRefreshTimer();
	var msgBox = document.querySelector("#msgRowDetails");
	msgBox.querySelector('#msgNode').innerText = hst_row['node_name'];
	msgBox.querySelector('#msgNodeDetails').innerText = node_details;
	msgBox.querySelector('#msgStatusDate').innerText = GetReadableDatetime(hst_row['ts']);
	msgBox.querySelector('#msgStatus').innerText = hst_row['status'];
	msgBox.querySelector('#msgStatusDetails').innerText = hst_row['details'];
	msgBox.showModal();
}

function CloseRowDetailsDialog() {
	document.querySelector("#msgRowDetails").close();
}
//

function FillHistoryTable(node_info) {
	var parents = node_info['node_deep'].map((el) => el['name']);
	var history = CollectHistory(node_info['child_nodes'], parents)
	history.sort((a, b) => b['in_focus'] != a['in_focus'] ? (b['in_focus'] - a['in_focus']) : (b['ts'] - a['ts']))

	const now = new Date();
	var tbl = document.getElementById('history');
	tbl.tBodies[0].replaceChildren();  // clear
	for (const hst_row of history) {
		const new_row = tbl.tBodies[0].insertRow(-1);
		const ts_cell = new_row.insertCell(0);
		const name_cell = new_row.insertCell(1);
		const details_cell = new_row.insertCell(2);

		mm_control.SetupAttention(new_row, hst_row['status']);
		const ts_string = GetReadableDatetime(hst_row['ts']);

		const row_dt = new Date(hst_row['ts']*1000);
		if (hst_row['is_actual'])
			new_row.classList.add('is_actual');
		if (hst_row['in_focus']) {
			new_row.classList.add('in_focus');

			var duration = GetDurationBetweenDates(row_dt, now);
			ts_cell.textContent = ts_string + "\nΔt: " + duration;
		}
		else
			ts_cell.textContent = ts_string;

		const node_details = (hst_row['node_parents'] || []).join(' → ')
						 	+ (hst_row['metric_node'] ? `\n[${hst_row['metric_node']}]` : '')

		const filter_btn = document.createElement('BUTTON');
		filter_btn.innerText = '⧩';
		filter_btn.title = 'filter by node name';
		filter_btn.addEventListener('click', (e) => {
			FilterHistoryTable(e.target.closest('TD').querySelector('A').innerText);
		});
		name_cell.appendChild(filter_btn);

		if (node_details != '') {
			const info_btn = document.createElement('BUTTON');
			info_btn.innerText = 'ℹ';
			info_btn.title = 'show detailed information';
			info_btn.addEventListener('click', (e) => {
				ShowRowDetailsDialog(hst_row, node_details);
			});
			name_cell.appendChild(info_btn);
		}

		const link = document.createElement('A');
		link.href = '/' + (hst_row['node_parents'] || []).join('/');
		link.title = node_details;
		link.textContent = hst_row['node_name'];
		name_cell.appendChild(link);

		var details = hst_row['details'];
		if (details.indexOf("\n") < 0)
			details = details.trim();
		details_cell.textContent = details;
	}

	FilterHistoryTable();
}

function GetPreparedPathName(el_name) {
	if (el_name.indexOf('/') >= 0)
		return `base64,${btoa(el_name).replaceAll('+', '-').replaceAll('/', '_')}`
	return el_name;
}

async function MakePageByPathname(node_info) {
	// project name
	document.getElementsByTagName('H1')[0].innerText = node_info.project_name;

	// prepare history table
	var history_box = document.querySelector('.history_box');
	var history_box_height = localStorage.getItem('history_box_height');
	history_box.style.height = (history_box_height ? `${history_box_height}px` : '');
	var resizeObserver = new ResizeObserver((entries) => {
		if (!entries[0].target.classList.contains('fullsize')) {
			localStorage.setItem('history_box_height', entries[0].contentRect.height);
		}
	});
	resizeObserver.observe(history_box);

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
				mm_control.SetupLink(el, `${pathname}/${GetPreparedPathName(k)}`);
			}
		}
	}

	svg['myConfig'] = node_info;
	return svg;
}

async function LoadNodeInfo(pathname)
{
	const node_info_text = await LoadFile('/node_info' + pathname);
	return JSON.parse(node_info_text);
}

// timer
function StopRefreshTimer()
{
	var timer = document.getElementById('timer');
	if (timer['myInterval']) {
		window.clearInterval(timer['myInterval']);
		delete timer['myInterval'];
		return true;
	}
	return false;
}

function ShowLoadingStatus()
{
	StopRefreshTimer();
	document.getElementById('refresh_control').style.display = "none";
	document.getElementById('loader').style.display = "block";
}

async function RefreshTimerTick()
{
	var timer = document.getElementById('timer');
	var counter = parseInt(timer.innerText, 10);
	timer.innerText = (--counter).toString();
	if (counter == 0)
		await RefreshMetrics();
}

function ContinueRefreshTimer()
{
	var timer = document.getElementById('timer');
	timer['myInterval'] = window.setInterval(RefreshTimerTick, 1000);
}

function StartRefreshTimer(node_info)
{
	var timer = document.getElementById('timer');
	document.getElementById('loader').style.display = "none";
	timer.innerText = node_info['ui_update_interval'] || '30';	// seconds
	document.getElementById('refresh_control').style.display = "block";
	ContinueRefreshTimer();
}
//

async function RefreshMetrics(node_info=null)
{
	var called_by_timer = !node_info;
	if (called_by_timer)
		ShowLoadingStatus();

	// data
	if (!node_info)
		node_info = await LoadNodeInfo(window.location.pathname);

	if (node_info && node_info['child_nodes'])
	{
		// table
		FillHistoryTable(node_info);

		// graph
		var svg = document.querySelector('#graph SVG');
		for (const [el_name, node] of Object.entries(node_info['child_nodes'])) {
			const sv_node = mm_control.GetSvgNodeById(svg, el_name);
			if (sv_node) {
				const metric = node['metric'];
				mm_control.SetupAttention(sv_node, metric['status'], metric['details']);
			}
		}
	}

	if (called_by_timer)
		StartRefreshTimer(node_info);
}

function InitEventHandlers()
{
	// Handle navigation
	navigation.addEventListener("navigate", async (e) => {
		if (!e.canIntercept)
			return true;
		e.intercept();  // do not load new page but change address bar

		var target_url = new URL(e.destination.url);
		await SetupPage(target_url.pathname);
	});

	// timer
	document.querySelector('#refresh_control BUTTON').addEventListener('click', async function(e) {
		if (StopRefreshTimer()) {
			this.innerText = "refresh";
			document.querySelector('#refresh_control SPAN:nth-child(2)').style.display = 'none';
			document.querySelector('#refresh_control SPAN').innerText = 'Last update: ' + GetReadableDatetime();
			return;
		}

		await RefreshMetrics();
		this.innerText = "stop";
		document.querySelector('#refresh_control SPAN:nth-child(2)').style.display = 'inline';
	});

	// prepare history table
	document.getElementById('history-resizer').addEventListener('click', function(e) {
		var box = e.target.closest('.history_box');
		box.style.height = '';
		box.classList.toggle('fullsize');
	});
	document.getElementById('history-filter').addEventListener('keyup', function(e) {
		if (e.code == 'Escape' && e.target.value == '') {
			var box = e.target.closest('.history_box');
			box.classList.remove('fullsize');
		}
	});
	document.getElementById('history-filter').addEventListener('input', function(e) {
		var re = null;
		if (e.target.value != '')
		{
			re = new RegExp(e.target.value, "i")
			var box = e.target.closest('.history_box');
			box.classList.add('fullsize');
		}
		var tbl = e.target.closest('TABLE');
		rows_loop: for (var row of tbl.tBodies[0].rows) {
			for (var cell of row.cells) {
				if (!re || cell.textContent.match(re)) {
					row.style.display = '';
					continue rows_loop;
				}
			}

			row.style.display = 'none';
		}
	});
}


// Initial draw on page load
async function SetupPage(pathname) {
	ShowLoadingStatus();

	var node_info = await LoadNodeInfo(pathname);
	if (node_info) {
		var svg = await MakePageByPathname(node_info);
		await RefreshMetrics(node_info);
	}

	StartRefreshTimer(node_info);
}

// Init
InitEventHandlers();
await SetupPage(window.location.pathname);
