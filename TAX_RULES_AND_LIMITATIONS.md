# Tax-rule implementation limitations

This code provides draft workpaper flags and reference calculations, not legal conclusions or tax-return computations. Tax-law assumptions in the code must be verified against current statutes, regulations, IRS forms and instructions for the applicable tax year.

- **§179:** The 2025 and 2026 values are reference ceilings only. The software does not calculate eligible-property status, taxable-income limitation, business-use tests, related-party restrictions, or all SUV/property rules.
- **Bonus depreciation:** The helper screens acquisition date, placed-in-service date and a user-entered binding-contract-before-cutoff flag. It does not determine qualified-property status, binding written contract facts, self-constructed property, used-property eligibility, class elections, long-production-period property, aircraft, plants, or other exceptions. Long-production-period property is rejected for manual review rather than assigned an unverified rate.
- **§274(o):** The code uses a provisional 50% placeholder for 2025 and a general 100% disallowance screen for covered employer-convenience meals/facility costs paid or incurred after 2025. Coverage, statutory exceptions, and timing must be confirmed by a tax professional.
- **§274(n):** The 50% value is a default workpaper placeholder only. Exceptions, substantiation, business purpose and special rules are not fully modeled.
- **§162(f):** Fines/penalties are marked `REVIEW_REQUIRED`; the software does not assume the full amount is automatically nondeductible. Restitution, remediation, compliance, identification and statutory exception facts require review.
- **§103:** Municipal interest is flagged as a potential exclusion only. The instrument, private-activity bond status, ownership, and statutory exceptions are not analyzed.
- **Schedule M-3:** The $10 million/$50 million and partnership receipt/partner flags are preliminary screening indicators, not a filing determination. Apply the current entity-specific form instructions and all applicable tests.

No output is a tax opinion, legal opinion, audit opinion, or filing recommendation. CPA review and documented approval are required.
