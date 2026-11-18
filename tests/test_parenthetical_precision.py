import unittest
from decimal import Decimal, localcontext

from core.reconciliation import InputValidationError, currency_stripper


class ParentheticalPrecisionTests(unittest.TestCase):
    def test_parentheses_preserve_all_digits_even_with_low_context_precision(self):
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(currency_stripper("(123456789012345678901234567890.12)"),
                             Decimal("-123456789012345678901234567890.12"))

    def test_parentheses_cannot_hide_over_limit_precision(self):
        with self.assertRaises(InputValidationError):
            currency_stripper("(" + "9" * 51 + ")")
