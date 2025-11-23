from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict

router = APIRouter(
    prefix="/ws",
    tags=["websockets"]
)

class ConnectionManager:
    def __init__(self):
        # Map document_id to list of WebSockets
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, doc_id: int):
        await websocket.accept()
        if doc_id not in self.active_connections:
            self.active_connections[doc_id] = []
        self.active_connections[doc_id].append(websocket)

    def disconnect(self, websocket: WebSocket, doc_id: int):
        if doc_id in self.active_connections:
            self.active_connections[doc_id].remove(websocket)
            if not self.active_connections[doc_id]:
                del self.active_connections[doc_id]

    async def broadcast(self, message: bytes, doc_id: int, sender: WebSocket):
        if doc_id in self.active_connections:
            for connection in self.active_connections[doc_id]:
                if connection != sender:
                    await connection.send_bytes(message)

manager = ConnectionManager()

@router.websocket("/documents/{doc_id}")
async def websocket_endpoint(websocket: WebSocket, doc_id: int):
    await manager.connect(websocket, doc_id)
    try:
        while True:
            data = await websocket.receive_bytes()
            # Broadcast the received data (e.g., Yjs updates) to other clients
            await manager.broadcast(data, doc_id, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, doc_id)
