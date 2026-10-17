import {browserGraphValues,reviewedTemplateGraph,matchesTemplateGraphReceipt} from './templateGraph';
const node={id:'root',type:'visit_profile',config:{},delay_hours:0};
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,nodes:[node],edges:[],tree:[node],
  graph_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    revision:0,workspace_id:'workspace',identity_digest:'a'.repeat(64),review_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});

it.each([Infinity,NaN,Number.MAX_SAFE_INTEGER+1,()=>{},undefined,new Date()])('non-browser JSON value stays unavailable %#',value=>{
  expect(browserGraphValues({value})).toBe(false);
});
it('bounded JSON excludes excess depth/items and NUL or oversized keys',()=>{
  let nested={};for(let i=0;i<14;i++)nested={nested};expect(browserGraphValues(nested)).toBe(false);
  expect(browserGraphValues(new Array(20001).fill(1))).toBe(false);expect(browserGraphValues({'bad\0key':1})).toBe(false);
  expect(browserGraphValues({['x'.repeat(201)]:1})).toBe(false);expect(browserGraphValues({valid:[null,true,'Unicode ☕',1.5]})).toBe(true);
});
it('unsupported review/visual source cannot enable editing',()=>{
  const record=row();expect(reviewedTemplateGraph(record)).not.toBeNull();
  for(const patch of [{is_custom:false},{tree:[]},{tree:[{...node,steps:[node]}]},
    {graph_review:{...record.graph_review,revision:Number.MAX_SAFE_INTEGER}},
    {graph_review:{...record.graph_review,update_authorized:true}},
    {nodes:[{...node,config:{numeric:Number.MAX_SAFE_INTEGER+1}}]}])expect(reviewedTemplateGraph({...record,...patch})).toBeNull();
});
it('receipt matches original revision/native/scope/input only with exact fields',()=>{
  const record=row(),captured={...reviewedTemplateGraph(record),graph_json:'{}',input_digest:'d'.repeat(64)};
  const receipt={...reviewedTemplateGraph(record),input_digest:captured.input_digest,status:'updated',template_id:record.id,
    new_revision:1,new_review_digest:'e'.repeat(64),graph_digest:'f'.repeat(64)};
  expect(matchesTemplateGraphReceipt(receipt,record.id,captured)).toBe(true);
  for(const patch of [{new_revision:2},{graph_digest:'bad'},{new_review_digest:null},{input_digest:'a'.repeat(64)},
    {graph_json:'{}'},{execution_authorized:true}])expect(matchesTemplateGraphReceipt({...receipt,...patch},record.id,captured)).toBe(false);
  expect(matchesTemplateGraphReceipt(null,record.id,captured)).toBe(false);
});
