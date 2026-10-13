"""Analysis failure cannot fabricate a personalized style or replace a default."""
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from outreach.api import styles
from tests.outreach_memory import Database
pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}

@pytest.mark.parametrize('result', [None, '', '   ', {'invented': 'shape'}, RuntimeError('private error')])
async def test_failed_analysis_saves_nothing_and_preserves_default(result):
    row = {'id': 'original', 'workspace_id': 'workspace', 'is_default': True}
    db = Database(outreach_writing_styles=[row])
    generator = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=(result, '', ''))
    with patch.object(styles.free_llm, 'generate_text', generator), pytest.raises(HTTPException) as exc:
        await styles.create_writing_style(styles.CreateWritingStyleRequest(name='My voice', sample_posts=['Real sample'], is_default=True), current_user=USER, db=db)
    assert exc.value.status_code == 503
    assert db.outreach_writing_styles.docs == [row]
    assert 'private error' not in str(exc.value.detail)

async def test_valid_analysis_has_provenance_and_exact_generated_instruction():
    db = Database()
    async def unit_persistence(database, workspace_id, operation): return await operation(database)
    with patch.object(styles, 'mutate_suppression', unit_persistence), patch.object(styles.free_llm, 'generate_text', AsyncMock(return_value=('Use reflective sentences and concrete examples.', '', ''))):
        result = await styles.create_writing_style(styles.CreateWritingStyleRequest(name='My voice', sample_posts=['A real post']), current_user=USER, db=db)
    assert result['analysis_source'] == 'sample_analysis'
    assert result['extracted_style_prompt'] == 'Use reflective sentences and concrete examples.'
    assert len(db.outreach_writing_styles.docs) == 1

@pytest.mark.parametrize('fields', [{'name': ' ', 'sample_posts': ['valid']}, {'name': 'Name', 'sample_posts': [' ']}, {'name': 'Name', 'sample_posts': ['Post'] * 11}])
async def test_blank_or_unbounded_style_input_is_rejected(fields):
    with pytest.raises(ValidationError): styles.CreateWritingStyleRequest(**fields)
