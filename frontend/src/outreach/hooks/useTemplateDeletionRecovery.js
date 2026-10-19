import useTemplateUpdateRecovery from './useTemplateUpdateRecovery';
import * as references from '../utils/templateDeletionReferences';
import { validHistoricalDeletionReceipt } from '../utils/templateDeletionRecovery';
const contract = Object.freeze({ references, noun: 'template deletion',
  confirmation: 'Original template deletion confirmed. Reloading current templates…',
  endpoint: '/api/v1/outreach/sequences/template-deletions', validReceipt: validHistoricalDeletionReceipt });
export default function useTemplateDeletionRecovery(viewKey, onConfirmed) {
  return useTemplateUpdateRecovery(viewKey, onConfirmed, contract);
}
