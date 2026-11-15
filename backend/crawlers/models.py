from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class MovieEvent:
    """
    영화관 이벤트를 나타내는 공통 데이터 모델
    """

    id: str  # 고유 식별자 (예: cgv-12345)
    theater: str  # 영화관 (CGV, LOTTECINEMA, MEGABOX 등)
    title: str  # 이벤트 제목
    startDate: str  # 시작일 (YYYY-MM-DD HH:MM:SS)
    url: str  # 상세 페이지 URL
    imageUrl: Optional[str] = None  # 이미지 URL
    category: Optional[str] = None  # 카테고리 (필요 시)
    timeUnknown: bool = False  # 날짜만 확인되고 시작 시각은 알 수 없는 이벤트

    def to_dict(self):
        """객체를 딕셔너리로 변환 (JSON 저장용)"""
        return asdict(self)
