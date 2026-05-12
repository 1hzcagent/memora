import os
import json
import tempfile
import uuid
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from core.auth import AuthManager
from core.knowledge_base import KnowledgeBaseManager
from core.agent import PersonalAgent
from utils.document_parser import parse_document, split_documents
from config import CHUNK_SIZE, CHUNK_OVERLAP, DASHSCOPE_API_KEY

app = FastAPI(title="个人知识库智能助手")

app.state.sessions = {}
app.state.auth = AuthManager()

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

class AddTextRequest(BaseModel):
    content: str
    source_name: str = "text_input"

def get_session(x_session_id: str = Header(None)):
    if not x_session_id or x_session_id not in app.state.sessions:
        raise HTTPException(status_code=401, detail="未登录")
    return app.state.sessions[x_session_id]

@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = Path(__file__).parent / "static" / "index.html"
    return html_file.read_text(encoding="utf-8")

@app.post("/api/register")
async def register(req: RegisterRequest):
    if not req.username or not req.password:
        return JSONResponse({"success": False, "message": "请输入用户名和密码"})
    success, msg = app.state.auth.register(req.username, req.password)
    return JSONResponse({"success": success, "message": msg})

@app.post("/api/login")
async def login(req: LoginRequest):
    if not req.username or not req.password:
        return JSONResponse({"success": False, "message": "请输入用户名和密码"})
    success, msg = app.state.auth.login(req.username, req.password)
    if not success:
        return JSONResponse({"success": False, "message": msg})
    kb_path = app.state.auth.get_user_kb_path(req.username)
    kb_manager = KnowledgeBaseManager(req.username, kb_path)
    agent = PersonalAgent(req.username, kb_manager)
    session_id = str(uuid.uuid4())
    app.state.sessions[session_id] = {"username": req.username, "kb_manager": kb_manager, "agent": agent}
    return JSONResponse({"success": True, "message": "登录成功", "session_id": session_id})

@app.get("/api/kb_status")
async def kb_status(x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    kb_manager = sess["kb_manager"]
    return JSONResponse({"doc_count": kb_manager.get_document_count(), "documents": kb_manager.list_documents()})

@app.post("/api/chat")
async def chat(req: ChatRequest, x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    agent = sess["agent"]
    
    async def generate():
        flags = {}
        async for chunk in agent.query_stream(req.message):
            if isinstance(chunk, bool):
                if 'kb' not in flags:
                    flags['kb'] = chunk
                else:
                    flags['search'] = chunk
                yield f"data: {json.dumps({'from_knowledge_base': flags.get('kb', False), 'from_search': flags.get('search', False)})}\n\n"
            else:
                yield f"data: {json.dumps({'content': chunk})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/add_text")
async def add_text(req: AddTextRequest, x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    kb_manager = sess["kb_manager"]
    from langchain_core.documents import Document
    doc = Document(page_content=req.content, metadata={"source": req.source_name, "user": sess["username"]})
    try:
        count = kb_manager.add_documents([doc], req.source_name)
        return JSONResponse({"success": True, "message": f"成功添加 {count} 条知识到永久记忆"})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"添加失败: {str(e)}"})

@app.post("/api/upload_document")
async def upload_document(file: UploadFile = File(...), source_name: str = Form("uploaded_doc"), x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    kb_manager = sess["kb_manager"]
    try:
        content = await file.read()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / file.filename
            with open(file_path, "wb") as f:
                f.write(content)
            documents = parse_document(file_path)
            chunks = split_documents(documents, CHUNK_SIZE, CHUNK_OVERLAP)
            count = kb_manager.add_documents(chunks, source_name)
            return JSONResponse({"success": True, "message": f"成功解析并添加 {count} 条知识到永久记忆"})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"文档解析失败: {str(e)}"})

@app.post("/api/delete_document")
async def delete_document(source_name: str, x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    kb_manager = sess["kb_manager"]
    try:
        success = kb_manager.delete_document(source_name)
        if success:
            return JSONResponse({"success": True, "message": f"已删除: {source_name}"})
        else:
            return JSONResponse({"success": False, "message": "未找到该文档"})
    except Exception as e:
        print(f"删除文档出错: {e}")
        return JSONResponse({"success": False, "message": f"删除失败: {str(e)}"})

@app.post("/api/logout")
async def logout(x_session_id: str = Header(None)):
    if x_session_id and x_session_id in app.state.sessions:
        del app.state.sessions[x_session_id]
    return JSONResponse({"success": True})

@app.get("/api/clear_chat")
async def clear_chat(x_session_id: str = Header(None)):
    sess = get_session(x_session_id)
    sess["agent"].clear_history()
    return JSONResponse({"success": True})
