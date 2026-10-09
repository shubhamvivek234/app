import { requestIntegrationTest, integrationTestMessage } from './integrationDelivery';
const response = (data, ok = true) => ({ ok, json: async () => data });
beforeAll(() => { Object.defineProperty(global, 'crypto', { configurable: true, value: { randomUUID: () => 'test-request-identity-123' } }); });
const queued = () => response({ status: 'queued', delivery_id: 'del2_a' });

test('queued acceptance waits for a saved delivered outcome and never reposts', async () => {
  const fetchImpl = jest.fn().mockResolvedValueOnce(queued())
    .mockResolvedValueOnce(response({ status: 'possible' }))
    .mockResolvedValueOnce(response({ status: 'delivered', status_code: 200 }));
  const onQueued = jest.fn();
  const result = await requestIntegrationTest('/test', { fetchImpl, onQueued, intervalMs: 0 });
  expect(onQueued).toHaveBeenCalledTimes(1);
  expect(result.status).toBe('delivered');
  expect(fetchImpl.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
  expect(integrationTestMessage(result).level).toBe('success');
});

test.each(['review_required', 'held_received'])('uncertain %s outcomes show review, never success', async status => {
  const fetchImpl = jest.fn().mockResolvedValueOnce(queued()).mockResolvedValue(response({ status }));
  expect(integrationTestMessage(await requestIntegrationTest('/test', { fetchImpl })).level).toBe('warning');
  expect(fetchImpl).toHaveBeenCalledTimes(2);
});

test('poll exhaustion stays pending and cannot create another job', async () => {
  const fetchImpl = jest.fn().mockResolvedValueOnce(queued()).mockResolvedValue(response({ status: 'pending' }));
  const result = await requestIntegrationTest('/test', { fetchImpl, intervalMs: 0, maxPolls: 3 });
  expect(result).toEqual({ id: 'del2_a', status: 'pending' });
  expect(integrationTestMessage(result).level).toBe('info');
  expect(fetchImpl).toHaveBeenCalledTimes(4);
});

test.each([false, 'network'])('loss of status access preserves pending outcome (%s)', async problem => {
  const fetchImpl = jest.fn().mockResolvedValueOnce(queued());
  if (problem === false) fetchImpl.mockResolvedValueOnce(response({}, false));
  else fetchImpl.mockRejectedValueOnce(new Error('network'));
  expect((await requestIntegrationTest('/test', { fetchImpl })).status).toBe('pending');
});

test('a rejected enqueue never starts status polling', async () => {
  const fetchImpl = jest.fn().mockResolvedValue(response({ detail: 'blocked' }, false));
  await expect(requestIntegrationTest('/test', { fetchImpl })).rejects.toThrow('could not be queued');
  expect(fetchImpl).toHaveBeenCalledTimes(1);
});

test('abort prevents further polls', async () => {
  const controller = new AbortController();
  const fetchImpl = jest.fn().mockResolvedValue(queued());
  await expect(requestIntegrationTest('/test', { fetchImpl, signal: controller.signal,
    onQueued: () => controller.abort() })).rejects.toMatchObject({ name: 'AbortError' });
  expect(fetchImpl).toHaveBeenCalledTimes(1);
});

test.each(['network', 'json'])('lost POST acknowledgement stays uncertain (%s)', async problem => {
  const fetchImpl = jest.fn();
  if (problem === 'network') fetchImpl.mockRejectedValue(new Error('lost response'));
  else fetchImpl.mockResolvedValue({ ok: true, json: async () => { throw new Error('broken response'); } });
  await expect(requestIntegrationTest('/test', { fetchImpl })).rejects.toMatchObject({
    message: 'Could not confirm the request; it may still be queued.', requestId: 'test-request-identity-123',
  });
  expect(fetchImpl).toHaveBeenCalledTimes(1);
});

test('saved receipt review is terminal and reports the connection stays paused', async () => {
  const fetchImpl = jest.fn().mockResolvedValueOnce(queued())
    .mockResolvedValueOnce(response({ status: 'review_completed', status_code: 200 }));
  const result = await requestIntegrationTest('/test', { fetchImpl });
  expect(result.status).toBe('review_completed');
  expect(fetchImpl).toHaveBeenCalledTimes(2);
  expect(integrationTestMessage(result)).toEqual({
    level: 'info', text: 'Operator review applied the saved delivery receipt. The connection remains paused.',
  });
});
