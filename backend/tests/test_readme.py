from pathlib import Path


def test_readme_documents_local_run_and_limitations() -> None:
    content = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")

    required_sections = (
        "문제 정의",
        "샘플 데이터 초기화",
        "아키텍처",
        "데이터 모델",
        "납기 위험",
        "14일 안전재고",
        "백엔드 설치·실행",
        "프론트엔드 설치·실행",
        "화면 안내",
        "합성 데이터 기반 데모",
        "LOT/FIFO",
        "품질·설비",
        "AI 브리핑",
        "Docker",
    )
    for section in required_sections:
        assert section in content
