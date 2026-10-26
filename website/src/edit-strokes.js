// Each base and its measured line use the same stroke samples. Branches in A
// and T become adjacent, non-overlapping portions of the finished line.
const clamp = value => Math.max(0,Math.min(1,value));
const ease = value => { const t=clamp(value); return t*t*(3-2*t); };
const mix = (a,b,t) => a+(b-a)*t;
const fmt = value => Number(value.toFixed(4));

// Monospace capitals: a .55-em width and cap bounds from -.40 to .33 em.
// A contour consists of a starting point followed by lines or cubic curves.
const c = [
  [.25,-.285],
  ['C',.18,-.365,.09,-.4,-.025,-.4],
  ['C',-.20,-.4,-.275,-.25,-.275,-.035],
  ['C',-.275,.18,-.18,.33,-.025,.33],
  ['C',.09,.33,.185,.29,.255,.215],
];
const shapes = {
  A: [
    [[-.27,.33],['L',0,-.4],['L',.27,.33]],
    [[-.17938,.085],['L',.17938,.085]],
  ],
  C: [c],
  G: [[...c,['L',.255,-.025],['L',.045,-.025]]],
  T: [
    [[-.275,-.4],['L',.275,-.4]],
    [[0,-.4],['L',0,.33]],
  ],
};

function sampleContour(commands) {
  const points=[commands[0]];
  let previous=commands[0];
  commands.slice(1).forEach(command=>{
    if(command[0]==='L') {
      previous=command.slice(1);
      points.push(previous);
      return;
    }
    const [,x1,y1,x2,y2,x3,y3]=command;
    const [x0,y0]=previous;
    for(let i=1;i<=40;i++) {
      const t=i/40,u=1-t;
      points.push([
        u*u*u*x0+3*u*u*t*x1+3*u*t*t*x2+t*t*t*x3,
        u*u*u*y0+3*u*u*t*y1+3*u*t*t*y2+t*t*t*y3,
      ]);
    }
    previous=[x3,y3];
  });
  const distances=[0];
  for(let i=1;i<points.length;i++) {
    distances.push(distances[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]));
  }
  const length=distances.at(-1);
  const count=Math.max(12,Math.ceil(length*80));
  const sampleDistances=Array.from({length:count+1},(_,i)=>length*i/count);
  // Keep sharp structural corners, especially A's apex, exactly in the sample.
  if(commands.slice(1).every(command=>command[0]==='L'))sampleDistances.push(...distances);
  let segment=1;
  const samples=[...new Set(sampleDistances)].sort((a,b)=>a-b).map(distance=>{
    while(segment<distances.length-1&&distances[segment]<distance)segment++;
    const t=(distance-distances[segment-1])/(distances[segment]-distances[segment-1]);
    return {
      x:mix(points[segment-1][0],points[segment][0],t),
      y:mix(points[segment-1][1],points[segment][1],t),
      distance,
    };
  });
  return {samples,length};
}

const glyphs=Object.fromEntries(Object.entries(shapes).map(([base,contours])=>{
  const strokes=contours.map(sampleContour);
  const length=strokes.reduce((sum,stroke)=>sum+stroke.length,0);
  let offset=0;
  return [base,strokes.map(stroke=>{
    const samples=stroke.samples.map(point=>({...point,along:(offset+point.distance)/length}));
    offset+=stroke.length;
    return samples;
  })];
}));

function glyph(base) {
  const strokes=glyphs[base];
  if(!strokes)throw new Error(`Unsupported edit base: ${base}`);
  return strokes;
}

function path(strokes,position) {
  return strokes.map(stroke=>stroke.map((point,i)=>{
    const [x,y]=position(point);
    return `${i?'L':'M'} ${fmt(x)},${fmt(y)}`;
  }).join(' ')).join(' ');
}

// Source glyph centred on x=0; offsetY shifts its original text anchor.
// Render with fill="none", round joins/caps, and stroke-width=size*.075.
export function editStrokePath(base,size,offsetY=0) {
  return path(glyph(base),point=>[point.x*size,point.y*size+offsetY]);
}

// source: {x,y,size}; target: {x0,x1,y}. At t=0 this is exactly the source
// glyph; at t=1 its contours form one contiguous horizontal 1.3px line.
// A small delay along the stroke lets it open progressively, without a
// separate trail, flying duplicate, or state that could break reverse scroll.
// The common centre moves into its row early, clear of completed measurements.
export function morphEditStroke(base,source,target,t) {
  const progress=clamp(t);
  const centreY=mix(source.y,target.y,ease(progress/.60));
  const d=path(glyph(base),point=>{
    const local=ease((progress-point.along*.12)/.88);
    return [
      mix(source.x+point.x*source.size,mix(target.x0,target.x1,point.along),local),
      centreY+point.y*source.size*(1-local),
    ];
  });
  return {d,width:fmt(mix(source.size*.075,1.3,ease(progress/.88)))};
}
