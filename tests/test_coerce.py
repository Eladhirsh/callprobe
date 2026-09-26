from callprobe.coerce import MAX_INTEGER_DIGITS, _coerce_scalar


def test_fractional_strings_are_not_coerced_to_integer():
    assert _coerce_scalar("4225.9", "integer") == "4225.9"
    assert _coerce_scalar("4225.00000000000001", "integer") == "4225.00000000000001"


def test_integral_decimal_and_exponent_strings_coerce_exactly():
    assert _coerce_scalar("4225.0", "integer") == 4225
    assert _coerce_scalar("4.225e3", "integer") == 4225
    assert _coerce_scalar("-10", "integer") == -10


def test_exact_large_integer_preserved_without_float_round_trip():
    text = "1" * 25
    assert _coerce_scalar(text, "integer") == int(text)


def test_value_at_the_digit_bound_is_still_coerced():
    text = "9" * MAX_INTEGER_DIGITS
    assert _coerce_scalar(text, "integer") == int(text)


def test_value_past_the_digit_bound_is_left_as_a_string():
    text = "9" * (MAX_INTEGER_DIGITS + 1)
    assert _coerce_scalar(text, "integer") == text


def test_excessive_exponent_is_left_as_a_string_without_expanding_digits():
    text = f"1e{MAX_INTEGER_DIGITS + 1000}"
    assert _coerce_scalar(text, "integer") == text


def test_nonfinite_strings_are_rejected_for_integer_and_number():
    for text in ("inf", "-inf", "Infinity", "NaN"):
        assert _coerce_scalar(text, "integer") == text
        assert _coerce_scalar(text, "number") == text


def test_number_still_coerces_ordinary_decimal_strings():
    assert _coerce_scalar("4225.9", "number") == 4225.9


def test_boolean_coercion_is_unchanged():
    assert _coerce_scalar("true", "boolean") is True
    assert _coerce_scalar("no", "boolean") is False
    assert _coerce_scalar("maybe", "boolean") == "maybe"


def test_non_string_values_pass_through_untouched():
    assert _coerce_scalar(4225, "integer") == 4225
    assert _coerce_scalar(True, "boolean") is True


def test_large_integral_decimal_preserves_digits_a_float_would_round():
    assert _coerce_scalar("9007199254740993.0", "integer") == 9007199254740993
    assert _coerce_scalar("9.007199254740993e15", "integer") == 9007199254740993


def test_zero_with_large_exponent_needs_no_integer_expansion():
    assert _coerce_scalar("0e999999", "integer") == 0
