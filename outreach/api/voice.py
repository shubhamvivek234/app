"""Consent-bound Voice Studio API: queue work, read status and saved previews."""
import base64
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core import suppression
from outreach.core.erasure import require_open_workspace
from outreach.core.voice_studio import VoiceStudio, public_job, require_profile, consent_current, now, enabled
from outreach.core.voice_policy import MAX_PCM_BYTES
from outreach.core.dag_compiler import interpolate_template

class StudioRoute(APIRoute):
    """Cap clone bodies before Starlette buffers the multipart form."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        if not self.path.endswith('/voice/clone'):
            return handler
        async def bounded(request: Request):
            maximum = MAX_PCM_BYTES + 65536  # bounded WAV plus form overhead
            declared = request.headers.get('content-length')
            if declared:
                try:
                    length = int(declared)
                except ValueError:
                    raise HTTPException(400, 'Invalid upload length') from None
                if length < 0 or length > maximum:
                    raise HTTPException(413, 'Voice upload exceeds its bounds')
            # Reject before the multipart parser opens partial temporary files.
            # This bounded buffer also covers chunked/missing-length uploads.
            body = bytearray()
            async for part in request.stream():
                if len(body) + len(part) > maximum:
                    raise HTTPException(413, 'Voice upload exceeds its bounds')
                body.extend(part)
            delivered = False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await request.receive()
            return await handler(Request(request.scope, receive=receive))
        return bounded


router = APIRouter(prefix='/voice', tags=['LinkedIn Voice AI Engine'], route_class=StudioRoute)
MAX_VOICE_PROFILES = 5


class VoicePreviewRequest(BaseModel):
    voice_id: str = Field(max_length=128)
    request_id: str = Field(min_length=8, max_length=128)
    template_text: str = Field(default='Hey {{first_name}}', max_length=1000)
    lead_sample: dict[str, str] = Field(default_factory=dict)


class AssignVoiceRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list, max_length=5)


class ConsentRequest(BaseModel):
    consent: bool


def workspace(user):
    return user.get('default_workspace_id') or user.get('user_id')


async def available(user, db):
    await require_open_workspace(user, db)


async def queued(db, ws, actor, op, request, **kwargs):
    try:
        return public_job(await VoiceStudio(db).queue(ws, actor, op, request, **kwargs))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except Exception:
        raise HTTPException(503, 'Voice Studio storage is unavailable; retry this same request') from None


@router.get('')
async def list_voices(current_user: dict = Depends(get_outreach_user), db=Depends(get_db)):
    await available(current_user, db)
    ws = workspace(current_user)
    voices = await db.outreach_voices.find({'workspace_id': ws}).limit(5).to_list(length=5)
    jobs = await db.outreach_voice_studio_jobs.find({'workspace_id': ws}).sort('created_at', -1).limit(50).to_list(length=50)
    return {'voices': [{**{k: v[k] for k in ('id', 'name', 'revision', 'assigned_account_ids', 'created_at') if k in v},
        'status': v.get('status', 'needs_review'), 'consent_current': consent_current(v),
        'operator_review_required': bool(v.get('studio_review_required'))} for v in voices],
        'jobs': [public_job(j) for j in jobs], 'studio_enabled': enabled(), 'used_count': len(voices), 'max_voices': 5}


@router.post('/clone', status_code=202)
async def clone_voice(file: UploadFile = File(...), name: str = Form(...), consent: bool = Form(False),
                      request_id: str = Form(...), current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    audio = await file.read(MAX_PCM_BYTES + 45)
    return await queued(db, workspace(current_user), current_user.get('user_id'), 'clone', request_id,
        name=name, audio=audio, consent=consent)


@router.post('/preview', status_code=202)
async def preview_voice_note(req: VoicePreviewRequest, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    if any(key not in {'first_name', 'last_name', 'company_name', 'job_title'} or len(value) > 200
           for key, value in req.lead_sample.items()):
        raise HTTPException(400, 'Preview sample fields are outside their bounds')
    script = interpolate_template(req.template_text, req.lead_sample)
    return await queued(db, workspace(current_user), current_user.get('user_id'), 'preview', req.request_id,
        voice_id=req.voice_id, script=script)


@router.get('/jobs/{job_id}')
async def job_status(job_id: str, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    job = await db.outreach_voice_studio_jobs.find_one({'workspace_id': workspace(current_user), '_id': job_id})
    if not job:
        raise HTTPException(404, 'Studio job is unavailable')
    return public_job(job)


@router.post('/jobs/{job_id}/cancel')
async def cancel_job(job_id: str, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    try:
        return public_job(await VoiceStudio(db).cancel(workspace(current_user), job_id, current_user.get('user_id')))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get('/jobs/{job_id}/audio')
async def saved_audio(job_id: str, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    try:
        audio = await VoiceStudio(db).preview(workspace(current_user), job_id, current_user.get('user_id'))
    except Exception:
        raise HTTPException(409, 'Saved preview is unavailable') from None
    return {'media_type': 'audio/wav', 'audio_base64': base64.b64encode(audio).decode()}


@router.post('/{voice_id}/assign')
async def assign_voice(voice_id: str, req: AssignVoiceRequest, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    ws = workspace(current_user)
    async def apply(current):
        await VoiceStudio(db)._access(current, ws, current_user.get('user_id'), 'delete')
        profile = require_profile(await current.outreach_voices.find_one({'workspace_id': ws, 'id': voice_id}))
        if profile.get('studio_job_id'):
            raise ValueError('Wait for unfinished Studio work')
        for account in req.account_ids:
            if not await current.outreach_accounts.find_one({'workspace_id': ws, 'id': account, 'is_deleted': {'$ne': True}}):
                raise ValueError('Sender is unavailable in this workspace')
        await current.outreach_voices.update_one({'workspace_id': ws, 'id': voice_id, 'revision': profile['revision']},
            {'$set': {'assigned_account_ids': list(dict.fromkeys(req.account_ids))}, '$inc': {'revision': 1}})
    try:
        await suppression.mutate_suppression(db, ws, apply)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {'status': 'success', 'voice_id': voice_id, 'assigned_account_ids': req.account_ids}


@router.post('/{voice_id}/consent')
async def update_consent(voice_id: str, req: ConsentRequest, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    ws, actor = workspace(current_user), current_user.get('user_id')
    async def apply(current):
        from outreach.core.authorization import canonical_hash
        await VoiceStudio(db)._access(current, ws, actor, 'delete')
        profile = await current.outreach_voices.find_one({'workspace_id': ws, 'id': voice_id})
        if not profile or (req.consent and (profile.get('studio_job_id') or profile.get('studio_review_required')
                or profile.get('status') not in {'active', 'consent_revoked', None})):
            raise ValueError('Voice profile has unfinished work or needs operator review')
        changes = {'status': 'active' if req.consent else 'consent_revoked', 'updated_at': now()}
        if req.consent:
            changes['consent'] = {'version': 1, 'actor': actor, 'asserted_at': now(),
                'assertion_digest': canonical_hash(['speaker_owns_or_authorized', actor, voice_id, now()])}
        else:
            changes['consent'] = {}
        # This assertion never adopts unproven legacy provider source custody.
        await current.outreach_voices.update_one({'workspace_id': ws, 'id': voice_id}, {'$set': changes, '$inc': {'revision': 1}})
    try:
        await suppression.mutate_suppression(db, ws, apply)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {'status': 'consent_recorded' if req.consent else 'consent_revoked'}


@router.delete('/{voice_id}', status_code=202)
async def delete_voice(voice_id: str, request_id: str, current_user: dict = require_outreach_permission('voice:manage'), db=Depends(get_db)):
    await available(current_user, db)
    return await queued(db, workspace(current_user), current_user.get('user_id'), 'delete', request_id, voice_id=voice_id)
