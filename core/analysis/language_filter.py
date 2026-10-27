"""
Language filter, Indian English (Oxford/Commonwealth) spelling standardizer,
and institutional research report quality auditor.

Enforces site-wide English (India) conventions:
- '-ise' / '-isation' over '-ize' / '-ization' (e.g. capitalisation, specialisation, prioritise)
- '-our' over '-or' (e.g. behaviour, labour, favour, colour, honour, rigour)
- 'defence' / 'offence' over 'defense' / 'offense'
- '-lling' / '-lled' over '-ling' / '-led' (e.g. signalling, modelling, cancelling)
- '-ogue' over '-og' (e.g. catalogue, analogue, dialogue)
- '-re' over '-er' (e.g. centre, fibre, calibre, theatre)
- Standard Commonwealth orthography (e.g. ageing, judgement, fulfilment, instalment)

Provides shielding for URLs, markdown links, code blocks, HTML tags, and proper nouns (e.g. Pfizer).
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("equity_research.core.analysis.language_filter")

# ------------------------------------------------------------------------------
# 1. Non-convertible words, brand names, and proper nouns
# ------------------------------------------------------------------------------
NON_CONVERTIBLE_WORDS: Set[str] = {
    # Words with root 'size'
    "size", "sizes", "sized", "sizing", "sizable", "sizeable",
    "downsize", "downsizes", "downsized", "downsizing",
    "capsize", "capsizes", "capsized", "capsizing",
    "oversize", "oversizes", "oversized", "oversizing",
    "undersize", "undersizes", "undersized", "undersizing",
    "outsize", "outsizes", "outsized", "outsizing",
    # Words with root 'prize'
    "prize", "prizes", "prized", "prizing",
    # Words with root 'seize'
    "seize", "seizes", "seized", "seizing", "seizure", "seizures",
    # Legal / historical roots
    "assize", "assizes", "maize", "bronze", "blaze", "glaze", "craze", "graze",
    "freeze", "freezer", "freezers", "freezing", "freezes",
    "squeeze", "squeezer", "squeezers", "squeezing", "squeezes",
    "breeze", "breezes", "breezy",
    # Instruments ending in -meter (kept as meter in Indian/UK English)
    "meter", "meters", "smartmeter", "smartmeters", "ammeter", "ammeters",
    "voltmeter", "voltmeters", "multimeter", "multimeters", "barometer", "barometers",
    "speedometer", "speedometers", "thermometer", "thermometers", "perimeter", "diameter",
    # Scientific / medical terms with universal -or
    "doctor", "doctors", "factor", "factors", "sector", "sectors",
    "director", "directors", "auditor", "auditors", "anchor", "anchors",
    "debtor", "debtors", "creditor", "creditors", "error", "errors",
    "prior", "senior", "junior", "sponsor", "sponsors", "tailor", "tailors",
    "minor", "major", "investor", "investors", "creator", "creators",
    "vendor", "vendors", "predecessor", "predecessors", "successor", "successors",
    "competitor", "competitors", "regulator", "regulators", "promoter", "promoters",
    "distributor", "distributors", "operator", "operators", "executor", "executors",
    "governor", "governors", "donor", "donors", "tractor", "tractors",
    "reactor", "reactors", "rotor", "rotors", "stator", "stators",
    "motor", "motors", "sensor", "sensors", "indicator", "indicators",
    "oscillator", "oscillators", "conductor", "conductors", "semiconductor", "semiconductors",
    "compressor", "compressors", "generator", "generators", "resistor", "resistors",
    "capacitor", "capacitors", "transformer", "transformers", "inventor", "inventors",
    "author", "authors", "editor", "editors", "visitor", "visitors",
    "emperor", "emperors", "corridor", "corridors", "exterior", "interior",
    "superior", "inferior", "ulterior", "anterior", "posterior",
    "mirror", "mirrors", "horror", "terror", "liquor",
    # Latin / specialized legal or corporate terms
    "defensive", "offensive", "laboratory", "laboratories", "laborious",
    "collaborate", "collaboration", "collaborative", "collaborations",
    "elaborate", "elaboration",
    "vigorous", "rigorous", "glamorous", "humorous", "odorous", "honorary",
    # Brand names, corporate entities, tickers, geography
    "pfizer", "amazon", "citizen", "citizens", "horizon", "horizons", "horizontal",
    "vizhinjam", "mizoram", "karizma", "lubrizol", "instabiz", "ickvayz", "bbevacizumab",
}

# ------------------------------------------------------------------------------
# 2. Canonical Explicit Mappings (US -> English (India))
# ------------------------------------------------------------------------------
EXPLICIT_SPELLING_MAP: Dict[str, str] = {
    # -or -> -our
    "labor": "labour",
    "labors": "labours",
    "labored": "laboured",
    "laboring": "labouring",
    "laborer": "labourer",
    "laborers": "labourers",
    "favor": "favour",
    "favors": "favours",
    "favored": "favoured",
    "favoring": "favouring",
    "favorable": "favourable",
    "favorably": "favourably",
    "unfavorable": "unfavourable",
    "unfavorably": "unfavourably",
    "favorite": "favourite",
    "favorites": "favourites",
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "behavioral": "behavioural",
    "behaviorally": "behaviourally",
    "misbehavior": "misbehaviour",
    "color": "colour",
    "colors": "colours",
    "colored": "coloured",
    "coloring": "colouring",
    "colorant": "colourant",
    "colorless": "colourless",
    "colorful": "colourful",
    "honor": "honour",
    "honors": "honours",
    "honored": "honoured",
    "honoring": "honouring",
    "honorable": "honourable",
    "honorably": "honourably",
    "dishonor": "dishonour",
    "dishonored": "dishonoured",
    "rigor": "rigour",
    "rigors": "rigours",
    "vigor": "vigour",
    "flavor": "flavour",
    "flavors": "flavours",
    "flavored": "flavoured",
    "flavoring": "flavouring",
    "flavorful": "flavourful",
    "harbor": "harbour",
    "harbors": "harbours",
    "harbored": "harboured",
    "harboring": "harbouring",
    "rumor": "rumour",
    "rumors": "rumours",
    "rumored": "rumoured",
    "odor": "odour",
    "odors": "odours",
    "odorless": "odourless",
    "armor": "armour",
    "armored": "armoured",
    "glamor": "glamour",
    "neighbor": "neighbour",
    "neighbors": "neighbours",
    "neighborhood": "neighbourhood",
    "neighborhoods": "neighbourhoods",
    "neighboring": "neighbouring",
    "endeavor": "endeavour",
    "endeavors": "endeavours",
    "endeavored": "endeavoured",
    "endeavoring": "endeavouring",
    "demeanor": "demeanour",
    "splendor": "splendour",
    "candor": "candour",
    "savior": "saviour",
    "saviors": "saviours",
    "vapor": "vapour",
    "vapors": "vapours",

    # defense / offense / pretense
    "defense": "defence",
    "defenses": "defences",
    "defense-oriented": "defence-oriented",
    "self-defense": "self-defence",
    "offense": "offence",
    "offenses": "offences",
    "pretense": "pretence",
    "pretenses": "pretences",

    # Double-L in inflected verbs
    "signaling": "signalling",
    "signaled": "signalled",
    "signaler": "signaller",
    "signalers": "signallers",
    "modeling": "modelling",
    "modeled": "modelled",
    "modeler": "modeller",
    "modelers": "modellers",
    "traveled": "travelled",
    "traveling": "travelling",
    "traveler": "traveller",
    "travelers": "travellers",
    "canceled": "cancelled",
    "canceling": "cancelling",
    "labeled": "labelled",
    "labeling": "labelling",
    "channeled": "channelled",
    "channeling": "channelling",
    "fueled": "fuelled",
    "fueling": "fuelling",
    "equaled": "equalled",
    "equaling": "equalling",
    "initialed": "initialled",
    "initialing": "initialling",
    "paneled": "panelled",
    "paneling": "panelling",
    "tunneled": "tunnelled",
    "tunneling": "tunnelling",
    "counseled": "counselled",
    "counseling": "counselling",
    "counselor": "counsellor",
    "counselors": "counsellors",
    "marshaled": "marshalled",
    "marshaling": "marshalling",

    # -og -> -ogue
    "catalog": "catalogue",
    "catalogs": "catalogues",
    "cataloged": "catalogue",
    "cataloging": "cataloguing",
    "dialog": "dialogue",
    "dialogs": "dialogues",
    "analog": "analogue",
    "analogs": "analogues",
    "monolog": "monologue",
    "monologs": "monologues",

    # -er -> -re
    "center": "centre",
    "centers": "centres",
    "centered": "centred",
    "centering": "centring",
    "fiber": "fibre",
    "fibers": "fibres",
    "caliber": "calibre",
    "calibers": "calibres",
    "theater": "theatre",
    "theaters": "theatres",
    "luster": "lustre",
    "somber": "sombre",
    "meager": "meagre",
    "maneuver": "manoeuvre",
    "maneuvers": "manoeuvres",
    "maneuvered": "manoeuvred",
    "maneuvering": "manoeuvring",
    "kilometer": "kilometre",
    "kilometers": "kilometres",
    "centimeter": "centimetre",
    "centimeters": "centimetres",
    "millimeter": "millimetre",
    "millimeters": "millimetres",

    # Orthographic hygiene
    "fulfill": "fulfil",
    "fulfills": "fulfils",
    "fulfillment": "fulfilment",
    "skillful": "skilful",
    "skillfully": "skilfully",
    "installment": "instalment",
    "installments": "instalments",
    "enroll": "enrol",
    "enrolls": "enrols",
    "enrollment": "enrolment",
    "enrolled": "enrolled",
    "aging": "ageing",
    "judgment": "judgement",
    "judgments": "judgements",
    "acknowledgment": "acknowledgement",
    "acknowledgments": "acknowledgements",
    "program": "programme",
    "programs": "programmes",
    "paycheck": "paycheque",
    "paychecks": "paycheques",
}

# ------------------------------------------------------------------------------
# 3. Dynamic Suffix Engine (-ize -> -ise, -yze -> -yse)
# ------------------------------------------------------------------------------
def _convert_suffix(low: str) -> Optional[str]:
    """Applies dynamic -ize/-yze suffix transformation if word is not an excluded root."""
    if low in NON_CONVERTIBLE_WORDS:
        return None

    # -izations -> -isations
    if low.endswith("izations") and len(low) > 9:
        return low[:-8] + "isations"
    # -ization -> -isation
    if low.endswith("ization") and len(low) > 8:
        return low[:-7] + "isation"
    # -izers -> -isers
    if low.endswith("izers") and len(low) > 6:
        return low[:-5] + "isers"
    # -izer -> -iser
    if low.endswith("izer") and len(low) > 5:
        return low[:-4] + "iser"
    # -izing -> -ising
    if low.endswith("izing") and len(low) > 6:
        return low[:-5] + "ising"
    # -ized -> -ised
    if low.endswith("ized") and len(low) > 5:
        return low[:-4] + "ised"
    # -izes -> -ises
    if low.endswith("izes") and len(low) > 5:
        return low[:-4] + "ises"
    # -ize -> -ise
    if low.endswith("ize") and len(low) > 4:
        return low[:-3] + "ise"

    # -yze / -yzed / -yzing / -yzer / -yzers (e.g. analyze, paralyze, catalyze)
    if low.endswith("yzers") and len(low) > 6:
        return low[:-5] + "ysers"
    if low.endswith("yzer") and len(low) > 5:
        return low[:-4] + "yser"
    if low.endswith("yzing") and len(low) > 6:
        return low[:-5] + "ysing"
    if low.endswith("yzed") and len(low) > 5:
        return low[:-4] + "ysed"
    if low.endswith("yzes") and len(low) > 5:
        return low[:-4] + "yses"
    if low.endswith("yze") and len(low) > 4:
        return low[:-3] + "yse"

    return None

def _match_case(original: str, replacement: str) -> str:
    """Matches the casing format of the original string (UPPERCASE, TitleCase, or lowercase)."""
    if original.isupper():
        return replacement.upper()
    if original.istitle() or (len(original) > 1 and original[0].isupper() and original[1:].islower()):
        # Handle hyphenated words e.g. Self-defense -> Self-defence
        if "-" in replacement:
            return "-".join(part.capitalize() for part in replacement.split("-"))
        return replacement.capitalize()
    return replacement.lower()

# ------------------------------------------------------------------------------
# 4. Content Shielding: Shield URLs, Markdown link URLs, Code blocks, and Tags
# ------------------------------------------------------------------------------
def _shield_protected_content(text: str) -> Tuple[str, List[str]]:
    """
    Shields code blocks, inline code, markdown link destinations, raw URLs,
    and HTML tags so their internal technical tokens are never modified.
    """
    shields: List[str] = []

    def _replace_block(m: re.Match) -> str:
        idx = len(shields)
        shields.append(m.group(0))
        return f"__IN_SHIELD_TOKEN_{idx}__"

    # 1. Fenced Code Blocks (```...```)
    text = re.sub(r"```[\s\S]*?```", _replace_block, text)

    # 2. Inline Code (`...`)
    text = re.sub(r"`[^`\n]+`", _replace_block, text)

    # 3. Markdown links: [link text](url) -> shield the url target only
    def _replace_link_url(m: re.Match) -> str:
        link_text = m.group(1)
        target = m.group(2)
        idx = len(shields)
        shields.append(f"({target})")
        return f"[{link_text}]__IN_SHIELD_TOKEN_{idx}__"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_link_url, text)

    # 4. Raw URLs (https://... or http://...)
    text = re.sub(r"https?://[^\s<>\)\]]+", _replace_block, text)

    # 5. HTML Tags (<...>)
    text = re.sub(r"<[^>]+>", _replace_block, text)

    # 6. Epistemic tags: [VERIFIED FACT], [CALCULATED METRIC], etc.
    def _replace_epistemic_tag(m: re.Match) -> str:
        idx = len(shields)
        shields.append(m.group(0))
        return f"__IN_SHIELD_TOKEN_{idx}__"

    text = re.sub(
        r"\[(VERIFIED FACT|CALCULATED METRIC|MODEL INTERPRETATION|UNRESOLVED UNCERTAINTY)\]",
        _replace_epistemic_tag,
        text,
    )

    return text, shields

def _unshield_protected_content(text: str, shields: List[str]) -> str:
    """Restores shielded blocks back to their original state."""
    for idx, orig in enumerate(shields):
        text = text.replace(f"__IN_SHIELD_TOKEN_{idx}__", orig)
    return text

# ------------------------------------------------------------------------------
# 5. Primary Converter: enforce_indian_english
# ------------------------------------------------------------------------------
def enforce_indian_english(text: str) -> str:
    """
    Transforms any American English spellings in the input text into English (India) /
    British-Commonwealth conventions with case preservation and technical shielding.
    """
    if not text or not isinstance(text, str):
        return text or ""

    shielded_text, shields = _shield_protected_content(text)

    def _convert_token(token: str) -> str:
        t_low = token.lower()
        if t_low in NON_CONVERTIBLE_WORDS:
            return token
        if t_low in EXPLICIT_SPELLING_MAP:
            return _match_case(token, EXPLICIT_SPELLING_MAP[t_low])
        suffix_rep = _convert_suffix(t_low)
        if suffix_rep:
            return _match_case(token, suffix_rep)
        return token

    def _replace_word(m: re.Match) -> str:
        word = m.group(0)
        low = word.lower()

        # Non-convertible whole compound
        if low in NON_CONVERTIBLE_WORDS:
            return word

        # Explicit whole compound
        if low in EXPLICIT_SPELLING_MAP:
            rep = EXPLICIT_SPELLING_MAP[low]
            return _match_case(word, rep)

        # Hyphenated compound: process component tokens (e.g. mid-sized, cost-optimization)
        if "-" in word:
            parts = word.split("-")
            return "-".join(_convert_token(p) for p in parts)

        # Dynamic suffix
        suffix_rep = _convert_suffix(low)
        if suffix_rep:
            return _match_case(word, suffix_rep)

        return word

    # Replace words bounded by \b, handling letters and hyphens (e.g. self-defense)
    converted = re.sub(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)*\b", _replace_word, shielded_text)

    # Restore shielded tokens
    return _unshield_protected_content(converted, shields)

# Alias for semantic clarity across modules
convert_to_indian_english = enforce_indian_english
enforce_indian_english_spelling = enforce_indian_english

# ------------------------------------------------------------------------------
# 6. Quality Audit & Discrepancy Detection Engine
# ------------------------------------------------------------------------------
@dataclass
class ReportQualityResult:
    is_compliant: bool
    quality_score: float
    spelling_score: float
    americanisms_found: List[Dict[str, Any]] = field(default_factory=list)
    epistemic_score: float = 100.0
    epistemic_tags_count: Dict[str, int] = field(default_factory=dict)
    pillars_present: List[str] = field(default_factory=list)
    missing_pillars: List[str] = field(default_factory=list)
    revision_triggers_present: bool = True
    esg_scorecard_valid: bool = True
    safe_harbor_compliant: bool = True
    denomination_compliant: bool = True
    discrepancies: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.is_compliant

    @property
    def americanisms(self) -> List[Dict[str, Any]]:
        return self.americanisms_found

    @property
    def compliance_risks(self) -> List[str]:
        return [d for d in self.discrepancies if "SEBI" in d or "prohibited" in d]

    @property
    def epistemic_deficiencies(self) -> List[str]:
        return [d for d in self.discrepancies if "epistemic" in d.lower()]

def detect_americanisms(text: str) -> List[Dict[str, Any]]:
    """
    Scans text for US English spelling occurrences, returning term, suggested
    English (India) replacement, line number, and snippet context.
    """
    if not text or not isinstance(text, str):
        return []

    shielded_text, _ = _shield_protected_content(text)
    findings = []

    def _get_replacement_for_token(t: str) -> Optional[str]:
        t_low = t.lower()
        if t_low in NON_CONVERTIBLE_WORDS:
            return None
        if t_low in EXPLICIT_SPELLING_MAP:
            return EXPLICIT_SPELLING_MAP[t_low]
        return _convert_suffix(t_low)

    for match in re.finditer(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)*\b", shielded_text):
        word = match.group(0)
        low = word.lower()

        if low in NON_CONVERTIBLE_WORDS:
            continue

        rep = None
        if low in EXPLICIT_SPELLING_MAP:
            rep = EXPLICIT_SPELLING_MAP[low]
        elif "-" in word:
            # Check individual parts
            parts = word.split("-")
            converted_parts = []
            has_change = False
            for p in parts:
                p_rep = _get_replacement_for_token(p)
                if p_rep and p_rep.lower() != p.lower():
                    converted_parts.append(_match_case(p, p_rep))
                    has_change = True
                else:
                    converted_parts.append(p)
            if has_change:
                rep = "-".join(converted_parts)
        else:
            rep = _convert_suffix(low)

        if rep and rep.lower() != low:
            start = max(0, match.start() - 25)
            end = min(len(shielded_text), match.end() + 25)
            snippet = shielded_text[start:end].replace("\n", " ").strip()
            line_no = shielded_text[:match.start()].count("\n") + 1
            replacement = _match_case(word, rep) if "-" not in word else rep
            findings.append({
                "term": word,
                "word": word,
                "replacement": replacement,
                "line": line_no,
                "position": match.start(),
                "snippet": f"...{snippet}..."
            })

    return findings

def audit_report_quality(report_text: str, stock_data: Optional[Dict[str, Any]] = None) -> ReportQualityResult:
    """
    High-rigor quality filter evaluating:
    1. English (India) spelling conformity (0 detected Americanisms)
    2. Epistemic Grounding Separation tags ([VERIFIED FACT], [CALCULATED METRIC], etc.)
    3. Structural completeness across all 7 Pillars
    4. Revision Triggers section presence
    5. ESG Impact Scorecard table formatting
    6. Indian financial denomination compliance (Crores/Lakhs vs Millions/Billions)
    7. SEBI Safe Harbor compliance (zero Buy/Sell/Hold verdicts or target prices)
    """
    discrepancies: List[str] = []

    if not report_text or len(report_text.strip()) < 400:
        americanisms = detect_americanisms(report_text) if report_text else []
        return ReportQualityResult(
            is_compliant=False,
            quality_score=0.0,
            spelling_score=0.0,
            americanisms_found=americanisms,
            missing_pillars=["Pillar 1", "Pillar 2", "Pillar 3", "Pillar 4", "Pillar 5", "Pillar 6", "Pillar 7"],
            discrepancies=["Report text is empty or critically truncated (< 400 characters)."]
        )

    # 1. Spelling Check
    americanisms = detect_americanisms(report_text)
    spelling_penalty = min(40.0, len(americanisms) * 4.0)
    spelling_score = max(0.0, 100.0 - spelling_penalty)
    if americanisms:
        sample_terms = ", ".join(f"'{item['term']}' (use '{item['replacement']}')" for item in americanisms[:4])
        more = f" and {len(americanisms) - 4} more" if len(americanisms) > 4 else ""
        discrepancies.append(
            f"English (India) spelling violations detected ({len(americanisms)} instance(s)): {sample_terms}{more}."
        )

    # 2. Structural Pillar Inspection
    required_pillars = [
        "Pillar 1", "Pillar 2", "Pillar 3", "Pillar 4", "Pillar 5", "Pillar 6", "Pillar 7"
    ]
    pillars_present = []
    missing_pillars = []
    for p in required_pillars:
        if re.search(rf"\b{p}\b", report_text, re.IGNORECASE):
            pillars_present.append(p)
        else:
            missing_pillars.append(p)
            discrepancies.append(f"Missing required analytical dimension: {p}")

    # 3. Revision Triggers Inspection
    revision_triggers_present = bool(re.search(
        r"(?:What Would Change This View|Revision Triggers|Falsification & Thesis-Revision Triggers|What Contradicts This Conclusion)",
        report_text,
        re.IGNORECASE
    ))
    if not revision_triggers_present:
        discrepancies.append("Missing required 'What Would Change This View (Revision Triggers)' section.")

    # 4. Epistemic Separation Tags
    epistemic_tags = {
        "VERIFIED FACT": len(re.findall(r"\[VERIFIED FACT\]", report_text)),
        "CALCULATED METRIC": len(re.findall(r"\[CALCULATED METRIC\]", report_text)),
        "MODEL INTERPRETATION": len(re.findall(r"\[MODEL INTERPRETATION\]", report_text)),
        "UNRESOLVED UNCERTAINTY": len(re.findall(r"\[UNRESOLVED UNCERTAINTY\]", report_text)),
    }
    total_tags = sum(epistemic_tags.values())
    if total_tags < 4:
        discrepancies.append(
            f"Insufficient epistemic grounding tags ({total_tags} found, minimum 4 required across pillars)."
        )
    epistemic_score = min(100.0, (total_tags / 7.0) * 100.0)

    # 5. ESG Impact Scorecard Table
    esg_pattern = re.compile(
        r'\|\s*\*\*?(Environmental|Social|Governance)\*?\*\s*\|\s*(\d+(?:\.\d+)?)(?:\s*/\s*100)?\s*\|',
        re.IGNORECASE
    )
    esg_matches = esg_pattern.findall(report_text)
    esg_valid = len(esg_matches) >= 3
    if not esg_valid:
        discrepancies.append("ESG Impact Scorecard table is incomplete or improperly formatted.")

    # 6. Indian Rupee Millions/Billions Check
    denomination_compliant = True
    if re.search(r'(?:₹|INR|Rs\.?)\s*\d+(?:\.\d+)?\s*(?:million|billion)', report_text, re.IGNORECASE):
        denomination_compliant = False
        discrepancies.append("Use Lakhs/Crores for Indian Rupee figures instead of Millions/Billions.")

    # 7. SEBI Safe Harbor Compliance
    safe_harbor_compliant = True
    non_compliant_verdicts = [
        r"\b(?:strong buy|strong sell|buy verdict|sell verdict|accumulate rating)\b",
        r"\btarget price\s*[:=]\s*(?:₹|INR|Rs\.?)\s*\d+",
        r"\bportfolio allocation\s*[:=]\s*\d+%",
    ]
    for pattern in non_compliant_verdicts:
        if re.search(pattern, report_text, re.IGNORECASE):
            safe_harbor_compliant = False
            discrepancies.append("Report contains prohibited investment verdicts or target prices under SEBI Safe Harbor rules.")
            break

    # Calculate Composite Quality Score (0 to 100)
    score = 100.0
    score -= min(30.0, len(americanisms) * 3.0)
    score -= len(missing_pillars) * 10.0
    if not revision_triggers_present:
        score -= 15.0
    if total_tags < 4:
        score -= 15.0
    if not esg_valid:
        score -= 10.0
    if not denomination_compliant:
        score -= 10.0
    if not safe_harbor_compliant:
        score -= 30.0

    quality_score = max(0.0, min(100.0, score))
    is_compliant = len(discrepancies) == 0 and quality_score >= 85.0

    return ReportQualityResult(
        is_compliant=is_compliant,
        quality_score=round(quality_score, 1),
        spelling_score=round(spelling_score, 1),
        americanisms_found=americanisms,
        epistemic_score=round(epistemic_score, 1),
        epistemic_tags_count=epistemic_tags,
        pillars_present=pillars_present,
        missing_pillars=missing_pillars,
        revision_triggers_present=revision_triggers_present,
        esg_scorecard_valid=esg_valid,
        safe_harbor_compliant=safe_harbor_compliant,
        denomination_compliant=denomination_compliant,
        discrepancies=discrepancies,
    )
