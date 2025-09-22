"""
PII and Sensitive Data Classifiers
Name-based heuristics for identifying potentially sensitive data.
"""
import re
import logging
from typing import Set, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ClassificationRule:
    """A rule for classifying column names."""
    patterns: List[str]
    confidence: float  # 0.0 to 1.0
    category: str

class PIIClassifier:
    """Name-based PII classifier using heuristic patterns."""
    
    def __init__(self):
        self.pii_rules = self._init_pii_rules()
        self.sensitive_rules = self._init_sensitive_rules()
        
    def _init_pii_rules(self) -> List[ClassificationRule]:
        """Initialize PII classification rules."""
        return [
            # High confidence PII patterns
            ClassificationRule(
                patterns=[
                    r'.*ssn.*', r'.*social.*security.*', r'.*sin.*',
                    r'.*passport.*', r'.*license.*', r'.*driver.*id.*',
                    r'.*national.*id.*', r'.*tax.*id.*', r'.*ein.*'
                ],
                confidence=0.95,
                category="government_id"
            ),
            ClassificationRule(
                patterns=[
                    r'.*email.*', r'.*e_mail.*', r'.*mail.*addr.*',
                    r'.*email.*address.*'
                ],
                confidence=0.90,
                category="email"
            ),
            ClassificationRule(
                patterns=[
                    r'.*phone.*', r'.*telephone.*', r'.*mobile.*',
                    r'.*cell.*', r'.*fax.*', r'.*tel_.*'
                ],
                confidence=0.90,
                category="phone"
            ),
            ClassificationRule(
                patterns=[
                    r'.*credit.*card.*', r'.*cc_num.*', r'.*card.*number.*',
                    r'.*account.*number.*', r'.*bank.*account.*', r'.*iban.*',
                    r'.*routing.*number.*', r'.*swift.*'
                ],
                confidence=0.95,
                category="financial"
            ),
            ClassificationRule(
                patterns=[
                    r'.*address.*', r'.*addr.*', r'.*street.*',
                    r'.*zip.*', r'.*postal.*', r'.*city.*',
                    r'.*state.*', r'.*province.*', r'.*country.*'
                ],
                confidence=0.80,
                category="address"
            ),
            ClassificationRule(
                patterns=[
                    r'.*birth.*date.*', r'.*dob.*', r'.*birth.*day.*',
                    r'.*age.*', r'.*born.*'
                ],
                confidence=0.85,
                category="demographic"
            ),
            ClassificationRule(
                patterns=[
                    r'.*first.*name.*', r'.*last.*name.*', r'.*full.*name.*',
                    r'.*fname.*', r'.*lname.*', r'.*given.*name.*',
                    r'.*family.*name.*', r'.*surname.*'
                ],
                confidence=0.85,
                category="name"
            ),
            # Medium confidence patterns
            ClassificationRule(
                patterns=[
                    r'.*password.*', r'.*pwd.*', r'.*secret.*',
                    r'.*token.*', r'.*key.*', r'.*hash.*',
                    r'.*salt.*', r'.*signature.*'
                ],
                confidence=0.75,
                category="authentication"
            ),
            ClassificationRule(
                patterns=[
                    r'.*salary.*', r'.*income.*', r'.*wage.*',
                    r'.*compensation.*', r'.*payment.*'
                ],
                confidence=0.70,
                category="financial"
            ),
            # Lower confidence patterns that might indicate PII
            ClassificationRule(
                patterns=[
                    r'.*customer.*id.*', r'.*client.*id.*', r'.*user.*id.*',
                    r'.*person.*id.*', r'.*individual.*id.*'
                ],
                confidence=0.60,
                category="identifier"
            )
        ]
    
    def _init_sensitive_rules(self) -> List[ClassificationRule]:
        """Initialize sensitive data classification rules."""
        return [
            ClassificationRule(
                patterns=[
                    r'.*aml.*risk.*', r'.*suspicious.*', r'.*alert.*',
                    r'.*investigation.*', r'.*compliance.*score.*',
                    r'.*kyc.*', r'.*sanction.*', r'.*watchlist.*'
                ],
                confidence=0.90,
                category="aml_sensitive"
            ),
            ClassificationRule(
                patterns=[
                    r'.*transaction.*amount.*', r'.*transfer.*amount.*',
                    r'.*balance.*', r'.*limit.*', r'.*exposure.*'
                ],
                confidence=0.75,
                category="financial_sensitive"
            ),
            ClassificationRule(
                patterns=[
                    r'.*confidential.*', r'.*internal.*', r'.*restricted.*',
                    r'.*private.*', r'.*sensitive.*'
                ],
                confidence=0.80,
                category="general_sensitive"
            )
        ]
    
    def _normalize_column_name(self, column_name: str) -> str:
        """Normalize column name for pattern matching."""
        # Convert to lowercase and replace common separators
        normalized = column_name.lower()
        normalized = re.sub(r'[_\-\s]+', '_', normalized)
        return normalized
    
    def _check_rules(self, column_name: str, rules: List[ClassificationRule]) -> Dict[str, Any]:
        """Check column name against classification rules."""
        normalized = self._normalize_column_name(column_name)
        
        best_match = {
            "is_match": False,
            "confidence": 0.0,
            "category": None,
            "matched_pattern": None
        }
        
        for rule in rules:
            for pattern in rule.patterns:
                if re.search(pattern, normalized):
                    if rule.confidence > best_match["confidence"]:
                        best_match = {
                            "is_match": True,
                            "confidence": rule.confidence,
                            "category": rule.category,
                            "matched_pattern": pattern
                        }
                    break  # Found a match in this rule, no need to check other patterns
        
        return best_match
    
    def is_pii(self, column_name: str, threshold: float = 0.7) -> bool:
        """
        Determine if a column name likely contains PII.
        
        Args:
            column_name: The column name to classify
            threshold: Confidence threshold (0.0 to 1.0)
            
        Returns:
            True if column is likely PII, False otherwise
        """
        if not column_name:
            return False
        
        result = self._check_rules(column_name, self.pii_rules)
        is_pii = result["is_match"] and result["confidence"] >= threshold
        
        if is_pii:
            logger.debug(
                f"Column '{column_name}' classified as PII: "
                f"category={result['category']}, confidence={result['confidence']:.2f}, "
                f"pattern={result['matched_pattern']}"
            )
        
        return is_pii
    
    def is_sensitive(self, column_name: str, threshold: float = 0.7) -> bool:
        """
        Determine if a column name likely contains sensitive data.
        
        Args:
            column_name: The column name to classify
            threshold: Confidence threshold (0.0 to 1.0)
            
        Returns:
            True if column is likely sensitive, False otherwise
        """
        if not column_name:
            return False
        
        result = self._check_rules(column_name, self.sensitive_rules)
        is_sensitive = result["is_match"] and result["confidence"] >= threshold
        
        if is_sensitive:
            logger.debug(
                f"Column '{column_name}' classified as sensitive: "
                f"category={result['category']}, confidence={result['confidence']:.2f}, "
                f"pattern={result['matched_pattern']}"
            )
        
        return is_sensitive
    
    def classify_column(self, column_name: str) -> Dict[str, Any]:
        """
        Get full classification details for a column name.
        
        Args:
            column_name: The column name to classify
            
        Returns:
            Dictionary with classification details
        """
        if not column_name:
            return {
                "column_name": column_name,
                "is_pii": False,
                "is_sensitive": False,
                "pii_details": {"is_match": False},
                "sensitive_details": {"is_match": False}
            }
        
        pii_result = self._check_rules(column_name, self.pii_rules)
        sensitive_result = self._check_rules(column_name, self.sensitive_rules)
        
        return {
            "column_name": column_name,
            "is_pii": pii_result["is_match"] and pii_result["confidence"] >= 0.7,
            "is_sensitive": sensitive_result["is_match"] and sensitive_result["confidence"] >= 0.7,
            "pii_details": pii_result,
            "sensitive_details": sensitive_result
        }
    
    def batch_classify(self, column_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Classify multiple column names in batch.
        
        Args:
            column_names: List of column names to classify
            
        Returns:
            Dictionary mapping column names to classification results
        """
        results = {}
        
        for column_name in column_names:
            results[column_name] = self.classify_column(column_name)
        
        return results
    
    def get_classification_summary(self, column_names: List[str]) -> Dict[str, Any]:
        """
        Get summary statistics for a list of column names.
        
        Args:
            column_names: List of column names to analyze
            
        Returns:
            Summary statistics
        """
        classifications = self.batch_classify(column_names)
        
        pii_count = sum(1 for result in classifications.values() if result["is_pii"])
        sensitive_count = sum(1 for result in classifications.values() if result["is_sensitive"])
        
        pii_categories = {}
        sensitive_categories = {}
        
        for result in classifications.values():
            if result["is_pii"] and result["pii_details"]["category"]:
                cat = result["pii_details"]["category"]
                pii_categories[cat] = pii_categories.get(cat, 0) + 1
            
            if result["is_sensitive"] and result["sensitive_details"]["category"]:
                cat = result["sensitive_details"]["category"]
                sensitive_categories[cat] = sensitive_categories.get(cat, 0) + 1
        
        return {
            "total_columns": len(column_names),
            "pii_columns": pii_count,
            "sensitive_columns": sensitive_count,
            "pii_percentage": (pii_count / len(column_names)) * 100 if column_names else 0,
            "sensitive_percentage": (sensitive_count / len(column_names)) * 100 if column_names else 0,
            "pii_categories": pii_categories,
            "sensitive_categories": sensitive_categories,
            "classifications": classifications
        }