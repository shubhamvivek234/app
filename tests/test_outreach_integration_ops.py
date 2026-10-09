"""Private CLI accepts references only and sanitizes failure output."""
from argparse import Namespace
from unittest.mock import AsyncMock
import pytest
from outreach.ops import integration_review as cli

@pytest.mark.parametrize('command,extra',[
    ('inspect-delivery',['--delivery','d']),('resolve-delivery',['--delivery','d','--decision','stop_local']),
    ('inspect-credential',['--kind','webhook','--resource','hook']),('migrate-credential',['--kind','webhook','--resource','hook'])])
def test_private_parser_requires_mutation_drain(command,extra):
    args=[command,'--workspace','w',*extra]
    if not command.startswith('inspect'):
        args+=['--operator','op','--evidence','All workspace writers and caches drained','--review-digest','a'*64,'--workers-drained',cli.DRAIN_ACK]
    result=cli.parser().parse_args(args)
    assert result.command==command and result.workspace=='w'

@pytest.mark.parametrize('extra',[['--key','private-secret'],['--decision','private-secret'],['--workspace=private-secret','--bogus']])
def test_parser_never_echoes_accidental_secret(extra,capsys):
    with pytest.raises(SystemExit):cli.parser().parse_args(['resolve-delivery','--workspace','w','--delivery','d',*extra])
    assert 'private-secret' not in capsys.readouterr().err

@pytest.mark.asyncio
@pytest.mark.parametrize('ack',[cli.DRAIN_ACK,'yes'])
async def test_cli_requires_exact_drain_ack(monkeypatch,ack):
    service=AsyncMock();monkeypatch.setattr(cli,'IntegrationReview',lambda db:service)
    args=Namespace(command='resolve-delivery',workspace='w',delivery='d',decision='stop_local',operator='op',evidence='evidence',review_digest='a'*64,workers_drained=ack)
    await cli.run_db(args,object())
    assert service.resolve.call_args.kwargs['workers_drained']==(ack==cli.DRAIN_ACK)

def test_main_sanitizes_private_database_error(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['integration_review','inspect-delivery','--workspace','w','--delivery','d'])
    monkeypatch.setattr(cli,'run',AsyncMock(side_effect=ValueError('private-secret')))
    assert cli.main()==2
    output=capsys.readouterr();assert not output.out and 'private-secret' not in output.err
