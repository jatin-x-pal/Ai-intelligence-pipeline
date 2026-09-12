"""Comprehensive tests for canonical Pydantic schemas.

Covers:
- Valid and invalid records for all entity types
- Required vs optional fields
- Fixed recordType enforcement
- Enum validations (e.g. PricingModel)
- Timezone-aware date parsing and naive rejection
- GitHub URL optionality and URL validation
- github_stars non-negative integer validation
- employeeCount optionality and validation
- EntityMapping confidence validation and audit logging
- JSON serialization and roundtrip deserialization
- Provenance / source preservation
"""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models import (
    EntityMapping,
    Job,
    JobContent,
    News,
    NewsContent,
    PricingModel,
    Product,
    ProductContent,
    ResearchPaper,
    ResearchPaperContent,
    SourceInfo,
    Startup,
    StartupContent,
    StartupData,
)


@pytest.fixture
def sample_utc_time() -> datetime:
    """Fixture providing a fixed UTC datetime."""
    return datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)


# =============================================================================
# 1. Base / SourceInfo Tests
# =============================================================================
class TestSourceInfo:
    """Tests for SourceInfo provenance model."""

    def test_valid_source_info(self) -> None:
        src = SourceInfo(name="TechCrunch", url="https://techcrunch.com/article1")
        assert src.name == "TechCrunch"
        assert src.url == "https://techcrunch.com/article1"

    def test_blank_source_name_fails(self) -> None:
        with pytest.raises(ValidationError, match="Source name cannot be blank"):
            SourceInfo(name="   ", url="https://example.com")

    def test_empty_source_name_fails(self) -> None:
        with pytest.raises(ValidationError):
            SourceInfo(name="", url="https://example.com")

    def test_invalid_source_url_fails(self) -> None:
        with pytest.raises(ValidationError, match="URL must start with http:// or https://"):
            SourceInfo(name="Site", url="ftp://invalid.url")

        with pytest.raises(ValidationError, match="URL must start with http:// or https://"):
            SourceInfo(name="Site", url="not_a_url")


# =============================================================================
# 2. Startup Model Tests
# =============================================================================
class TestStartupModel:
    """Tests for Startup canonical schema."""

    def test_valid_startup_with_employee_count(self, sample_utc_time: datetime) -> None:
        startup = Startup(
            schemaVersion="1.0",
            recordType="STARTUP",
            source=SourceInfo(name="Y Combinator", url="https://ycombinator.com/companies/openai"),
            content=StartupContent(
                entityName="OpenAI",
                data=StartupData(employeeCount=1000),
            ),
            collectedAt=sample_utc_time,
        )
        assert startup.schemaVersion == "1.0"
        assert startup.recordType == "STARTUP"
        assert startup.source.name == "Y Combinator"
        assert startup.content.entityName == "OpenAI"
        assert startup.content.data.employeeCount == 1000
        assert startup.collectedAt == sample_utc_time

    def test_valid_startup_with_optional_employee_count_as_none(
        self, sample_utc_time: datetime
    ) -> None:
        startup = Startup(
            source=SourceInfo(name="YC", url="https://yc.com"),
            content=StartupContent(
                entityName="NewCo",
                data=StartupData(employeeCount=None),
            ),
            collectedAt=sample_utc_time,
        )
        assert startup.content.data.employeeCount is None

    def test_startup_defaults(self, sample_utc_time: datetime) -> None:
        startup = Startup(
            source=SourceInfo(name="YC", url="https://yc.com"),
            content=StartupContent(entityName="NewCo"),
            collectedAt=sample_utc_time,
        )
        assert startup.schemaVersion == "1.0"
        assert startup.recordType == "STARTUP"
        assert startup.content.data.employeeCount is None

    def test_startup_fixed_record_type_enforced(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            Startup(
                recordType="INVALID_TYPE",  # type: ignore[arg-type]
                source=SourceInfo(name="YC", url="https://yc.com"),
                content=StartupContent(entityName="NewCo"),
                collectedAt=sample_utc_time,
            )

    def test_startup_missing_required_fields_fails(self) -> None:
        with pytest.raises(ValidationError):
            Startup()  # type: ignore[call-arg]

    def test_startup_negative_employee_count_fails(self) -> None:
        with pytest.raises(ValidationError):
            StartupData(employeeCount=-10)

    def test_startup_blank_entity_name_fails(self) -> None:
        with pytest.raises(ValidationError, match="Entity name cannot be blank"):
            StartupContent(entityName="   ")

    def test_startup_naive_datetime_rejected(self) -> None:
        naive_time = datetime(2026, 9, 10, 12, 0, 0)
        with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
            Startup(
                source=SourceInfo(name="YC", url="https://yc.com"),
                content=StartupContent(entityName="NewCo"),
                collectedAt=naive_time,
            )


# =============================================================================
# 3. Product Model Tests
# =============================================================================
class TestProductModel:
    """Tests for Product canonical schema and PricingModel enum."""

    @pytest.mark.parametrize("pricing", [PricingModel.FREE, PricingModel.FREEMIUM, PricingModel.PAID, PricingModel.ENTERPRISE])
    def test_valid_product_all_pricing_models(
        self, pricing: PricingModel, sample_utc_time: datetime
    ) -> None:
        product = Product(
            source=SourceInfo(name="ProductHunt", url="https://producthunt.com/products/ai-tool"),
            content=ProductContent(
                startupName="Anthropic",
                pricingModel=pricing,
            ),
            collectedAt=sample_utc_time,
        )
        assert product.content.pricingModel == pricing
        assert product.recordType == "PRODUCT"
        assert product.schemaVersion == "1.0"

    def test_product_accepts_string_pricing_model(self, sample_utc_time: datetime) -> None:
        product = Product(
            source=SourceInfo(name="Site", url="https://example.com"),
            content=ProductContent(
                startupName="Acme AI",
                pricingModel="FREEMIUM",  # type: ignore[arg-type]
            ),
            collectedAt=sample_utc_time,
        )
        assert product.content.pricingModel == PricingModel.FREEMIUM

    def test_product_invalid_pricing_model_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            Product(
                source=SourceInfo(name="Site", url="https://example.com"),
                content=ProductContent(
                    startupName="Acme AI",
                    pricingModel="SUPER_EXPENSIVE",  # type: ignore[arg-type]
                ),
                collectedAt=sample_utc_time,
            )

    def test_product_fixed_record_type_enforced(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            Product(
                recordType="STARTUP",  # type: ignore[arg-type]
                source=SourceInfo(name="Site", url="https://example.com"),
                content=ProductContent(
                    startupName="Acme AI",
                    pricingModel=PricingModel.FREE,
                ),
                collectedAt=sample_utc_time,
            )

    def test_product_blank_startup_name_fails(self) -> None:
        with pytest.raises(ValidationError, match="Startup name cannot be blank"):
            ProductContent(
                startupName="   ",
                pricingModel=PricingModel.PAID,
            )


# =============================================================================
# 4. ResearchPaper Model Tests
# =============================================================================
class TestResearchPaperModel:
    """Tests for ResearchPaper canonical schema."""

    def test_valid_research_paper_with_github_url(self, sample_utc_time: datetime) -> None:
        paper = ResearchPaper(
            content=ResearchPaperContent(
                title="Attention Is All You Need",
                authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
                paper_url="https://arxiv.org/abs/1706.03762",
                github_url="https://github.com/tensorflow/tensor2tensor",
                github_stars=15000,
                published_date=sample_utc_time,
            )
        )
        assert paper.schemaVersion == "1.0"
        assert paper.recordType == "RESEARCH_PAPER"
        assert paper.content.title == "Attention Is All You Need"
        assert len(paper.content.authors) == 3
        assert paper.content.github_url == "https://github.com/tensorflow/tensor2tensor"
        assert paper.content.github_stars == 15000
        assert paper.content.published_date == sample_utc_time

    def test_valid_research_paper_without_github_url(self, sample_utc_time: datetime) -> None:
        paper = ResearchPaper(
            content=ResearchPaperContent(
                title="Deep Residual Learning for Image Recognition",
                authors=["Kaiming He", "Xiangyu Zhang"],
                paper_url="https://arxiv.org/abs/1512.03385",
                github_url=None,
                github_stars=0,
                published_date=sample_utc_time,
            )
        )
        assert paper.content.github_url is None
        assert paper.content.github_stars == 0

    def test_research_paper_negative_stars_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            ResearchPaperContent(
                title="Some Paper",
                authors=["Author One"],
                paper_url="https://arxiv.org/abs/123",
                github_stars=-1,
                published_date=sample_utc_time,
            )

    def test_research_paper_non_integer_stars_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            ResearchPaperContent(
                title="Some Paper",
                authors=["Author One"],
                paper_url="https://arxiv.org/abs/123",
                github_stars="lots_of_stars",  # type: ignore[arg-type]
                published_date=sample_utc_time,
            )

    def test_research_paper_empty_authors_list_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            ResearchPaperContent(
                title="Paper Title",
                authors=[],
                paper_url="https://arxiv.org/abs/123",
                github_stars=0,
                published_date=sample_utc_time,
            )

    def test_research_paper_blank_author_name_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="at least one valid author name"):
            ResearchPaperContent(
                title="Paper Title",
                authors=["   ", ""],
                paper_url="https://arxiv.org/abs/123",
                github_stars=0,
                published_date=sample_utc_time,
            )

    def test_research_paper_invalid_paper_url_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="URL must start with http:// or https://"):
            ResearchPaperContent(
                title="Paper Title",
                authors=["Author One"],
                paper_url="not_a_valid_url",
                github_stars=0,
                published_date=sample_utc_time,
            )

    def test_research_paper_invalid_github_url_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="URL must start with http:// or https://"):
            ResearchPaperContent(
                title="Paper Title",
                authors=["Author One"],
                paper_url="https://arxiv.org/abs/123",
                github_url="invalid_github_url",
                github_stars=0,
                published_date=sample_utc_time,
            )

    def test_research_paper_naive_published_date_fails(self) -> None:
        with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
            ResearchPaperContent(
                title="Paper Title",
                authors=["Author One"],
                paper_url="https://arxiv.org/abs/123",
                github_stars=0,
                published_date=datetime(2026, 1, 1, 10, 0)
            )


# =============================================================================
# 5. Job Model Tests
# =============================================================================
class TestJobModel:
    """Tests for Job canonical schema."""

    def test_valid_job(self, sample_utc_time: datetime) -> None:
        job = Job(
            content=JobContent(
                company="Anthropic",
                date=sample_utc_time,
                is_remote=True,
                role_family="Engineering",
            )
        )
        assert job.schemaVersion == "1.0"
        assert job.recordType == "JOB"
        assert job.content.company == "Anthropic"
        assert job.content.is_remote is True
        assert job.content.role_family == "Engineering"
        assert job.content.date == sample_utc_time

    def test_job_fixed_record_type_enforced(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            Job(
                recordType="PRODUCT",  # type: ignore[arg-type]
                content=JobContent(
                    company="Anthropic",
                    date=sample_utc_time,
                    is_remote=False,
                    role_family="Research",
                ),
            )

    def test_job_blank_company_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="Company name cannot be blank"):
            JobContent(
                company="   ",
                date=sample_utc_time,
                is_remote=False,
                role_family="Engineering",
            )

    def test_job_blank_role_family_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="Role family cannot be blank"):
            JobContent(
                company="Anthropic",
                date=sample_utc_time,
                is_remote=False,
                role_family="  ",
            )

    def test_job_naive_date_fails(self) -> None:
        with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
            JobContent(
                company="Anthropic",
                date=datetime(2026, 9, 10, 0, 0, 0),
                is_remote=True,
                role_family="Engineering",
            )


# =============================================================================
# 6. News Model Tests
# =============================================================================
class TestNewsModel:
    """Tests for News canonical schema."""

    def test_valid_news(self, sample_utc_time: datetime) -> None:
        news = News(
            source=SourceInfo(name="VentureBeat", url="https://venturebeat.com"),
            content=NewsContent(
                title="New Frontier LLM Released",
                article_url="https://venturebeat.com/ai/frontier-llm",
                published_date=sample_utc_time,
                text="A groundbreaking model has just been unveiled.",
            ),
            collectedAt=sample_utc_time,
        )
        assert news.schemaVersion == "1.0"
        assert news.recordType == "NEWS"
        assert news.source.name == "VentureBeat"
        assert news.content.title == "New Frontier LLM Released"
        assert news.content.article_url == "https://venturebeat.com/ai/frontier-llm"
        assert news.content.published_date == sample_utc_time
        assert news.content.text == "A groundbreaking model has just been unveiled."
        assert news.collectedAt == sample_utc_time

    def test_news_fixed_record_type_enforced(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError):
            News(
                recordType="STARTUP",  # type: ignore[arg-type]
                source=SourceInfo(name="VentureBeat", url="https://venturebeat.com"),
                content=NewsContent(
                    title="Headline",
                    article_url="https://example.com/article",
                    published_date=sample_utc_time,
                    text="Body text",
                ),
                collectedAt=sample_utc_time,
            )

    def test_news_blank_title_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="Title cannot be blank"):
            NewsContent(
                title="   ",
                article_url="https://example.com",
                published_date=sample_utc_time,
                text="Text",
            )

    def test_news_blank_text_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="Article text cannot be blank"):
            NewsContent(
                title="Headline",
                article_url="https://example.com",
                published_date=sample_utc_time,
                text="   ",
            )

    def test_news_invalid_article_url_fails(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="URL must start with http:// or https://"):
            NewsContent(
                title="Headline",
                article_url="invalid_url",
                published_date=sample_utc_time,
                text="Body text",
            )

    def test_news_naive_dates_fail(self) -> None:
        naive_dt = datetime(2026, 9, 10, 10, 0, 0)
        with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
            NewsContent(
                title="Headline",
                article_url="https://example.com",
                published_date=naive_dt,
                text="Text",
            )


# =============================================================================
# 7. EntityMapping Model Tests
# =============================================================================
class TestEntityMappingModel:
    """Tests for EntityMapping log schema."""

    def test_valid_entity_mapping(self, sample_utc_time: datetime) -> None:
        mapping = EntityMapping(
            raw_name="Open AI, Inc.",
            canonical_name="OpenAI",
            entity_type="STARTUP",
            mapping_method="exact",
            confidence=1.0,
            source="Y Combinator",
            source_url="https://ycombinator.com/companies/openai",
            timestamp=sample_utc_time,
        )
        assert mapping.raw_name == "Open AI, Inc."
        assert mapping.canonical_name == "OpenAI"
        assert mapping.entity_type == "STARTUP"
        assert mapping.mapping_method == "exact"
        assert mapping.confidence == 1.0
        assert mapping.source == "Y Combinator"
        assert mapping.source_url == "https://ycombinator.com/companies/openai"
        assert mapping.timestamp == sample_utc_time

    def test_entity_mapping_confidence_bounds(self, sample_utc_time: datetime) -> None:
        # Confidence can be None (for deterministic lookups)
        m_none = EntityMapping(
            raw_name="OpenAI",
            canonical_name="OpenAI",
            entity_type="STARTUP",
            mapping_method="exact",
            confidence=None,
            source="SeedList",
            timestamp=sample_utc_time,
        )
        assert m_none.confidence is None

        # Confidence bounds [0.0, 1.0]
        with pytest.raises(ValidationError):
            EntityMapping(
                raw_name="OpenAI",
                canonical_name="OpenAI",
                entity_type="STARTUP",
                mapping_method="fuzzy",
                confidence=1.5,
                source="SeedList",
                timestamp=sample_utc_time,
            )

        with pytest.raises(ValidationError):
            EntityMapping(
                raw_name="OpenAI",
                canonical_name="OpenAI",
                entity_type="STARTUP",
                mapping_method="fuzzy",
                confidence=-0.1,
                source="SeedList",
                timestamp=sample_utc_time,
            )

    def test_entity_mapping_source_aliases(self, sample_utc_time: datetime) -> None:
        # Accepts 'source_info' when 'source' is not passed directly
        mapping = EntityMapping.model_validate({
            "raw_name": "DeepMind Technologies",
            "canonical_name": "Google DeepMind",
            "entity_type": "STARTUP",
            "mapping_method": "alias_dict",
            "confidence": 1.0,
            "source_info": "TechCrunch",
            "timestamp": sample_utc_time.isoformat(),
        })
        assert mapping.source == "TechCrunch"

    def test_entity_mapping_default_timestamp_is_utc_aware(self) -> None:
        mapping = EntityMapping(
            raw_name="Anthropic PBC",
            canonical_name="Anthropic",
            entity_type="STARTUP",
            mapping_method="rule_based",
            confidence=0.95,
            source="HackerNews",
        )
        assert mapping.timestamp is not None
        assert mapping.timestamp.tzinfo is not None

    def test_entity_mapping_blank_names_fail(self, sample_utc_time: datetime) -> None:
        with pytest.raises(ValidationError, match="raw_name cannot be blank"):
            EntityMapping(
                raw_name="   ",
                canonical_name="OpenAI",
                entity_type="STARTUP",
                mapping_method="exact",
                source="SeedList",
                timestamp=sample_utc_time,
            )

        with pytest.raises(ValidationError, match="canonical_name cannot be blank"):
            EntityMapping(
                raw_name="Open AI",
                canonical_name="   ",
                entity_type="STARTUP",
                mapping_method="exact",
                source="SeedList",
                timestamp=sample_utc_time,
            )


# =============================================================================
# 8. JSON Serialization and Deserialization Roundtrips
# =============================================================================
class TestJsonSerialization:
    """Tests JSON dump and load roundtrips for all models."""

    def test_startup_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = Startup(
            source=SourceInfo(name="Crunchbase", url="https://crunchbase.com/org/scale-ai"),
            content=StartupContent(
                entityName="Scale AI",
                data=StartupData(employeeCount=800),
            ),
            collectedAt=sample_utc_time,
        )
        json_data = original.model_dump_json()
        parsed = Startup.model_validate_json(json_data)
        assert parsed == original

        raw_dict = json.loads(json_data)
        assert raw_dict["schemaVersion"] == "1.0"
        assert raw_dict["recordType"] == "STARTUP"
        assert raw_dict["content"]["data"]["employeeCount"] == 800

    def test_product_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = Product(
            source=SourceInfo(name="ProductHunt", url="https://producthunt.com/posts/claude-3"),
            content=ProductContent(
                startupName="Anthropic",
                pricingModel=PricingModel.FREEMIUM,
            ),
            collectedAt=sample_utc_time,
        )
        json_data = original.model_dump_json()
        parsed = Product.model_validate_json(json_data)
        assert parsed == original

        raw_dict = json.loads(json_data)
        assert raw_dict["content"]["pricingModel"] == "FREEMIUM"

    def test_research_paper_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = ResearchPaper(
            content=ResearchPaperContent(
                title="Llama 3 Herd of Models",
                authors=["Meta AI"],
                paper_url="https://arxiv.org/abs/2407.21783",
                github_url="https://github.com/meta-llama/llama3",
                github_stars=45000,
                published_date=sample_utc_time,
            )
        )
        json_data = original.model_dump_json()
        parsed = ResearchPaper.model_validate_json(json_data)
        assert parsed == original

    def test_job_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = Job(
            content=JobContent(
                company="OpenAI",
                date=sample_utc_time,
                is_remote=True,
                role_family="Engineering",
            )
        )
        json_data = original.model_dump_json()
        parsed = Job.model_validate_json(json_data)
        assert parsed == original

    def test_news_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = News(
            source=SourceInfo(name="TechCrunch", url="https://techcrunch.com"),
            content=NewsContent(
                title="AI Startup Raises $100M",
                article_url="https://techcrunch.com/2026/09/ai-funding",
                published_date=sample_utc_time,
                text="The round was led by top venture capital firms.",
            ),
            collectedAt=sample_utc_time,
        )
        json_data = original.model_dump_json()
        parsed = News.model_validate_json(json_data)
        assert parsed == original

    def test_entity_mapping_json_roundtrip(self, sample_utc_time: datetime) -> None:
        original = EntityMapping(
            raw_name="Hugging Face, Inc.",
            canonical_name="Hugging Face",
            entity_type="STARTUP",
            mapping_method="exact",
            confidence=1.0,
            source="PapersWithCode",
            source_url="https://paperswithcode.com",
            timestamp=sample_utc_time,
        )
        json_data = original.model_dump_json()
        parsed = EntityMapping.model_validate_json(json_data)
        assert parsed == original
