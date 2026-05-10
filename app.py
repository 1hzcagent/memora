import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.auth import AuthManager
from core.knowledge_base import KnowledgeBaseManager
from core.agent import PersonalAgent
from utils.document_parser import parse_document, split_documents
from config import CHUNK_SIZE, CHUNK_OVERLAP

load_dotenv()

st.set_page_config(
    page_title="个人知识库智能助手",
    page_icon="🧠",
    layout="wide",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

def init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "kb_manager" not in st.session_state:
        st.session_state.kb_manager = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

def login_page():
    st.title("🧠 个人知识库智能助手")
    st.markdown("### 你的专属 AI 助手，拥有永久记忆能力")
    st.markdown("---")
    
    st.info("💡 **功能特色**：\n- 永久记忆：添加的知识永远不会遗忘\n- 智能回答：优先从你的知识库检索，没有则用 AI 知识\n- 安全私密：每个用户独立的知识库，密码保护\n- 随时更新：可以随时添加、删除知识库内容")
    
    tab1, tab2 = st.tabs(["🔐 用户登录", "📝 用户注册"])
    
    with tab1:
        st.subheader("欢迎回来，请登录你的账号")
        username = st.text_input("用户名", key="login_user")
        password = st.text_input("密码", type="password", key="login_pass")
        
        if st.button("登录", type="primary", use_container_width=True):
            if not username or not password:
                st.error("请输入用户名和密码")
                return
            
            auth = AuthManager()
            success, msg = auth.login(username, password)
            
            if success:
                st.session_state.authenticated = True
                st.session_state.username = username
                kb_path = auth.get_user_kb_path(username)
                
                st.session_state.kb_manager = KnowledgeBaseManager(username, kb_path)
                st.session_state.agent = PersonalAgent(username, st.session_state.kb_manager)
                st.session_state.messages = []
                st.rerun()
            else:
                st.error(msg)
    
    with tab2:
        st.subheader("创建新账号，开始使用")
        new_username = st.text_input("用户名", key="reg_user")
        new_password = st.text_input("密码", type="password", key="reg_pass")
        confirm_password = st.text_input("确认密码", type="password", key="reg_confirm")
        
        if st.button("注册", type="primary", use_container_width=True):
            if not new_username or not new_password:
                st.error("请输入用户名和密码")
                return
            
            if new_password != confirm_password:
                st.error("两次输入的密码不一致")
                return
            
            auth = AuthManager()
            success, msg = auth.register(new_username, new_password)
            
            if success:
                st.success("注册成功！请登录")
            else:
                st.error(msg)

def main_page():
    st.sidebar.title(f"👤 用户: {st.session_state.username}")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 退出登录", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.agent = None
        st.session_state.kb_manager = None
        st.session_state.messages = []
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 知识库状态")
    doc_count = st.session_state.kb_manager.get_document_count()
    st.sidebar.metric("知识源数量", doc_count)
    
    menu = st.sidebar.radio("📌 导航菜单", ["💬 智能对话", "📚 知识库管理"])
    
    if menu == "💬 智能对话":
        chat_page()
    else:
        kb_management_page()

def chat_page():
    st.header("💬 智能对话")
    st.markdown("向你的个人助手提问，它会先从你的知识库中查找信息，没有则用自身知识回答")
    
    if st.session_state.agent is None:
        st.error("请先登录")
        return
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "source" in msg:
                st.caption(msg["source"])
    
    if prompt := st.chat_input("输入你的问题..."):
        with st.chat_message("user"):
            st.write(prompt)
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            with st.spinner("🤔 正在思考..."):
                answer, has_kb = st.session_state.agent.query(prompt)
                st.write(answer)
                
                if has_kb:
                    st.caption("📖 回答来源：已结合你的个人知识库")
                else:
                    st.caption("💡 回答来源：个人知识库中无相关信息，使用 AI 通用知识")
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "source": "📖 已结合个人知识库回答" if has_kb else "💡 通用知识回答"
                })
    
    if st.session_state.messages:
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ 清空对话", use_container_width=True):
                st.session_state.agent.clear_history()
                st.session_state.messages = []
                st.rerun()

def kb_management_page():
    st.header("📚 知识库管理")
    st.markdown("在这里添加、查看、删除你的知识，所有知识都会永久保存")
    
    if st.session_state.kb_manager is None:
        st.error("请先登录")
        return
    
    tab1, tab2, tab3 = st.tabs(["✏️ 添加文本知识", "📄 上传文档", "📋 查看与管理知识库"])
    
    with tab1:
        st.subheader("添加文本知识")
        st.info("输入你想让 AI 助手记住的信息，例如个人信息、业务规则、产品说明等")
        
        text_content = st.text_area(
            "输入知识内容",
            height=200,
            placeholder="例如：我们公司的办公地址是北京市朝阳区xxx路xxx号，工作时间是周一到周五9:00-18:00..."
        )
        source_name = st.text_input("知识来源标签（方便以后查找）", value=f"文本_{st.session_state.username}")
        
        if st.button("✅ 添加到知识库", type="primary"):
            if not text_content.strip():
                st.error("请输入内容")
                return
            
            from langchain_core.documents import Document
            doc = Document(
                page_content=text_content,
                metadata={"source": source_name, "user": st.session_state.username}
            )
            
            try:
                count = st.session_state.kb_manager.add_documents([doc], source_name)
                st.success(f"✅ 成功添加 {count} 条知识到永久记忆，AI 现在能记住这些信息了！")
            except Exception as e:
                st.error(f"添加失败: {str(e)}")
    
    with tab2:
        st.subheader("上传文档到知识库")
        st.info("支持上传 PDF、Word、TXT、Excel 文档，AI 会自动解析并添加到知识库")
        
        uploaded_file = st.file_uploader(
            "选择文件上传",
            type=["pdf", "docx", "doc", "txt", "xlsx"],
            key="doc_uploader"
        )
        
        source_name = st.text_input("知识来源标签", value="上传的文档")
        
        if uploaded_file and st.button("📤 上传并解析", type="primary"):
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = Path(tmpdir) / uploaded_file.name
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                try:
                    with st.spinner("正在解析文档..."):
                        documents = parse_document(file_path)
                        chunks = split_documents(documents, CHUNK_SIZE, CHUNK_OVERLAP)
                        
                        count = st.session_state.kb_manager.add_documents(chunks, source_name)
                        st.success(f"✅ 文档解析成功！共添加 {count} 条知识到永久记忆")
                except Exception as e:
                    st.error(f"文档解析失败: {str(e)}")
    
    with tab3:
        st.subheader("我的知识库")
        
        docs = st.session_state.kb_manager.list_documents()
        
        if not docs:
            st.info("知识库还是空的，快去添加一些知识吧！")
        else:
            st.success(f"你的知识库共有 {len(docs)} 个知识源")
            st.markdown("---")
            
            for doc in docs:
                with st.expander(f"📄 {doc['source']} （包含 {doc['count']} 条知识片段）"):
                    st.write(f"**知识来源**: {doc['source']}")
                    st.write(f"**知识条数**: {doc['count']} 条")
                    
                    col1, col2 = st.columns([3, 1])
                    with col2:
                        if st.button("🗑️ 删除", key=f"del_{doc['source']}"):
                            st.session_state.kb_manager.delete_document(doc['source'])
                            st.success(f"已删除知识源：{doc['source']}")
                            st.rerun()

if __name__ == "__main__":
    init_session()
    
    if st.session_state.authenticated:
        main_page()
    else:
        login_page()
