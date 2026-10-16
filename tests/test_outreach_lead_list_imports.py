"""Bounds and original-row fidelity for reviewed list imports."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from outreach.api.lead_lists import ImportPreview, ListRevision
from outreach.core.lead_list_imports import parsed_source, public_receipt


def payload(**values):
    return ImportPreview(source_type='csv', raw_text='linkedin_url,first_name\nhttps://www.linkedin.com/in/person,Person', quantity=1, **values).model_dump()


@pytest.mark.parametrize('raw', [
    'linkedin_url,first_name\n\nhttps://www.linkedin.com/in/one,One\n\nhttps://www.linkedin.com/in/two,Two',
    '\ufeff"linkedin_url",first_name\nhttps://www.linkedin.com/in/one,One\nhttps://www.linkedin.com/in/two,Two',
])
def test_csv_prefix_skips_blank_records_and_preserves_bom_quoted_header(raw):
    p = payload(); p['raw_text'] = raw
    rows, more = parsed_source(p)
    assert len(rows) == 1 and rows[0]['first_name'] == 'One' and more
    assert rows[0]['linkedin_url'] == 'https://www.linkedin.com/in/one'


def test_invalid_records_remain_in_selected_prefix():
    p = payload(); p['raw_text'] = 'linkedin_url,first_name\nbad,Missing\nhttps://www.linkedin.com/in/one,One'
    rows, more = parsed_source(p)
    assert len(rows) == 1 and not rows[0]['linkedin_url'] and more


@pytest.mark.parametrize('key', ['01', '001', '0', '2', '9'*5000, '\u0661'])
def test_edited_names_cannot_alias_or_reference_an_unreviewed_row(key):
    p=payload(); p['name_overrides']={key:'Changed'}
    with pytest.raises(HTTPException) as error:
        parsed_source(p)
    assert error.value.status_code == 422


@pytest.mark.parametrize('raw', ['\ud800', 'x'*2_000_001])
def test_invalid_utf8_and_oversize_input_have_controlled_errors(raw):
    p = payload(); p['raw_text'] = raw
    with pytest.raises(HTTPException) as error: parsed_source(p)
    assert error.value.status_code == 422


def test_streamed_prefix_does_not_parse_or_materialize_unselected_records():
    p = payload(); p['raw_text'] += '\n' + '\n'.join('bad,x' for _ in range(150000))
    rows, more = parsed_source(p)
    assert len(rows) == 1 and more


@pytest.mark.parametrize('quantity', [True, '1', 0, 101])
def test_quantity_is_explicit_and_strict(quantity):
    with pytest.raises(ValidationError): ImportPreview(source_type='csv', raw_text='x', quantity=quantity)


def test_http_metadata_mutations_require_native_review_digest():
    with pytest.raises(ValidationError): ListRevision(revision=1)


@pytest.mark.parametrize('row', [None, {}, {'status':'completed'}, {'status':[]}])
def test_missing_or_malformed_receipts_do_not_become_success(row):
    with pytest.raises(HTTPException) as error: public_receipt(row)
    assert error.value.status_code == 503


@pytest.mark.parametrize('value', ['\ud800', '\x7f', '\u200b'])
@pytest.mark.parametrize('field', ['default_first_name', 'default_company_name', 'name_overrides'])
def test_names_reject_nonprintable_and_surrogate_text(value,field):
    p=payload(); p[field]={'1':value} if field=='name_overrides' else value
    with pytest.raises(HTTPException) as error: parsed_source(p)
    assert error.value.status_code==422


def test_explicit_empty_name_clears_all_effective_name_fallbacks():
    rows,_=parsed_source(payload(name_overrides={'1':''}))
    assert not any(rows[0][key] for key in ('first_name','raw_first_name','cleaned_first_name'))


@pytest.mark.parametrize('edits',[{'101':'x'},{'1':'x'*101},{'01':'x'}])
def test_http_override_fields_are_bounded_before_core_hashing(edits):
    with pytest.raises(ValidationError): payload(name_overrides=edits)


@pytest.mark.parametrize('wide_header',[True,False])
def test_csv_width_is_bounded_before_dict_materialization(wide_header):
    p=payload()
    p['raw_text']=(','.join('x' for _ in range(101))+'\nvalue') if wide_header else ('linkedin_url,first_name\n'+','.join('x' for _ in range(101)))
    with pytest.raises(HTTPException) as error: parsed_source(p)
    assert error.value.status_code==422 and '100 columns' in error.value.detail


@pytest.mark.parametrize('separator',['\r','\r\n','\u2028','\x85','\v'])
def test_pasted_prefix_uses_parser_line_boundaries_without_materializing_suffix(separator):
    p=payload(); p.update(source_type='pasted_urls',raw_text=separator.join(['https://linkedin.com/in/one,One','https://linkedin.com/in/two,Two']))
    rows,more=parsed_source(p)
    assert len(rows)==1 and rows[0]['first_name']=='One' and more


def test_unselected_csv_sentinel_is_not_parsed_or_admitted():
    p=payload(); p['raw_text']='linkedin_url,first_name,member_urn\nhttps://www.linkedin.com/in/one,One,\nhttps://www.linkedin.com/in/two,Two,urn:li:fsd_profile:Unreviewed'
    rows,more=parsed_source(p)
    assert len(rows)==1 and more and not rows[0]['identifiers'].get('member_urn')
