// Preserve the visible graph; the server validates the complete execution contract.
export function flattenTreeToDAG(tree) {
  const nodes = [], edges = [];
  const ids = new Set();
  function visit(steps, parent = null, label = null, depth = 0) {
    if (!Array.isArray(steps) || depth > 12) throw new Error('Sequence steps exceed their shape or depth limit.');
    let previous = parent;
    steps.forEach((step, index) => {
      if (!step || typeof step.id !== 'string' || !/^[A-Za-z0-9_.:-]{1,200}$/.test(step.id) || ids.has(step.id) || typeof step.type !== 'string') throw new Error('Every sequence step needs its own valid ID and type.');
      ids.add(step.id);
      if (step.title !== undefined && (typeof step.title !== 'string' || step.title.length > 200) || step.subtitle !== undefined && typeof step.subtitle !== 'string') throw new Error('Step labels must be bounded text.');
      if (nodes.length >= 100) throw new Error('A sequence supports at most 100 steps.');
      let hours = step.delay_hours === undefined ? 0 : step.delay_hours;
      if (step.delay_days !== undefined) {
        if (typeof step.delay_days !== 'number' || !Number.isFinite(step.delay_days)) throw new Error('Step delays must be numeric.');
        hours = step.delay_days * 24;
        if (step.delay_hours !== undefined && step.delay_hours !== hours) throw new Error('Day and hour delays disagree.');
      }
      if (!Number.isInteger(hours) || hours < 0 || hours > 8760) throw new Error('Step delays require whole hours from 0 to 8760.');
      const config = step.config === undefined ? {} : step.config;
      if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('Step settings must be an object.');
      nodes.push({ id: step.id, type: step.type, title: step.title || '', subtitle: step.subtitle || '', delay_hours: hours, config, position: { x: 250, y: 50 + nodes.length * 130 } });
      if (previous) edges.push({ id: `edge_${previous}_to_${step.id}`, source: previous, target: step.id, ...(index === 0 && label ? { label } : {}) });
      previous = step.id;
      const branches = step.branches === undefined ? {} : step.branches;
      if (step.endsHere !== undefined && typeof step.endsHere !== 'boolean') throw new Error('End markers must be booleans.');
      if (!branches || typeof branches !== 'object' || Array.isArray(branches) || Object.keys(branches).some((key) => !['left', 'right'].includes(key))) throw new Error('Sequence branches must use left and right paths.');
      if (step.endsHere && (index < steps.length - 1 || step.steps?.length || Object.values(branches).some((branch) => branch?.steps?.length))) throw new Error('An ended path cannot contain more steps.');
      Object.values(branches).forEach((branch) => {
        if (!branch || Array.isArray(branch) || typeof branch !== 'object' || !Array.isArray(branch.steps === undefined ? [] : branch.steps) || branch.endsHere && branch.steps?.length) throw new Error('An ended or invalid branch cannot contain steps.');
        if (branch.endsHere !== undefined && typeof branch.endsHere !== 'boolean') throw new Error('Branch end markers must be booleans.');
        if (branch.condition !== undefined && (typeof branch.condition !== 'string' || branch.condition.length > 80)) throw new Error('Branch labels must be bounded text.');
        if (branch.steps?.length) visit(branch.steps, step.id, branch.condition, depth + 1);
      });
      if (step.steps !== undefined && (!Array.isArray(step.steps) || step.steps.length)) throw new Error('Nested linear child steps are not displayed by this editor.');
    });
  }
  visit(tree);
  return { nodes, edges };
}
