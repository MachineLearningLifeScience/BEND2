import { createReferenceExperiment } from './reference-experiment.js';

// An illustrative experiment. Scroll choreographs objects, never benchmark values.
const original = 'ACGTACGCTAGCTACGATGC';
const alternatives = [
  { site:9, base:'G', prediction:.73, measured:.88 },
  { site:6, base:'A', prediction:.70, measured:.83 },
  { site:5, base:'A', prediction:.75, measured:.71 },
  { site:8, base:'C', prediction:.65, measured:.59 },
  { site:10, base:'T', prediction:.82, measured:.90 },
];
const clamp = n => Math.max(0,Math.min(1,n));
const ease = n => { const p=clamp(n); return p*p*(3-2*p); };
const ramp = (p,a,b) => ease((p-a)/(b-a));
const mix = (a,b,t) => a+(b-a)*t;
const editName = a => `${original[a.site]}${a.site+1} → ${a.base}`;
const attributeValues = new WeakMap(), displayValues = new WeakMap();
function attrs(element,values) {
  let previous=attributeValues.get(element);
  if(!previous) attributeValues.set(element,previous={});
  for(const key in values) {
    const value=typeof values[key]==='number'?values[key].toFixed(3):String(values[key]);
    if(previous[key]!==value) { element.setAttribute(key,value); previous[key]=value; }
  }
}
function show(element,opacity) {
  let previous=displayValues.get(element);
  if(!previous) displayValues.set(element,previous={});
  const value=opacity.toFixed(4),visibility=opacity>.001?'visible':'hidden';
  if(previous.opacity!==value) { element.style.opacity=value; previous.opacity=value; }
  if(previous.visibility!==visibility) { element.style.visibility=visibility; previous.visibility=visibility; }
  attrs(element,{'aria-hidden':String(opacity<.5)});
}

export function createDesignExample(host) {
  host.innerHTML = `<div class="edit-lab">
    <div class="motion-stage">
      <svg class="motion-scene" role="img" aria-label="An original DNA sequence. Scroll to change C8 to T and set a response target.">
        <g class="response-field">
          <rect class="target-band"/><line class="target-rule"/>
          <g class="response-axis"><path/>${[0,.5,1].map(v=>`<g><line y1="0" y2="5"/><text y="21">${v.toFixed(v===0?0:1)}</text></g>`).join('')}<text class="response-axis-title" y="43">Measured RNA activity</text></g>
        </g>
        <g class="reference-experiment"></g>
        <g class="experiment-traces">${alternatives.map(a=>`<g class="experiment-trace"><text class="edit-label" xml:space="preserve"><tspan>${original[a.site]}${a.site+1} → </tspan><tspan class="edit-label-base">${a.base}</tspan></text><g class="measured-edit"><circle class="result-ring" r="8"/><circle class="result-disc" r="4"/><text class="measured-value">${a.measured.toFixed(2)}</text></g></g>`).join('')}</g>
      </svg>
    </div>
  </div>`;
  const scene=host.querySelector('.motion-scene'), stage=host.querySelector('.motion-stage');
  const reference=createReferenceExperiment(host.querySelector('.reference-experiment'),original,alternatives);
  const field=host.querySelector('.response-field'), band=host.querySelector('.target-band'), rule=host.querySelector('.target-rule');
  const axis=host.querySelector('.response-axis');
  const axisPath=axis.querySelector('path'),axisTitle=axis.querySelector('.response-axis-title'),ticks=[...axis.querySelectorAll('g')];
  const traces=[...host.querySelectorAll('.experiment-trace')].map(node=>({
    node,label:node.querySelector('.edit-label'),disc:node.querySelector('.result-disc'),
    ring:node.querySelector('.result-ring'),value:node.querySelector('.measured-value'),
  }));
  let W=1100,H=420,small=false;
  function measure() {
    W=Math.max(1,stage.clientWidth); H=Math.max(200,stage.clientHeight-20); small=W<600;
    attrs(scene,{viewBox:`0 0 ${W} ${H}`});
  }
  return {
    measure,
    setProgress(progress,isPrint) {
      const p=isPrint ? .87 : progress;
      const x0=small?90:156,x1=W-(small?32:60),valueX=v=>x0+(x1-x0)*v/1.1;
      const labelRight=x0-(small?16:24),minTop=small?32:42;
      const rowGap=Math.min(64,(H-76-minTop)/5);
      // Centre the completed comparison on taller screens; keep short screens compact.
      const targetY=Math.max(minTop,(H-(rowGap*5+73))/2),rowY=i=>targetY+(i+1)*rowGap,axisY=rowY(4)+30;
      const targetX=valueX(.70);
      // The very same strokes that form each edited base open into its
      // measured line. Read the first result before the remaining edits follow.
      const measurements=alternatives.map((_,i)=>{
        const start=i===0?.55:.66+(i-1)*(.14/3),end=i===0?.66:.73+(i-1)*(.14/3);
        // The stroke eases its own movement; easing this clock again rushes its middle.
        return clamp((p-start)/(end-start));
      });
      const landed=measurements.map(t=>ramp(t,.94,1));
      reference.draw(p,W,H,small,{
        transfers:measurements,rowY,labelX:labelRight,x0,valueX,targetY,
      });
      show(field,ramp(p,.59,.63));
      const bandReveal=ramp(p,.60,.63),axisGrowth=ramp(p,.59,.66);
      // Show the whole matching interval once the target reaches its plot position.
      attrs(band,{x:valueX(.67),y:targetY,width:valueX(.73)-valueX(.67),height:axisY-targetY,opacity:bandReveal});
      attrs(rule,{x1:targetX,x2:targetX,y1:targetY,y2:axisY,opacity:bandReveal*.5});
      attrs(axis,{transform:`translate(0,${axisY})`,opacity:axisGrowth});
      attrs(axisPath,{d:`M ${mix(targetX,x0,axisGrowth)},0 H ${mix(targetX,x1,axisGrowth)}`});
      attrs(axisTitle,{x:(x0+x1)/2});
      ticks.forEach((tick,i)=>attrs(tick,{transform:`translate(${valueX([0,.5,1][i])},0)`,opacity:ramp(axisGrowth,.5,1)}));

      alternatives.forEach((a,i)=>{
        const trace=traces[i];
        const t=measurements[i],endX=valueX(a.measured);
        show(trace.node,ramp(t,.62,.93));
        attrs(trace.label,{x:labelRight,y:rowY(i)+5,opacity:1});
        const match=i===2 && landed[i]>.5;
        if(trace.match!==match) { trace.node.classList.toggle('is-match',match); trace.match=match; }
        attrs(trace.disc,{cx:endX,cy:rowY(i),r:4,opacity:landed[i]});
        attrs(trace.ring,{cx:endX,cy:rowY(i),opacity:i===2?landed[i]:0});
        attrs(trace.value,{x:endX+14,y:rowY(i)+5,opacity:landed[i]});
      });
      let description;
      if(p<.025) description=`Original sequence ${original}, with measured RNA activity normalized to 1.00. Change C8 to T to set a reference response.`;
      else if(p<.105) description='The C8 to T reference edit and its measured RNA activity appear together. Original RNA activity remains at 1.00 for comparison.';
      else if(p<.34) description='The experimental reference C8 to T measures RNA activity of 0.70 relative to the original at 1.00. This measured activity sets the target.';
      else if(p<.51) description=`The DNA stays fixed while crosshair-style brackets edit ${alternatives.map(editName).join(', ')} at staggered times. Each highlighted change is scored as a separate single-edit candidate. The original activity of 1.00 and experimental reference of 0.70 remain visible for comparison.`;
      else if(p<.55) description=`Five independent single-edit candidates, ranked by closeness to reference prediction 0.72: ${alternatives.map(a=>`${editName(a)}, predicted ${a.prediction.toFixed(2)}`).join('; ')}. The shared strand marks proposed sites; the changes are not combined for evaluation.`;
      else if(p<.66) description='The strokes of the edited G at position 10 open into its measured RNA activity line. The target is 0.70, with a matching range of 0.67 to 0.73. The other proposed bases remain in the original sequence frame.';
      else if(p<.87) description='The first choice A10 to G measures 0.88, outside the matching range 0.67 to 0.73. Increasing the budget tests four more edits from the same original sequence, in rank order.';
      else description=`Five edits tested in rank order: ${alternatives.map(a=>`${editName(a)}, ${a.measured.toFixed(2)}`).join('; ')}. C6 to A matches the 0.70 target within the illustrative range 0.67 to 0.73. One target reached.`;
      if(scene.getAttribute('aria-label')!==description) scene.setAttribute('aria-label',description);
    },
  };
}
