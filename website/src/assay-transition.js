// Five independent single-edit sequences, restored from the earlier walkthrough.
// Each starts from the original DNA; edits are never accumulated across rows.
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

export function createAssayTransition(host,original,alternatives) {
  host.innerHTML = `<defs><clipPath id="assay-window"><rect/></clipPath></defs><g clip-path="url(#assay-window)">${alternatives.map(edit=>`<g class="assay-sequence"><rect class="assay-site"/>${[...original].map((base,j)=>`<text class="${j===edit.site?'assay-base':'assay-context'}">${j===edit.site?edit.base:base}</text>`).join('')}</g>`).join('')}</g>`;
  const window=host.querySelector('clipPath rect');
  const rows=[...host.querySelectorAll('.assay-sequence')].map(node=>({node,site:node.querySelector('.assay-site'),letters:[...node.querySelectorAll('text')]}));
  return {
    draw(p,W,H,source,comparison) {
      attrs(window,{x:0,y:0,width:W,height:H});
      const open=ramp(p,.55,.63),handover=ramp(p,.55,.57);
      const columns=ramp(open,0,.7);
      // Phones retain a shared local window containing all five edit positions.
      const first=W<600?3:0,last=W<600?13:original.length,count=last-first;
      const rowFont=Math.min(24,(comparison.x1-comparison.x0)/count*.92,(comparison.rowY(1)-comparison.rowY(0))*.8);
      alternatives.forEach((edit,i)=>{
        const {node,site,letters}=rows[i],m=comparison.measurements[i];
        const size=mix(source.size,rowFont,ramp(open,0,.55));
        const y=mix(source.y,comparison.rowY(i),open);
        const fold=ramp(m,0,.7),flat=mix(1,.035,fold);
        const length=mix(comparison.x1-comparison.x0,comparison.valueX(edit.measured)-comparison.x0,ramp(m,.4,1));
        const step=length/count;
        const ink=(1-ramp(m,.45,.8))*mix(.84,1,ramp(m,0,.22));
        attrs(node,{transform:`translate(0,${y}) scale(1,${flat})`,'font-size':size,opacity:ink});
        letters.forEach((letter,j)=>{
          const x=mix(source.cx+(j-7)*source.spacing,comparison.x0+(j-first+.5)*step,columns);
          attrs(letter,{x,y:size*.33,opacity:j<first||j>=last?0:j===edit.site?handover:ramp(open,.5,.8)*.68});
        });
        const editedX=mix(source.cx+(edit.site-7)*source.spacing,comparison.x0+(edit.site-first+.5)*step,columns);
        attrs(site,{x:editedX-size*.42,y:-size*.64,width:size*.84,height:size*.98,opacity:ramp(open,.35,.85)*(1-ramp(m,0,.5))});
      });
      return {open};
    },
  };
}
