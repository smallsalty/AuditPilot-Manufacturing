from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models import EnterpriseProfile
from app.services.industry_classifier_service import IndustryClassification, IndustryClassifierService


@dataclass(frozen=True)
class IndustryReference:
    industry_name: str
    industry_level: str
    fallback_used: bool
    industry_code: str
    original_industry: str
    rank: int


class IndustryTaxonomyService:
    MANUFACTURING_NAME = "制造业"
    BROAD_NAMES = {"制造业", "未知行业", "其他", "其他制造"}
    SIMILAR_INDUSTRY_MAP = {
        "半导体设备": ["专用设备", "电子设备", "工业自动化"],
        "汽车零部件": ["汽车整车", "机械设备", "橡胶塑料"],
        "医疗器械": ["医药制造", "专用设备", "生物医药"],
        "化工新材料": ["基础化工", "新材料", "塑料制品"],
        "工程机械": ["专用设备", "机械设备", "通用设备"],
        "工业自动化": ["专用设备", "机械设备", "仪器仪表"],
    }
    PARENT_INDUSTRY_MAP = {
        "半导体设备": [("专用设备", "secondary"), ("机械设备", "primary")],
        "专用设备": [("机械设备", "primary")],
        "工程机械": [("专用设备", "secondary"), ("机械设备", "primary")],
        "工业自动化": [("专用设备", "secondary"), ("机械设备", "primary")],
        "汽车零部件": [("汽车", "secondary"), ("汽车制造", "primary")],
        "医疗器械": [("医药制造", "secondary"), ("制造业", "manufacturing")],
        "化工新材料": [("基础化工", "secondary"), ("化学原料和化学制品制造业", "primary")],
        "消费电子": [("电子设备", "secondary"), ("计算机、通信和其他电子设备制造业", "primary")],
    }
    CLASSIFIER_FALLBACKS = {
        "construction_machinery": ["工程机械", "专用设备", "机械设备"],
        "auto_parts": ["汽车零部件", "汽车", "汽车制造"],
        "chemical_materials": ["化工新材料", "基础化工", "化学原料和化学制品制造业"],
        "consumer_electronics": ["消费电子", "电子设备", "计算机、通信和其他电子设备制造业"],
        "industrial_automation": ["工业自动化", "专用设备", "机械设备"],
        "food_beverage": ["食品饮料", "食品加工", "制造业"],
    }

    def __init__(self, classifier: IndustryClassifierService | None = None) -> None:
        self.classifier = classifier or IndustryClassifierService()

    def classify(self, enterprise: EnterpriseProfile) -> IndustryClassification:
        return self.classifier.classify(enterprise)

    def candidates(
        self,
        enterprise: EnterpriseProfile,
        classification: IndustryClassification | None = None,
    ) -> list[IndustryReference]:
        classification = classification or self.classify(enterprise)
        original = self.original_industry(enterprise, classification)
        names: list[tuple[str, str, bool]] = []

        if original and self._normalize(original) not in {self._normalize(name) for name in self.BROAD_NAMES}:
            names.append((original, "tertiary", False))

        for similar in self._similar_industries(original):
            names.append((similar, "adjacent", True))

        for parent_name, level in self._parent_industries(original):
            names.append((parent_name, level, True))

        for fallback in self.CLASSIFIER_FALLBACKS.get(classification.industry_code, []):
            level = "tertiary" if fallback == classification.industry_name else "secondary"
            names.append((fallback, level, fallback != original))

        if classification.industry_name:
            names.append((classification.industry_name, "secondary", classification.industry_name != original))

        names.append((self.MANUFACTURING_NAME, "manufacturing", True))
        return self._dedupe(names, original)

    def original_industry(self, enterprise: EnterpriseProfile, classification: IndustryClassification) -> str:
        metadata = self._metadata(enterprise)
        for key in ("akshare_industry", "normalized_industry_name", "industry_name", "sector"):
            value = str(metadata.get(key) or "").strip()
            if value:
                return value
        for value in (
            getattr(enterprise, "sub_industry", None),
            getattr(enterprise, "industry_tag", None),
            classification.industry_name,
        ):
            text = str(value or "").strip()
            if text:
                return text
        return classification.industry_name or self.MANUFACTURING_NAME

    def _similar_industries(self, original: str) -> list[str]:
        normalized_original = self._normalize(original)
        for key, values in self.SIMILAR_INDUSTRY_MAP.items():
            if self._normalize(key) == normalized_original:
                return values
        return []

    def _parent_industries(self, original: str) -> list[tuple[str, str]]:
        normalized_original = self._normalize(original)
        for key, values in self.PARENT_INDUSTRY_MAP.items():
            if self._normalize(key) == normalized_original:
                return values
        return []

    def _dedupe(self, names: list[tuple[str, str, bool]], original: str) -> list[IndustryReference]:
        references: list[IndustryReference] = []
        seen: set[tuple[str, str]] = set()
        for rank, (name, level, fallback_used) in enumerate(names):
            normalized = self._normalize(name)
            if not normalized:
                continue
            key = (normalized, level)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                IndustryReference(
                    industry_name=name,
                    industry_level=level,
                    fallback_used=bool(fallback_used or self._normalize(name) != self._normalize(original)),
                    industry_code=self.industry_code(name, level),
                    original_industry=original,
                    rank=len(references),
                )
            )
        return references

    @staticmethod
    def industry_code(name: str, level: str) -> str:
        normalized = IndustryTaxonomyService._normalize(name).lower()
        return f"{level}:{normalized or 'unknown'}"

    @staticmethod
    def _metadata(enterprise: EnterpriseProfile) -> dict[str, Any]:
        for attr in ("metadata_json", "portrait"):
            value = getattr(enterprise, attr, None)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _normalize(value: str | None) -> str:
        return re.sub(r"[\s（）()_\-/]+", "", str(value or "").strip()).upper()

