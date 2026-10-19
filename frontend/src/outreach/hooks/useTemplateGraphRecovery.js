import useTemplateUpdateRecovery from './useTemplateUpdateRecovery';
import * as references from '../utils/templateGraphReferences';
import { validHistoricalGraphReceipt } from '../utils/templateGraphUpdates';
const contract = Object.freeze({ references, label: 'sequence', endpoint: '/api/v1/outreach/sequences/template-graph-updates', validReceipt: validHistoricalGraphReceipt });
export default function useTemplateGraphRecovery(viewKey, onConfirmed) {
  return useTemplateUpdateRecovery(viewKey, onConfirmed, contract);
}
