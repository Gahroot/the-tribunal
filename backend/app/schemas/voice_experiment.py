"""Bounded campaign voice experiments. Traits describe the chosen catalog voice."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VoiceVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    voice_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    gender: Literal["female", "male", "neutral"]
    accent: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9 ()-]+$")
    speed: float = Field(default=1.0, ge=0.7, le=1.2, allow_inf_nan=False)


class VoiceExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "grok", "elevenlabs", "live"]
    variants: list[VoiceVariant] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def unique_variants(self) -> "VoiceExperiment":
        if len({v.id for v in self.variants}) != len(self.variants):
            raise ValueError("Voice variant IDs must be unique")
        settings = {
            (
                v.voice_id if self.provider == "elevenlabs" else v.voice_id.lower(),
                v.speed,
                v.accent.strip().lower() if self.provider != "elevenlabs" else "catalog",
            )
            for v in self.variants
        }
        if len(settings) != len(self.variants):
            raise ValueError("Each variant must change the voice, speed, or supported accent")
        return self


class VoiceVariantResult(BaseModel):
    variant: VoiceVariant
    assigned_contacts: int
    converted_contacts: int
    conversion_rate: float


class VoiceExperimentResults(BaseModel):
    metric: Literal["campaign_appointment_booking"] = "campaign_appointment_booking"
    denominator: Literal["assigned_contacts"] = "assigned_contacts"
    variants: list[VoiceVariantResult] = Field(default_factory=list)
    # Deliberately no automatic winner: small samples are not proof of improvement.
