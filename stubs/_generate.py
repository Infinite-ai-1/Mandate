"""Generates stubs/ : synthetic data in the exact CLAUDE.md schemas.

Hand-written illustrative text, NOT real filings. Run:
    python3 gen_stubs.py /path/to/Mandate
"""
import json, os, sys, textwrap

ROOT = sys.argv[1]
OUT = os.path.join(ROOT, "stubs")

# ---------------------------------------------------------------- companies
COMPANIES = [
    {"ticker": "PM",  "name": "Philip Morris International Inc.", "cik": "0001413329",
     "sic": "2111", "sic_description": "Cigarettes", "form": "10-K", "is_bond": False},
    {"ticker": "MMM", "name": "3M Company", "cik": "0000066740",
     "sic": "3841", "sic_description": "Surgical & Medical Instruments & Apparatus",
     "form": "10-K", "is_bond": False},
    {"ticker": "XYL", "name": "Xylem Inc.", "cik": "0001524472",
     "sic": "3561", "sic_description": "Pumps & Pumping Equipment", "form": "10-K",
     "is_bond": False},
    # one bond ETF so the optimiser's min_bonds path is exercisable off stubs
    {"ticker": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "cik": "0001100663",
     "sic": "6726", "sic_description": "Investment Offices NEC", "form": "10-K",
     "is_bond": True},
]

# ---------------------------------------------------------------- sources
# (source_id, ticker, kind, origin, title, date, url, section)
SOURCES = [
 ("S-PM-0001","PM","filing","edgar_10k","Philip Morris International Inc. Form 10-K for fiscal year 2025","2026-02-12","https://www.sec.gov/Archives/edgar/data/1413329/000141332926000008/pm-20251231.htm","Item 1 Business"),
 ("S-PM-0002","PM","filing","edgar_10k","Philip Morris International Inc. Form 10-K for fiscal year 2025","2026-02-12","https://www.sec.gov/Archives/edgar/data/1413329/000141332926000008/pm-20251231.htm","Item 1A Risk Factors"),
 ("S-PM-0003","PM","filing","edgar_10k","Philip Morris International Inc. Form 10-K for fiscal year 2025","2026-02-12","https://www.sec.gov/Archives/edgar/data/1413329/000141332926000008/pm-20251231.htm","Item 3 Legal Proceedings"),
 ("S-PM-0004","PM","news","guardian","Tobacco firm accused of targeting young adults in low-income markets","2026-05-18","https://www.theguardian.com/business/2026/may/18/tobacco-marketing-low-income-markets",None),
 ("S-PM-0005","PM","news","finnhub","Philip Morris raises full-year outlook as heated tobacco volumes climb","2026-07-22","https://finnhub.io/news/pm-2026-07-22-outlook",None),
 ("S-PM-0006","PM","news","gdelt","Health ministers press for tighter nicotine pouch rules","2026-09-03","https://example-newswire.test/articles/nicotine-pouch-rules-2026",None),
 ("S-PM-0007","PM","market","edgar_xbrl","Philip Morris International Inc. XBRL company facts","2026-02-12","https://data.sec.gov/api/xbrl/companyfacts/CIK0001413329.json",None),
 ("S-PM-0008","PM","computed","quant","Risk statistics computed from 5 years of adjusted daily closes","2026-10-22","https://query1.finance.yahoo.com/v8/finance/chart/PM",None),

 ("S-MMM-0001","MMM","filing","edgar_10k","3M Company Form 10-K for fiscal year 2025","2026-02-05","https://www.sec.gov/Archives/edgar/data/66740/000006674026000012/mmm-20251231.htm","Item 1 Business"),
 ("S-MMM-0002","MMM","filing","edgar_10k","3M Company Form 10-K for fiscal year 2025","2026-02-05","https://www.sec.gov/Archives/edgar/data/66740/000006674026000012/mmm-20251231.htm","Item 1A Risk Factors"),
 ("S-MMM-0003","MMM","filing","edgar_10k","3M Company Form 10-K for fiscal year 2025","2026-02-05","https://www.sec.gov/Archives/edgar/data/66740/000006674026000012/mmm-20251231.htm","Item 3 Legal Proceedings"),
 ("S-MMM-0004","MMM","filing","edgar_8k","3M Company Form 8-K dated 2026-06-11","2026-06-11","https://www.sec.gov/Archives/edgar/data/66740/000006674026000044/mmm-20260611.htm","Item 8.01 Other Events"),
 ("S-MMM-0005","MMM","news","guardian","Water companies say PFAS clean-up costs will outlast settlement payments","2026-06-12","https://www.theguardian.com/environment/2026/jun/12/pfas-clean-up-costs-settlement",None),
 ("S-MMM-0006","MMM","regulator","epa","EPA ECHO enforcement summary for 3M Cordova facility","2026-04-30","https://echo.epa.gov/detailed-facility-report?fid=110000380567",None),
 ("S-MMM-0007","MMM","news","finnhub","3M lifts guidance as industrial demand recovers","2026-07-28","https://finnhub.io/news/mmm-2026-07-28-guidance",None),
 ("S-MMM-0008","MMM","market","edgar_xbrl","3M Company XBRL company facts","2026-02-05","https://data.sec.gov/api/xbrl/companyfacts/CIK0000066740.json",None),
 ("S-MMM-0009","MMM","computed","quant","Risk statistics computed from 5 years of adjusted daily closes","2026-10-22","https://query1.finance.yahoo.com/v8/finance/chart/MMM",None),

 ("S-XYL-0001","XYL","filing","edgar_10k","Xylem Inc. Form 10-K for fiscal year 2025","2026-02-24","https://www.sec.gov/Archives/edgar/data/1524472/000152447226000015/xyl-20251231.htm","Item 1 Business"),
 ("S-XYL-0002","XYL","filing","edgar_10k","Xylem Inc. Form 10-K for fiscal year 2025","2026-02-24","https://www.sec.gov/Archives/edgar/data/1524472/000152447226000015/xyl-20251231.htm","Item 1A Risk Factors"),
 ("S-XYL-0003","XYL","filing","edgar_10k","Xylem Inc. Form 10-K for fiscal year 2025","2026-02-24","https://www.sec.gov/Archives/edgar/data/1524472/000152447226000015/xyl-20251231.htm","Item 3 Legal Proceedings"),
 ("S-XYL-0004","XYL","news","guardian","Leak-detection contracts hand water technology firms a decade of work","2026-03-09","https://www.theguardian.com/business/2026/mar/09/leak-detection-water-technology",None),
 ("S-XYL-0005","XYL","news","finnhub","Xylem wins multi-year metering contract with US municipal utility","2026-08-14","https://finnhub.io/news/xyl-2026-08-14-metering-contract",None),
 ("S-XYL-0006","XYL","market","edgar_xbrl","Xylem Inc. XBRL company facts","2026-02-24","https://data.sec.gov/api/xbrl/companyfacts/CIK0001524472.json",None),
 ("S-XYL-0007","XYL","computed","quant","Risk statistics computed from 5 years of adjusted daily closes","2026-10-22","https://query1.finance.yahoo.com/v8/finance/chart/XYL",None),

 ("S-AGG-0001","AGG","computed","quant","Risk statistics computed from 5 years of adjusted daily closes","2026-10-22","https://query1.finance.yahoo.com/v8/finance/chart/AGG",None),
]

def source_dict(row):
    sid, ticker, kind, origin, title, date, url, section = row
    return {"source_id": sid, "ticker": ticker, "kind": kind, "origin": origin,
            "title": title, "date": date, "url": url, "section": section}

# ---------------------------------------------------------------- chunks
def T(s):
    return " ".join(textwrap.dedent(s).split())

CHUNKS = {}

CHUNKS["PM"] = [
 ("S-PM-0001","2026-02-12", T("""
    We are an international tobacco and nicotine company. Our principal products are combustible
    cigarettes, which we sell under the Marlboro, L&M, Chesterfield, Philip Morris, Bond Street and
    Parliament brands, and smoke-free products, which include heated tobacco units, oral nicotine
    pouches and e-vapour products. Combustible cigarettes accounted for 61.4% of our net revenues in
    2025 and were shipped to consumers in more than 170 markets outside the United States. We
    manufacture cigarettes at 38 owned facilities and purchase tobacco leaf from suppliers in 27
    countries. Our stated ambition is to increase the share of net revenues from smoke-free products,
    and we continue to invest in heated tobacco capacity, but we expect combustible cigarettes to
    remain a majority of our net revenues and the substantial majority of our shipment volume for the
    foreseeable future. Our business is subject to excise taxation, advertising restrictions, graphic
    health warning requirements, flavour bans and, in a growing number of markets, generational sales
    prohibitions.""")),
 ("S-PM-0002","2026-02-12", T("""
    Our products contain nicotine, which is addictive, and the use of our combustible products causes
    serious disease. Regulatory authorities in many of our markets have adopted or are considering
    measures that would further restrict the sale, packaging, flavouring or nicotine content of our
    products, including prohibitions on sales to anyone born after a specified year. Litigation and
    regulatory action of this kind could materially reduce our shipment volume and net revenues.
    Public health bodies, institutional investors and a growing number of asset owners apply
    exclusion policies that prevent them from holding securities issued by tobacco manufacturers,
    which may reduce demand for our shares and increase our cost of capital. We also face
    reputational risk from allegations that our marketing reaches young adults, from the conduct of
    distributors in markets where we do not control the retail channel, and from illicit trade in
    counterfeit versions of our brands.""")),
 ("S-PM-0003","2026-02-12", T("""
    Legal proceedings covering a wide range of matters are pending or threatened against us and our
    subsidiaries in various jurisdictions. These include smoking and health class actions in Canada,
    individual smoking and health claims in Brazil, Argentina, Italy and Nigeria, and health care
    cost recovery actions brought by provincial governments. In the Canadian proceedings, companies
    including our subsidiary Rothmans, Benson & Hedges Inc. remain subject to a court-supervised
    creditor protection process following judgments in the Blais and Letourneau class actions. We
    recorded a charge of $482 million in the fourth quarter of 2025 in connection with these matters.
    An adverse outcome in any pending smoking and health proceeding could require us to pay damages
    that are material to our consolidated results of operations and cash flows, and we cannot predict
    the outcome of the appeals that remain outstanding.""")),
 ("S-PM-0004","2026-05-18", T("""
    Campaigners have accused the tobacco industry of using music festivals, influencer partnerships
    and branded lounges to put nicotine pouches in front of young adults in lower-income markets
    where advertising rules are weaker. Researchers who reviewed 1,400 social media posts said
    roughly a third carried no health warning and that the accounts posting them had a median
    follower age under 30. Philip Morris International said its marketing is aimed only at adults who
    already smoke or use nicotine, that it audits its agencies, and that it supports age verification
    at the point of sale. A spokesperson for a coalition of health charities said exclusion lists are
    the only tool trustees can rely on, because company-level assurances cannot be audited by
    investors from the outside. Health ministers in two of the markets named in the report have asked
    their regulators to review whether pouch advertising falls inside existing tobacco advertising
    bans.""")),
 ("S-PM-0005","2026-07-22", T("""
    Philip Morris International raised its full-year adjusted earnings outlook after heated tobacco
    unit shipments rose 11.2% year on year in the second quarter, and now expects currency-neutral
    adjusted diluted earnings per share growth of 10% to 12%. Smoke-free products reached 40.3% of
    net revenues in the quarter. Combustible cigarette shipment volume fell 1.4%, a smaller decline
    than the company guided to in April, helped by pricing in Turkey, Indonesia and Egypt. The
    company reaffirmed its dividend and said it expects to complete its current capacity expansion in
    Europe by the end of 2027.""")),
 ("S-PM-0006","2026-09-03", T("""
    Health ministers from eleven countries issued a joint statement calling for nicotine pouches to
    be regulated on the same footing as combustible tobacco, including bans on flavours other than
    tobacco and mandatory plain packaging. The statement cites rising use among people aged 18 to 24
    and says voluntary industry marketing codes have not prevented products from being promoted to
    that group. Industry representatives said the products help adult smokers switch away from
    cigarettes and that treating them identically to cigarettes removes that incentive.""")),
]

CHUNKS["MMM"] = [
 ("S-MMM-0001","2026-02-05", T("""
    3M is a diversified technology company with a global presence in safety and industrial;
    transportation and electronics; and consumer markets. We manage our operations in three business
    segments and sell products in approximately 200 countries. Our safety and industrial segment
    supplies personal safety equipment, abrasives, adhesives, tapes and roofing granules. Our
    transportation and electronics segment supplies films, display materials and aerospace products.
    Our consumer segment supplies home care, stationery and home improvement products under brands
    including Post-it, Scotch, Filtrete and Command. We completed the exit of all per- and
    polyfluoroalkyl substance manufacturing by the end of 2025 and continue to work to discontinue
    the use of PFAS across our product portfolio, a programme that has required reformulation of a
    number of product lines and the closure or conversion of several manufacturing sites.""")),
 ("S-MMM-0002","2026-02-05", T("""
    We are exposed to significant environmental, product liability and other claims. Our exit from
    PFAS manufacturing does not resolve claims arising from historical manufacturing or from the
    presence of these substances in the environment, and we continue to face claims by public water
    systems, state attorneys general and individuals alleging property damage, remediation costs and
    personal injury. The cost of remediating sites where PFAS were manufactured or disposed of, and
    the cost of defending and resolving these claims, could exceed the amounts we have accrued. We
    are also subject to ongoing regulatory requirements relating to discharges to water and air at
    our facilities, and from time to time we have been in non-compliance with permit limits. New
    drinking water standards for PFAS adopted in several jurisdictions may increase both the number
    of claimants and the scope of remediation sought from us.""")),
 ("S-MMM-0003","2026-02-05", T("""
    The Company is a defendant in numerous proceedings relating to per- and polyfluoroalkyl
    substances. In June 2023 the Company entered into a settlement with public water systems in the
    United States, under which it agreed to pay up to $12.5 billion through 2036 to fund testing and
    treatment of PFAS in drinking water. Separately, the Company has resolved claims brought by
    service members alleging hearing damage from Combat Arms earplugs for an aggregate of $6.0
    billion payable through 2029. Attorneys general in 32 states have filed natural resource damage
    actions that are not covered by the public water system settlement, and the Company is a
    defendant in personal injury actions alleging that exposure to PFAS caused kidney cancer,
    thyroid disease and ulcerative colitis. The Company has accrued $3.1 billion for these matters,
    which does not reflect amounts for claims it cannot reasonably estimate.""")),
 ("S-MMM-0004","2026-06-11", T("""
    On June 11, 2026, 3M Company reached an agreement in principle with the attorneys general of
    four states to resolve natural resource damage claims relating to per- and polyfluoroalkyl
    substances for an aggregate of $825 million, payable over eight years. The agreement is subject
    to definitive documentation and court approval and does not resolve claims brought by other
    states, by individual plaintiffs, or claims relating to the Company's Cordova, Illinois
    facility. The Company expects to record a pre-tax charge of $825 million in the second quarter of
    2026.""")),
 ("S-MMM-0005","2026-06-12", T("""
    Water companies say the clean-up bill for PFAS contamination will run well past the end of the
    payment schedules agreed with manufacturers, because treatment plants installed to remove the
    chemicals have to be operated and have their filters replaced for decades. One utility serving
    1.2 million people said settlement money covers roughly 60% of its capital cost and none of its
    operating cost. 3M, which agreed in 2023 to pay up to $12.5 billion to public water systems and
    this week settled natural resource claims with four states, said it has exited PFAS manufacturing
    and is working with utilities on treatment technology. Environmental lawyers said the pattern of
    settling state by state means the company's total exposure will not be known for years, which is
    the point charities screening for pollution litigation tend to find hardest to price.""")),
 ("S-MMM-0006","2026-04-30", T("""
    EPA ECHO detailed facility report for 3M Cordova, Illinois (NPDES permit IL0000426) records the
    facility in significant non-compliance for two of the twelve most recent quarters, with
    effluent limit exceedances reported for perfluorooctanoic acid and total suspended solids. One
    formal enforcement action is listed with a penalty of $132,000 assessed in the current reporting
    period, and the facility remains under a compliance schedule for outfall monitoring. Name match
    to the registered facility operator was exact. Air and hazardous waste programmes at the site
    show no violations in the same period.""")),
 ("S-MMM-0007","2026-07-28", T("""
    3M raised its full-year adjusted earnings guidance after organic sales grew 3.4% in the second
    quarter, led by industrial adhesives and aerospace. Adjusted operating margin expanded 180 basis
    points year on year. The company said the $825 million natural resource damage agreement
    announced in June is reflected in reported results but excluded from adjusted figures, and that
    it continues to expect PFAS-related cash payments of roughly $1.2 billion a year through 2029.""")),
]

CHUNKS["XYL"] = [
 ("S-XYL-0001","2026-02-24", T("""
    Xylem is a leading global water technology company. We design, manufacture and service products
    and solutions that move, treat, analyse and return water to the environment, and we provide
    software and services that help utilities and industrial customers manage water networks. We
    operate through four segments: Water Infrastructure, Applied Water, Measurement and Control
    Solutions, and Water Solutions and Services. Our products include pumps, valves, mixers,
    disinfection systems, smart meters and leak-detection networks, and are sold in more than 150
    countries. Approximately 95% of our revenue is derived from products and services that
    contribute to clean water access, water quality, water efficiency or resilience to drought and
    flooding. We do not manufacture tobacco, alcohol, weapons or fossil fuel extraction equipment,
    and we do not operate in the oil and gas exploration and production market.""")),
 ("S-XYL-0002","2026-02-24", T("""
    Our results depend on capital spending by public water utilities, which is funded by rates and
    by government programmes and can be deferred during periods of fiscal pressure. A reduction in
    infrastructure funding, or delays in the award of contracts under such programmes, could reduce
    our revenue growth. We are exposed to supply chain disruption for electronic components used in
    our metering products, to competition from lower-cost pump manufacturers in Asia, and to
    exchange rate movements, as roughly half of our revenue is denominated in currencies other than
    the US dollar. Our products are subject to drinking water safety and product certification
    regimes, and a failure to meet those standards could result in recalls or exclusion from
    tenders.""")),
 ("S-XYL-0003","2026-02-24", T("""
    From time to time we are party to legal proceedings arising in the ordinary course of business,
    including contract disputes, employment claims and product warranty matters. We are also a
    defendant in asbestos-related claims arising from products manufactured by predecessor
    businesses decades ago; the number of pending claims has declined for five consecutive years and
    the Company's recorded liability for these matters was $18 million at December 31, 2025. We do
    not believe that any pending proceeding, individually or in the aggregate, will have a material
    adverse effect on our financial condition, results of operations or cash flows. No environmental
    proceeding is pending to which a governmental authority is a party and in which monetary
    sanctions of $300,000 or more are expected.""")),
 ("S-XYL-0004","2026-03-09", T("""
    Water regulators in England and Wales have set leakage reduction targets that will require
    companies to find and fix hundreds of thousands of hidden leaks over the next decade, work that
    depends on acoustic sensors, pressure monitoring and the analytics software that interprets them.
    Suppliers including Xylem and a handful of specialist rivals have signed multi-year framework
    agreements covering sensor supply and managed services. Analysts said the contracts are unusually
    long by industrial standards, which smooths revenue but also locks in pricing before inflation is
    known. Charities investing with an environmental mission have shown interest in the sector
    because the capital spending is mandated by regulators rather than discretionary.""")),
 ("S-XYL-0005","2026-08-14", T("""
    Xylem said it won a seven-year contract with a US municipal utility to supply and operate
    advanced metering infrastructure for 740,000 service connections, including meters, the
    communications network and leak-detection analytics. The company did not disclose the contract
    value. Management said the award supports its target of mid-single-digit organic revenue growth
    and that backlog in its Measurement and Control Solutions segment reached a record at the end of
    the second quarter.""")),
]

# ---------------------------------------------------------------- metrics
FUNDAMENTALS = {
 "PM": ("S-PM-0007", [
    ("revenue_3y_growth", 0.071, "ratio", "2025-12-31"),
    ("net_margin", 0.198, "ratio", "2025-12-31"),
    ("debt_to_equity", 14.82, "ratio", "2025-12-31"),
    ("operating_cash_flow", 12_210_000_000, "usd", "2025-12-31"),
    ("dividends_per_share", 5.40, "usd", "2025-12-31"),
 ]),
 "MMM": ("S-MMM-0008", [
    ("revenue_3y_growth", -0.018, "ratio", "2025-12-31"),
    ("net_margin", 0.112, "ratio", "2025-12-31"),
    ("debt_to_equity", 2.31, "ratio", "2025-12-31"),
    ("operating_cash_flow", 6_840_000_000, "usd", "2025-12-31"),
    ("dividends_per_share", 2.92, "usd", "2025-12-31"),
 ]),
 "XYL": ("S-XYL-0006", [
    ("revenue_3y_growth", 0.134, "ratio", "2025-12-31"),
    ("net_margin", 0.094, "ratio", "2025-12-31"),
    ("debt_to_equity", 0.23, "ratio", "2025-12-31"),
    ("operating_cash_flow", 1_190_000_000, "usd", "2025-12-31"),
    ("dividends_per_share", 1.56, "usd", "2025-12-31"),
 ]),
}

RISK = {
 "PM":  ("S-PM-0008", [
    ("volatility_1y", 0.213, "ratio", "2026-10-22"),
    ("beta_vs_spy", 0.62, "ratio", "2026-10-22"),
    ("max_drawdown_5y", -0.329, "ratio", "2026-10-22"),
    ("worst_12m_return", -0.187, "ratio", "2026-10-22"),
    ("dividend_yield", 0.042, "ratio", "2026-10-22"),
 ]),
 "MMM": ("S-MMM-0009", [
    ("volatility_1y", 0.274, "ratio", "2026-10-22"),
    ("beta_vs_spy", 0.98, "ratio", "2026-10-22"),
    ("max_drawdown_5y", -0.512, "ratio", "2026-10-22"),
    ("worst_12m_return", -0.341, "ratio", "2026-10-22"),
    ("dividend_yield", 0.021, "ratio", "2026-10-22"),
 ]),
 "XYL": ("S-XYL-0007", [
    ("volatility_1y", 0.246, "ratio", "2026-10-22"),
    ("beta_vs_spy", 1.09, "ratio", "2026-10-22"),
    ("max_drawdown_5y", -0.298, "ratio", "2026-10-22"),
    ("worst_12m_return", -0.142, "ratio", "2026-10-22"),
    ("dividend_yield", 0.011, "ratio", "2026-10-22"),
 ]),
 "AGG": ("S-AGG-0001", [
    ("volatility_1y", 0.054, "ratio", "2026-10-22"),
    ("beta_vs_spy", 0.11, "ratio", "2026-10-22"),
    ("max_drawdown_5y", -0.183, "ratio", "2026-10-22"),
    ("worst_12m_return", -0.079, "ratio", "2026-10-22"),
    ("dividend_yield", 0.038, "ratio", "2026-10-22"),
 ]),
}

def metrics(sid, rows):
    return [{"name": n, "value": v, "unit": u, "as_of": d, "source_id": sid}
            for n, v, u, d in rows]

# ---------------------------------------------------------------- write
def dump(relpath, obj):
    path = os.path.join(OUT, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    return relpath

written = []
written.append(dump("universe.json", COMPANIES))
written.append(dump("sources.json", {r[0]: source_dict(r) for r in SOURCES}))

for ticker, rows in CHUNKS.items():
    written.append(dump(f"chunks/{ticker}.json",
        [{"source_id": sid, "ticker": ticker, "text": text, "date": date}
         for sid, date, text in rows]))

for ticker, (sid, rows) in FUNDAMENTALS.items():
    written.append(dump(f"fundamentals/{ticker}.json",
        {"ticker": ticker, "metrics": metrics(sid, rows)}))

for ticker, (sid, rows) in RISK.items():
    written.append(dump(f"risk/{ticker}.json",
        {"ticker": ticker, "metrics": metrics(sid, rows)}))

for p in written:
    print("wrote stubs/" + p)
