import { editStrokePath } from './edit-strokes.js';

// One persistent strand: the reference edit and assay together, then model substitutions.
const clamp = n => Math.max(0,Math.min(1,n));
const ramp = (p,a,b) => { const t=clamp((p-a)/(b-a)); return t*t*(3-2*t); };
const mix = (a,b,t) => a+(b-a)*t;
const attributeValues = new WeakMap();
function attrs(node,values) {
  let previous=attributeValues.get(node);
  if(!previous) attributeValues.set(node,previous={});
  for(const key in values) {
    const value=typeof values[key]==='number'?values[key].toFixed(3):String(values[key]);
    if(previous[key]!==value) { node.setAttribute(key,value); previous[key]=value; }
  }
}

export function createReferenceExperiment(host,original,alternatives) {
  const order=[...alternatives].sort((a,b)=>a.site-b.site);
  const sites=new Map(alternatives.map((edit,rank)=>[edit.site,{...edit,rank,order:order.indexOf(edit)}]));
  function locus(base,site) {
    const proposal=sites.get(site),edited=site===7||proposal;
    return `<g class="sequence-locus ${site===7?'reference-locus':proposal?'candidate-locus':''}" data-site="${site}">
      ${edited?`<defs><clipPath id="sequence-slot-${site}"><rect/></clipPath></defs><g class="sequence-focus"><rect class="slot-wash"/><path class="slot-brackets"/><text class="slot-position">${String(site+1).padStart(2,'0')}</text></g>`:''}
      <g class="sequence-letter" ${edited?`clip-path="url(#sequence-slot-${site})"`:''}><text class="slot-before">${base}</text>${proposal?'<path class="slot-after"/>':edited?'<text class="slot-after">T</text>':''}</g>
    </g>`;
  }
  host.innerHTML = `<defs>
    <linearGradient id="reference-feather"><stop stop-color="white" stop-opacity="0"/><stop class="feather-left" offset=".15" stop-color="white"/><stop class="feather-right" offset=".85" stop-color="white"/><stop offset="1" stop-color="white" stop-opacity="0"/></linearGradient>
    <mask id="reference-window"><rect width="100%" height="100%" fill="url(#reference-feather)"/></mask>
  </defs>
  <g class="reference-tape" mask="url(#reference-window)">
    ${[...original].map((base,site)=>sites.has(site)?'':locus(base,site)).join('')}
  </g>
  <g class="candidate-slots">${[...original].map((base,site)=>sites.has(site)?locus(base,site):'').join('')}</g>
  <g class="reference-assay" opacity="0">
    <text class="assay-title">Measured RNA activity</text><line class="assay-origin"/>
    <g class="assay-row assay-original"><text class="assay-label">Original</text><line class="assay-bar"/><circle r="3"/><text class="assay-value">1.00</text></g>
    <g class="assay-row assay-edited"><text class="assay-label"><tspan class="assay-name">Experimental</tspan><tspan class="assay-kind"> reference</tspan></text><text class="assay-edit-name">C8 → T</text><line class="assay-bar"/><circle class="assay-target-ring" r="8"/><circle class="assay-point" r="4"/><text class="assay-value">0.70</text></g>
  </g>`;
  const tape=host.querySelector('.reference-tape');
  const loci=[...host.querySelectorAll('.sequence-locus')].map(node=>({
    node,site:Number(node.dataset.site),before:node.querySelector('.slot-before'),after:node.querySelector('.slot-after'),
    focus:node.querySelector('.sequence-focus'),letters:node.querySelector('.sequence-letter'),
    window:node.querySelector('clipPath rect'),wash:node.querySelector('.slot-wash'),
    brackets:node.querySelector('.slot-brackets'),position:node.querySelector('.slot-position'),
  }));
  const assay=host.querySelector('.reference-assay');
  const originalRow=assay.querySelector('.assay-original'),editedRow=assay.querySelector('.assay-edited');
  const referenceName=editedRow.querySelector('.assay-name'),referenceKind=editedRow.querySelector('.assay-kind');
  const assayTitle=assay.querySelector('.assay-title'),assayOrigin=assay.querySelector('.assay-origin');
  const editName=editedRow.querySelector('.assay-edit-name'),targetRing=editedRow.querySelector('.assay-target-ring');
  const assayRows=[originalRow,editedRow].map(node=>({
    node,label:node.querySelector('.assay-label'),bar:node.querySelector('.assay-bar'),
    circles:[...node.querySelectorAll('circle')],value:node.querySelector('.assay-value'),
  }));
  return {
    draw(p,W,H,small,comparison) {
      const referenceEdit=ramp(p,.025,.105);
      // Restore the parent gradually before proposing independent single edits.
      const edit=referenceEdit*(1-ramp(p,.27,.325));
      const spacing=small?Math.min(46,(W-56)/5):Math.min(104,(W-80)/6);
      // Scale down continuously on short screens instead of halving the DNA
      // at one height threshold when the caption needs more room.
      const cx=small?W/2-spacing*.5:W/2;
      const rowGap=small?44:Math.max(44,Math.min(58,H*.15));
      const assayGap=small?42:Math.max(42,Math.min(58,H*.15));
      // Reserve room for the persistent bottom axis, including on short screens.
      const availableSize=(comparison.axisY-assayGap-rowGap-28-14)/1.1;
      const referenceSize=Math.min(availableSize,small?Math.min(64,H*.26):Math.min(132,spacing*1.5,H*.36));
      const sy=Math.min(H*(small?.30:.34),small?150:170,comparison.axisY-28-referenceSize*.46-assayGap-rowGap);
      const backdrop=1-ramp(p,.54,.59);
      attrs(tape,{opacity:backdrop});
      loci.forEach(locus=>{
        const site=locus.site,proposal=sites.get(site),isReference=site===7;
        const sourceSize=isReference?referenceSize:Math.min(referenceSize*.72,spacing*.96);
        const sourceX=cx+(site-7)*spacing;
        const size=sourceSize,x=sourceX,y=sy;
        const start=proposal?[.34,.37,.398,.418,.447][proposal.order]:1;
        const duration=proposal?[.055,.06,.055,.06,.06][proposal.order]:1;
        const turn=isReference?edit:proposal?ramp(p,start,start+duration):0;
        const acquired=proposal?ramp(p,start-.018,start+.008):1;
        const settled=proposal?ramp(p,start+duration*.7,start+duration+.026):0;
        const focus=isReference?1-ramp(p,.325,.36):acquired*(1-settled*.76)*(1-ramp(p,.53,.55));
        const initialOpacity=isReference?1:Math.max(.15,.62-Math.abs(site-7)*.07);
        attrs(locus.node,{transform:`translate(${x},${y})`,'font-size':size});
        const handover=1-ramp(p,.55,.57);
        const letterOpacity=proposal?mix(initialOpacity,.96-settled*.12,acquired)*handover:isReference?1-.87*ramp(p,.325,.36):initialOpacity;
        attrs(locus.letters,{opacity:letterOpacity});
        attrs(locus.before,{y:size*.33-turn*size*1.12,'font-size':size});
        if(!locus.after)return;
        if(proposal) {
          const offset=(1-turn)*size*1.12,key=`${size},${offset}`;
          if(locus.glyphKey!==key) {
            locus.glyphKey=key;
            locus.glyph={d:editStrokePath(proposal.base,size,offset),width:Number((size*.075).toFixed(4))};
          }
          attrs(locus.after,{d:locus.glyph.d,'stroke-width':locus.glyph.width});
        } else attrs(locus.after,{y:size*.33+(1-turn)*size*1.12,'font-size':size});
        const acquisition=proposal?1+(1-acquired)*.16:1;
        const slotWidth=size*.86*acquisition,slotTop=-size*.64*acquisition,slotBottom=size*(proposal?.4:.34)*acquisition;
        const arm=Math.min(12,slotWidth*.22)*mix(1,.56,settled);
        const bounds={x:-slotWidth/2,y:slotTop,width:slotWidth,height:slotBottom-slotTop};
        attrs(locus.window,bounds); attrs(locus.wash,bounds);
        attrs(locus.wash,{opacity:1-settled});
        attrs(locus.focus,{opacity:focus});
        attrs(locus.brackets,{d:`M ${-slotWidth/2+arm},${slotTop} H ${-slotWidth/2} V ${slotTop+arm} M ${slotWidth/2-arm},${slotTop} H ${slotWidth/2} V ${slotTop+arm} M ${-slotWidth/2},${slotBottom-arm} V ${slotBottom} H ${-slotWidth/2+arm} M ${slotWidth/2},${slotBottom-arm} V ${slotBottom} H ${slotWidth/2-arm}`});
        attrs(locus.position,{y:slotTop-12,opacity:(1-settled)*(1-ramp(p,.53,.55))});
      });

      // The same measured reference uses the same x scale throughout the story.
      const chartY=sy+referenceSize*.46+assayGap;
      // The baseline is present from the start; the reference arrives with C → T.
      // Keep both measurements through the model edits; clear the baseline before the rows form.
      const originalReveal=1,editedReveal=referenceEdit;
      const transfer=ramp(p,.53,.60),originalExit=1-ramp(p,.53,.55);
      const referenceLabel=1-ramp(transfer,.08,.3)+ramp(transfer,.78,1);
      const referenceY=mix(chartY+rowGap,comparison.targetY,transfer);
      attrs(assay,{opacity:1});
      // Keep a heading above the measurements as well as the bottom axis label.
      attrs(assayTitle,{x:comparison.x0,y:mix(chartY-24,comparison.targetY-(small?18:24),transfer),opacity:1});
      attrs(assayOrigin,{x1:comparison.x0,x2:comparison.x0,y1:chartY-9,y2:chartY+rowGap*editedReveal+9,opacity:originalReveal*originalExit});
      [[assayRows[0],1,chartY,originalReveal,originalExit],[assayRows[1],.70,referenceY,editedReveal,1]].forEach(([row,value,y,reveal,opacity])=>{
        const end=mix(comparison.x0,comparison.valueX(value),reveal);
        attrs(row.node,{transform:`translate(0,${y})`,opacity:reveal*opacity});
        attrs(row.label,{x:comparison.labelX,y:4,opacity:row.node===editedRow?referenceLabel:1});
        attrs(row.bar,{x1:comparison.x0,x2:end,y1:0,y2:0,'stroke-width':mix(2,1.3,transfer)});
        row.circles.forEach(circle=>attrs(circle,{cx:end,cy:0}));
        attrs(row.value,{x:comparison.valueX(value)+14,y:5,opacity:ramp(reveal,.85,1)});
      });
      // Rename while the label is hidden in transit, in either scroll direction.
      const isTarget=transfer>.5,name=isTarget?'Target':'Experimental';
      if(referenceName.textContent!==name) referenceName.textContent=name;
      attrs(referenceName,{x:comparison.labelX,y:isTarget?4:-4});
      attrs(referenceKind,{x:comparison.labelX,y:11,opacity:isTarget?0:1});
      attrs(editName,{x:comparison.labelX,y:28,opacity:1-ramp(transfer,0,.25)});
      attrs(targetRing,{opacity:ramp(p,.105,.125)});
      return {referenceY,source:{cx,y:sy,spacing,size:Math.min(referenceSize*.72,spacing*.96)}};
    },
  };
}
