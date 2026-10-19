import { createTemplateReferenceStore } from './templateOperationReferences';
export const STORAGE_KEY = 'unravler.outreach.templateDeletionReferences.v1';
export class DeletionReferenceError extends Error {}
export const { readReferences, storeReference, clearReference } = createTemplateReferenceStore(
  STORAGE_KEY, DeletionReferenceError, 'Saved deletion references need review. Check status before changing templates.');
