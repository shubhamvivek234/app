import useTemplateUpdateRecovery from './useTemplateUpdateRecovery';
import * as references from '../utils/templateMetadataReferences';
import { validHistoricalMetadataReceipt } from '../utils/templateMetadataUpdates';
const contract = Object.freeze({ references, label: 'details', endpoint: '/api/v1/outreach/sequences/template-metadata-updates', validReceipt: validHistoricalMetadataReceipt });
export default function useTemplateMetadataRecovery(viewKey, onConfirmed) {
  return useTemplateUpdateRecovery(viewKey, onConfirmed, contract);
}
