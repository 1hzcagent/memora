import os
import hashlib
import json
from pathlib import Path
from config import USER_DATA_DIR

class AuthManager:
    def __init__(self):
        self.users_file = USER_DATA_DIR / "users.json"
        self._load_users()
    
    def _load_users(self):
        if self.users_file.exists():
            with open(self.users_file, "r", encoding="utf-8") as f:
                self.users = json.load(f)
        else:
            self.users = {}
            self._save_users()
    
    def _save_users(self):
        with open(self.users_file, "w", encoding="utf-8") as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2)
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register(self, username, password):
        if username in self.users:
            return False, "用户已存在"
        
        self.users[username] = {
            "password_hash": self._hash_password(password),
            "created_at": str(__import__('datetime').datetime.now())
        }
        self._save_users()
        
        user_dir = USER_DATA_DIR / username
        user_dir.mkdir(exist_ok=True)
        
        return True, "注册成功"
    
    def login(self, username, password):
        if username not in self.users:
            return False, "用户不存在"
        
        if self.users[username]["password_hash"] != self._hash_password(password):
            return False, "密码错误"
        
        return True, "登录成功"
    
    def get_user_kb_path(self, username):
        return USER_DATA_DIR / username / "knowledge_base"
