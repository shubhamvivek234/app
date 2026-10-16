import { reviewedTemplateDeletion, matchesTemplateDeletionReceipt } from './templateDeletion';

const template = () => ({id:'tpl_custom_012345abcd',is_custom:true,deletion_review:{
  contract_version:1,reviewable:true,deletion_authorized:false,execution_authorized:false,
  revision:0,workspace_id:'workspace',review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});

it('captures exactly the strict fields required by DELETE', () => {
  const row=template(); const before=JSON.stringify(row);const body=reviewedTemplateDeletion(row);
  expect(body).toEqual({contract_version:1,revision:0,workspace_id:'workspace',review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)});
  expect(JSON.stringify(row)).toBe(before);
});

it.each([{contract_version:2},{reviewable:false},{deletion_authorized:true},{execution_authorized:true},
  {revision:true},{revision:'0'},{revision:-1},{revision:2**53},{workspace_id:[]},{workspace_id:' '},
  {review_digest:'bad'},{identity_digest:null},{scope_digest:[]}])('denies malformed/unknown/authority-claiming review %#', (change) => {
  const row=template();row.deletion_review={...row.deletion_review,...change};expect(reviewedTemplateDeletion(row)).toBeNull();
});

it.each([{id:'prebuilt'},{id:[]},{is_custom:1},{deletion_review:null}])('does not delete unreviewed/prebuilt templates %#', (change) => {
  expect(reviewedTemplateDeletion({...template(),...change})).toBeNull();
});

it('accepts only the exact native/scope/revision/request receipt', () => {
  const body=reviewedTemplateDeletion(template());
  expect(matchesTemplateDeletionReceipt({...body,status:'deleted',template_id:template().id},template().id,body)).toBe(true);
});

it.each([{status:'success'},{template_id:'other'},{revision:1},{identity_digest:'d'.repeat(64)},
  {workspace_id:'other'},{scope_digest:'d'.repeat(64)},{review_digest:'d'.repeat(64)},{contract_version:2},
  {execution_authorized:true}])('rejects wrong or authority-claiming receipts %#', (change) => {
  const row=template(),body=reviewedTemplateDeletion(row);
  expect(matchesTemplateDeletionReceipt({...body,status:'deleted',template_id:row.id,...change},row.id,body)).toBe(false);
});
