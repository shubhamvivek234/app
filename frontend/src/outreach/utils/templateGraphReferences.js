import { createTemplateReferenceStore } from './templateOperationReferences';
export const STORAGE_KEY = 'unravler.outreach.templateGraphReferences.v1';
export class GraphReferenceError extends Error {}
export const { readReferences, storeReference, clearReference } = createTemplateReferenceStore(
  STORAGE_KEY, GraphReferenceError, 'Saved sequence update references need review. Check status before editing templates.');
