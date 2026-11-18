"""Unit and adversarial tests for modules/csv_mapper.py."""
import unittest

from core.reconciliation import InputValidationError, Sovereign167VReconciler
from modules.csv_mapper import map_bank_csv_to_ledger


class CsvMapperTests(unittest.TestCase):
    def test_quickbooks_split_debit_credit_with_bom_and_reconciles(self):
        csv_data = (
            "\ufeffTransaction Date,Memo,Debit,Credit\n"
            "01/15/2026,=CMD(),0.00,\"$1,200.50\"\n"
            "01/16/2026,Office Rent,200.50,\n"
        ).encode("utf-8")
        ledger = map_bank_csv_to_ledger(
            csv_data,
            date_col="Transaction Date",
            debit_col="Debit",
            credit_col="Credit",
            memo_col="Memo",
            date_format="%m/%d/%Y",
        )
        self.assertEqual(ledger.loc[0, "Memo"], "'=CMD()")
        res = Sovereign167VReconciler(ledger, "500.00", "1500.00", "0.00").execute_reconciliation()
        self.assertEqual(res.status, "PASS")

    def test_signed_amount_column_mapping(self):
        csv_data = b"Posting Date,Amount\n2026-01-01,300.00\n2026-01-02,-50.00\n"
        ledger = map_bank_csv_to_ledger(csv_data, date_col="Posting Date", amount_col="Amount", type_col=None)
        res = Sovereign167VReconciler(ledger, "1000.00", "1250.00", "0.00").execute_reconciliation()
        self.assertEqual(res.status, "PASS")

    def test_rejects_ambiguous_date_without_format_and_both_debit_credit(self):
        with self.assertRaises(InputValidationError):
            map_bank_csv_to_ledger(b"Date,Amount,Type\n01/02/2026,100,CREDIT\n")
        with self.assertRaises(InputValidationError):
            map_bank_csv_to_ledger(
                b"Date,Debit,Credit\n2026-01-01,10,20\n",
                debit_col="Debit",
                credit_col="Credit",
            )


if __name__ == "__main__":
    unittest.main()
