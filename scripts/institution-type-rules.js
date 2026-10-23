// High-precision keyword rules for institution type. Returns null when unsure.
const R = (s) => new RegExp(s, 'i')
const RULES = [
  ['central_bank', R('\\b(central bank|banque centrale|banco central|banca centrale|zentralbank|national bank of (?:the )?(?:republic|kyrgyz|kazakhstan|ukraine|serbia|georgia|cambodia|ethiopia|rwanda|angola|poland|romania|moldova|belgium|denmark|slovakia|austria)|monetary authority|reserve bank of|bank negara|bank indonesia$|bundesbank|banque de france|banca d.italia|banco de españa|de nederlandsche bank|sveriges riksbank|norges bank|bank of england|bank of japan|federal reserve)\\b')],
  ['development_bank', R('\\b(development bank|development finance|banque de développement|banco de desarrollo|banca di sviluppo|förderbank|landwirtschaftliche rentenbank|export[- ]import bank|eximbank|kfw\\b|agricultural development)')],
  ['credit_union', R('\\b(credit union|federal credit|caisse populaire|caisse desjardins|cooperativa de ahorro|cooperative de ahorro|sacco\\b|\\bcu\\b|\\bfcu\\b)')],
  ['insurance', R('\\b(insurance|assurance|assurances|versicherung|assicurazion|seguros|reinsurance|rückversicherung|reassurance|life (?:company|limited|ltd|s\\.a\\.)|lloyd.s (?:syndicate|underwriter))')],
  ['public_body', R('^(comune di|comunit[aà]|citt[aà] di|provincia di|regione |municipality|municipalit|city of|county of|state of |ville de|département|gmina|kommune|ministry|ministerio|minist[eè]re|tesoro|treasury of|government of)')],
  ['investment', R('(asset management|assetmanagement|asset managers?\\b|investment management|fund management|funds? services|fund managers?|fondsmæglerselskab|kapitalanlage|kapitalverwaltung|investmentgesellschaft|\\bkag\\b|sicav|\\bsgr\\b|\\bucits\\b|gestion\\b|gestão|vermogensbeheer|wealth management|portfolio management|pension fund|pensionskasse|\\bfunds?\\b|unit trust|investment managers?|capital management|asset administration)')],
  ['brokerage', R('(securities|stockbrok|stock brok|brokerage|broking|brokers?\\b|\\bsim s\\.?p\\.?a|\\bsim\\b|corretora|sociedad de valores|agencia de valores|wertpapierhandel|futures|capital markets|börse|stock exchange|bolsa de|clearing|depository|central securities|euroclear|clearstream)')],
  ['payment_emoney', R('(payment services|payments? (?:ltd|limited|s\\.?a|b\\.?v|gmbh|inc|uab|plc)|e-money|electronic money|money transfer|remittance|exchange (?:house|company|bureau)|bureau de change|change s\\.a|forex|western union|moneygram|paysafe|\\bpay\\b)')],
  ['bank', R('(\\bbank|bank\\b|banka\\b|bankas\\b|banca\\b|banco\\b|banque\\b|bancaria|bancario|banken\\b|sparkasse|sparbank|sparebank|volksbank|raiffeisen|landesbank|kreditbank|hypothekenbank|bausparkasse|caisse d.épargne|caja de ahorros|caja rural|cassa di risparmio|cassa rurale|credito cooperativo|crédit agricole|crédit mutuel|banque populaire|shinkin|building society|savings and loan|savings bank|\\bs&l\\b|bancorp|bancshares|trust company|national association|\\bn\\.a\\.|\\bfsb\\b|\\bssb\\b|state bank|osuuspankki|säästöpankki|andelskasse|spar(?:e)?kasse|privatbank|bankhaus|\\bbcc\\b)')]
]
// A securities/asset-management arm of a bank ("BANC OF AMERICA SECURITIES") is not a bank:
// rules are ordered so investment/brokerage win over bank.
function classifyByRules (name) {
  const n = (name || '').normalize('NFC')
  for (const [cls, re] of RULES) if (re.test(n)) return cls
  return null
}
module.exports = { classifyByRules }
