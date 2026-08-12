from fastapi import FastAPI, HTTPException, Query, status

from matraix.vita.climate import SessionStore
from matraix.vita.models import (
    ConversationResponse,
    MessageRequest,
    MessageResponse,
    ReadyResponse,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Vita Climate Simulator")
    store = SessionStore()

    @app.get("/health", response_model=ReadyResponse)
    @app.get("/v1/health", response_model=ReadyResponse)
    def health() -> ReadyResponse:
        return ReadyResponse(status="ok", capabilities=("text_chat", "climate_control"))

    @app.get("/ready", response_model=ReadyResponse)
    @app.get("/v1/ready", response_model=ReadyResponse)
    def ready() -> ReadyResponse:
        return ReadyResponse(
            status="ready", capabilities=("text_chat", "climate_control")
        )

    @app.post("/v1/messages", response_model=MessageResponse)
    def post_message(payload: MessageRequest) -> MessageResponse:
        return store.handle_message(payload)

    @app.get("/v1/conversation", response_model=ConversationResponse)
    def get_conversation(
        session_id: str = Query(alias="sessionId", min_length=1),
    ) -> ConversationResponse:
        conversation = store.conversation(session_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vita session not found",
            )
        return conversation

    return app


app = create_app()
