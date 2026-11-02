"""UK tax + Universal Credit tracker. Rules [S] from gov.uk, checked 2 Nov 2026:
- Trading allowance £1,000 gross per tax year (gov.uk/guidance/tax-free-allowances-on-property-and-trading-income)
- Personal allowance £12,570 (gov.uk/income-tax-rates)
- Register for Self Assessment by 5 Oct after the tax year (gov.uk/register-for-self-assessment)
- Platform reporting: 30 sales or ~£1,700 per calendar year; eBay 2026 £1,707 (gov.uk/guidance/selling-goods-or-services-on-a-digital-platform)
- UC: report self-employed income and expenses EVERY monthly assessment period, even if nil (gov.uk/self-employment-and-universal-credit)
- UC: if gainfully self-employed and not in a start-up period, the higher of actual earnings or the Minimum Income Floor is used
- UC: losses carry forward; earnings £2,500+ over the nil-UC limit become surplus earnings carried to the next period
  (gov.uk/government/publications/universal-credit-for-the-self-employed/universal-credit-and-self-employment-quick-guide)
- UC taper: payment falls 55p per £1 earned (gov.uk/guidance/universal-credit-and-earnings)
- UC capital: under £6,000 ignored; £4.35/month off per £250 (or part) from £6,000 to £16,000; over £16,000 usually not eligible
  (gov.uk/guidance/universal-credit-money-savings-and-investments)
This is a tracker, not advice. Tell your work coach before starting; confirm how business stock and cash count."""
import math

TRADING_ALLOWANCE = 1000.0
PERSONAL_ALLOWANCE = 12570.0
PLATFORM_SALES, PLATFORM_VALUE, EBAY_VALUE_2026 = 30, 1700.0, 1707.0
UC_TAPER = 0.55
SURPLUS_BAND = 2500.0
CAP_LOWER, CAP_UPPER, TARIFF_STEP, TARIFF = 6000.0, 16000.0, 250.0, 4.35

def capital_effect(capital: float) -> dict:
    if capital > CAP_UPPER:
        return {"status": "OVER £16,000: usually not eligible for UC", "monthly_reduction": None}
    if capital <= CAP_LOWER:
        return {"status": "Under £6,000: no effect", "monthly_reduction": 0.0}
    steps = math.ceil((capital - CAP_LOWER) / TARIFF_STEP)
    return {"status": "Between £6,000 and £16,000: UC reduced", "monthly_reduction": round(steps * TARIFF, 2)}

def uc_period(receipts: float, expenses: float, loss_bf: float = 0.0, mif: float = None,
              start_up: bool = True, nil_limit: float = None, surplus_bf: float = 0.0) -> dict:
    profit = receipts - expenses
    net = profit - loss_bf
    loss_cf = max(0.0, -net)
    earnings = max(0.0, net) + surplus_bf
    used = earnings
    note = "Actual earnings used"
    if not start_up and mif is not None and earnings < mif:
        used, note = mif, "Minimum Income Floor used (actual earnings lower)"
    out = {"receipts": receipts, "expenses": expenses, "profit": round(profit, 2),
           "loss_carried_forward": round(loss_cf, 2), "earnings_counted": round(used, 2), "basis": note,
           "uc_reduction_est": round(used * UC_TAPER, 2), "report": "Report receipts and expenses in your UC journal at the end of the period (even if nil)"}
    if nil_limit is not None and earnings - nil_limit >= SURPLUS_BAND:
        out["surplus_to_next_period"] = round(earnings - nil_limit - SURPLUS_BAND, 2)
        out["warning"] = "Surplus earnings: no UC this period, excess carried forward"
    return out

def tax_meters(gross_tax_year: float, platform_year: list) -> dict:
    plat = []
    for p in platform_year:
        lim = EBAY_VALUE_2026 if (p["platform"] or "").startswith("ebay") else PLATFORM_VALUE
        plat.append({**p, "sales_pct": round(p["sales"] / PLATFORM_SALES * 100), "value_pct": round((p["value"] or 0) / lim * 100)})
    return {"trading_allowance_used_pct": round(gross_tax_year / TRADING_ALLOWANCE * 100),
            "over_allowance": gross_tax_year > TRADING_ALLOWANCE,
            "action": ("Register for Self Assessment by 5 October after this tax year ends" if gross_tax_year > TRADING_ALLOWANCE
                       else "Under £1,000 gross: usually nothing to tell HMRC, keep records"),
            "personal_allowance_note": "With no other income, taxable profit up to £12,570 is covered by the personal allowance; you may still need to register and file once gross sales pass £1,000",
            "platforms": plat}
