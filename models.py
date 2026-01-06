from pydantic import BaseModel

class TrafficReportStatements(BaseModel):
    statements: list[str]
    

class TrafficReportStatementCategorization(BaseModel):
    statement: str
    reasoning: str
    category: str  # accident | delay | patrol | general warning

class TrafficReportCategorizationResponse(BaseModel):
    categorizations: list[TrafficReportStatementCategorization]
    

class TrafficReportResponse(BaseModel):
    recording_name: str
    transcription: str
    statements: list[TrafficReportStatementCategorization]
    created_at: str | None = None
    
class TrafficReportDataStorageModel(BaseModel):
    transcription: str
    statements: list[TrafficReportStatementCategorization]