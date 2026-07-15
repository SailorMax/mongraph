function GetSvgElementsPrefix(svg)
{
	var middle_prefix = svg['myDiagramType'].split('-')[0];
	if (middle_prefix == 'block')
		middle_prefix = null

	if (middle_prefix == null)
		return `${svg.id}-`
	return `${svg.id}-${middle_prefix}-`
}

export function GetSvgNodeById(svg, id)
{
	var idPrefix = GetSvgElementsPrefix(svg);
	var NodeSelector = 'g.node';
	var nodeId;

	var els = svg.querySelectorAll(NodeSelector);
	// console.log(els);
	for (var i=0; i<els.length; i++)
	{
		if (els[i].id.indexOf('≡') > 0)  // auto-generated block-diagram
			nodeId = idPrefix + id.replaceAll('-', '≡');
		else
			nodeId = idPrefix + id;

		if (els[i].id == nodeId || els[i].id.indexOf(nodeId + '-') === 0)
			return els[i];
	}
	return null;
}

export function GetSvgConnectionById(svg, id)
{
	var link_label = [null, null];

	var idPrefix = GetSvgElementsPrefix(svg);
	var els = svg.querySelectorAll('path.flowchart-link');
	var nodeId;

	//console.log(els);
	for (var i=0; i<els.length; i++)
	{
		if (els[i].id.indexOf('≡') > 0)  // auto-generated block-diagram
			nodeId = idPrefix + id.replaceAll('-', '≡') + '_';
		else
			nodeId = idPrefix + id + '_';

		if (els[i].id.indexOf(nodeId) === 0) {
			link_label[0] = els[i];
			break;
		}
	}

	var els = svg.querySelectorAll('g.label');
	//console.log(els);
	for (var i=0; i<els.length; i++)
	{
		if (els[i].id.indexOf('≡') > 0)  // auto-generated block-diagram
			nodeId = id.replaceAll('-', '≡');
		else
			nodeId = id;

		if (els[i].dataset.id.indexOf(nodeId) === 0) {
			link_label[1] = els[i];
			break;
		}
	}

	return link_label;
}

export function SetupAttention(el, level=null, title=null)
{
	// console.log(el);
	if (el.length && el.length == 2)
	{
		// connection
		el[0].classList.remove('normal', 'warning', 'danger');
		el[1]?.classList.remove('normal', 'warning', 'danger');
		if (level !== null) {
			el[0].classList.add(level);
			el[1]?.classList.add(level);
		}
		if (title !== null)
			el[1]?.querySelector('.edgeLabel')?.setAttribute('title', title);
		else
			el[1]?.querySelector('.edgeLabel')?.removeAttribute('title');
	}
	else
	{
		// node
		el.classList.remove('normal', 'warning', 'danger');
		if (level !== null) {
			el.classList.add(level);
		}
		if (title !== null)
			el.querySelector('.nodeLabel')?.setAttribute('title', title);
		else
			el.querySelector('.nodeLabel')?.removeAttribute('title');
	}
}

export function SetupLink(el, url)
{
	el.classList.add('link');
	el['href'] = url;

	const funcOnClick = function(e) {
		if (e.button == 0)  // left button
			window.location = this.href;
		else if (e.button == 1)  // middle button
			window.open(this.href, '_blank');
	};
	el.addEventListener('click', funcOnClick);
	el.addEventListener('auxclick', funcOnClick);
}
