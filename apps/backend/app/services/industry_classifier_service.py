from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndustryClassification:
    industry_code: str
    industry_name: str
    source: str


class IndustryClassifierService:
    UNKNOWN = IndustryClassification(industry_code="unknown", industry_name="未知行业", source="fallback")

    INDUSTRY_ALIASES: dict[str, tuple[str, str]] = {
        "工程机械": ("construction_machinery", "工程机械"),
        "专用设备制造": ("construction_machinery", "工程机械"),
        "机械设备": ("construction_machinery", "工程机械"),
        "汽车零部件": ("auto_parts", "汽车零部件"),
        "汽车零部件制造": ("auto_parts", "汽车零部件"),
        "化工材料": ("chemical_materials", "化工材料"),
        "化工新材料": ("chemical_materials", "化工材料"),
        "消费电子制造": ("consumer_electronics", "消费电子制造"),
        "电子元器件制造": ("consumer_electronics", "消费电子制造"),
        "工业自动化": ("industrial_automation", "工业自动化"),
        "工业控制设备": ("industrial_automation", "工业自动化"),
        "制造业": ("manufacturing", "制造业"),
        "软件服务": ("software_service", "软件服务"),
        "专业服务": ("professional_service", "专业服务"),
        "互联网平台": ("internet_platform", "互联网平台"),
    }

    def classify(self, enterprise: Any | None = None, *, industry_tag: str | None = None, sub_industry: str | None = None) -> IndustryClassification:
        profile = self._metadata_industry(enterprise)
        if profile is not None:
            return profile

        tag = industry_tag if industry_tag is not None else getattr(enterprise, "industry_tag", None)
        sub = sub_industry if sub_industry is not None else getattr(enterprise, "sub_industry", None)
        for value in (sub, tag):
            normalized = self._normalize(value)
            if normalized in self.INDUSTRY_ALIASES:
                code, name = self.INDUSTRY_ALIASES[normalized]
                return IndustryClassification(industry_code=code, industry_name=name, source="mapping")
        return self.UNKNOWN

    def _metadata_industry(self, enterprise: Any | None) -> IndustryClassification | None:
        if enterprise is None:
            return None
        metadata = getattr(enterprise, "metadata_json", None)
        if not isinstance(metadata, dict):
            metadata = getattr(enterprise, "portrait", None)
        if not isinstance(metadata, dict):
            return None
        code = str(metadata.get("industry_code") or metadata.get("normalized_industry_code") or "").strip()
        if not code:
            return None
        name = str(metadata.get("industry_name") or metadata.get("normalized_industry_name") or code).strip()
        return IndustryClassification(industry_code=code, industry_name=name, source="metadata")

    def _normalize(self, value: str | None) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return re.sub(r"\s+", "", text)
