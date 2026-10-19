import { createTemplateReferenceStore } from './templateOperationReferences';
export const STORAGE_KEY = 'unravler.outreach.templateMetadataReferences.v1';
export class MetadataReferenceError extends Error {}
export const { readReferences, storeReference, clearReference } = createTemplateReferenceStore(
  STORAGE_KEY, MetadataReferenceError, 'Saved details update references need review. Check status before editing templates.');
