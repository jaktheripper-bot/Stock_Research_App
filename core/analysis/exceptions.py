"""Custom exception hierarchy for equity research ingestion and pipeline processing."""

class PipelineError(Exception):
    def __init__(self, stage: str, message: str, technical_details: str = ""):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.technical_details = technical_details

class TickerResolutionError(PipelineError):
    def __init__(self, query: str):
        super().__init__(
            stage="Ticker Resolution",
            message=f"Could not resolve an official BSE scrip code for '{query}'.",
            technical_details="Evaluated static map, Supabase master universe, and JIT AI discovery. Zero active quotes confirmed."
        )

class ExchangeDataFetchError(PipelineError):
    def __init__(self, scrip: str, detail: str):
        super().__init__(
            stage="Exchange Data Ingestion",
            message=f"BSE exchange rejected or failed to return quote data for scrip {scrip}.",
            technical_details=detail
        )
