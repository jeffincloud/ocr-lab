from typing import Optional
from pydantic import BaseModel, Field


class PassportFields(BaseModel):
    surname: Optional[str] = None
    given_names: Optional[str] = None
    passport_number: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD")
    sex: Optional[str] = None
    date_of_issue: Optional[str] = Field(None, description="YYYY-MM-DD")
    date_of_expiry: Optional[str] = Field(None, description="YYYY-MM-DD")
    issuing_authority: Optional[str] = None
    mrz_line1: Optional[str] = None
    mrz_line2: Optional[str] = None


class TokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ExtractResponse(BaseModel):
    fields: PassportFields
    model: str
    # valid | invalid | missing | unparseable — MRZ check-digit result
    mrz_result: Optional[str] = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
