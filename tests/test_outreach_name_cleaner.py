import pytest
from outreach.core.name_cleaner import clean_first_name


def test_preserve_mixed_case():
    assert clean_first_name("McDonald") == "McDonald"
    assert clean_first_name("de la Cruz") == "de la Cruz"
    assert clean_first_name("van Buren") == "van Buren"
    assert clean_first_name("O'Connor") == "O'Connor"
    assert clean_first_name("MacDonald") == "MacDonald"
    assert clean_first_name("diCaprio") == "diCaprio"


def test_all_caps_normalization():
    assert clean_first_name("JOHN") == "John"
    assert clean_first_name("JOHN DOE") == "John Doe"
    assert clean_first_name("MICHAEL O'CONNOR") == "Michael O'Connor"
    assert clean_first_name("MCDONALD") == "McDonald"
    assert clean_first_name("JOHN-PAUL") == "John-Paul"


def test_all_lowercase_capitalization():
    assert clean_first_name("john") == "John"
    assert clean_first_name("sarah jane") == "Sarah Jane"


def test_emoji_and_noise_removal():
    assert clean_first_name("Sarah 🚀 | Founder & CEO") == "Sarah"
    assert clean_first_name("Bob Smith, CPA") == "Bob Smith"
    assert clean_first_name("Elena Rostova, MBA, PhD") == "Elena Rostova"
    assert clean_first_name("Alice [Hiring engineers]") == "Alice"
    assert clean_first_name("David (Speaker & Coach)") == "David"
    assert clean_first_name("✨ Marcus ✨") == "Marcus"


def test_initials_and_special():
    assert clean_first_name("J.R.") == "J.R."
    assert clean_first_name("A.J.") == "A.J."
    assert clean_first_name("") == ""
    assert clean_first_name(None) == ""
    assert clean_first_name("   ") == ""
