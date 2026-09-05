from __future__ import annotations
import json
import threading
from pathlib import Path
import sys
from typing import Any

BUILTIN_STYLES: list[dict[str, Any]] = [
    {"id":"normal","name":"Обычный","description":"Без дополнительной стилизации. Сохраняет естественную подачу.","prompt":"","builtin":True},
    {"id":"business","name":"Деловой","description":"Профессиональная, ясная и аккуратная формулировка.","prompt":"Сформулируй текст в профессиональном деловом стиле. Убери разговорные обороты и излишнюю эмоциональность, сохрани исходный смысл, факты и степень конкретности. Не добавляй новую информацию.","builtin":True},
    {"id":"short","name":"Короткий","description":"Максимально лаконично, без потери смысла.","prompt":"Сделай формулировку максимально краткой и ёмкой. Удали повторения, лишние слова и необязательные вводные конструкции, но не убирай важную информацию и не меняй смысл.","builtin":True},
    {"id":"natural","name":"Неардеталец","description":"Максимально близко к естественной манере речи.","prompt":"Сохрани естественную манеру речи автора. Не превращай текст в литературный или канцелярский. Исправляй только то, что мешает нормальному письменному восприятию: пунктуацию, явные оговорки, повторы и очевидные ошибки.","builtin":True},
    {"id":"friendly","name":"Дружелюбный","description":"Живой, естественный и доброжелательный тон.","prompt":"Сделай текст живым, естественным и доброжелательным. Избегай канцелярита и излишней формальности. Не добавляй новую информацию и не меняй смысл.","builtin":True},
    {"id":"technical","name":"Технический","description":"Точно, структурированно и без двусмысленности.","prompt":"Сформулируй текст в точном техническом стиле. Используй однозначные формулировки, сохраняй технические термины, числа, названия и последовательность действий. Не добавляй предположений или новой информации.","builtin":True},
]

def app_root() -> Path:
    if getattr(sys, "frozen", False): return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

def data_path(name: str) -> Path:
    path=app_root()/"data"; path.mkdir(parents=True,exist_ok=True); return path/name

class StyleStore:
    def __init__(self)->None:
        self.path=data_path("styles.json"); self._lock=threading.RLock(); self._ensure_file()
    def _save(self,data:dict[str,Any])->None:
        self.path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    def _ensure_file(self)->None:
        try:
            data=json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            if not isinstance(data,dict) or not isinstance(data.get("styles"),list): raise ValueError
        except Exception:
            self._save({"selected":"normal","styles":BUILTIN_STYLES})
    def load(self)->list[dict[str,Any]]:
        try:
            data=json.loads(self.path.read_text(encoding="utf-8")); styles=data.get("styles",[])
            return styles if isinstance(styles,list) else list(BUILTIN_STYLES)
        except Exception: return list(BUILTIN_STYLES)
    def get_selected_id(self)->str:
        try: return str(json.loads(self.path.read_text(encoding="utf-8")).get("selected","normal"))
        except Exception: return "normal"
    def get_selected(self)->dict[str,Any]:
        sid=self.get_selected_id()
        return next((s for s in self.load() if str(s.get("id"))==sid),BUILTIN_STYLES[0])
    def select(self,style_id:str)->bool:
        with self._lock:
            styles=self.load()
            if not any(str(s.get("id"))==style_id for s in styles): return False
            self._save({"selected":style_id,"styles":styles}); return True
    def add(self,name:str,description:str,prompt:str)->dict[str,Any]:
        name,description,prompt=name.strip(),description.strip(),prompt.strip()
        if not name: raise ValueError("Название стиля не может быть пустым.")
        if not prompt: raise ValueError("Инструкции стиля не могут быть пустыми.")
        with self._lock:
            styles=self.load(); base="".join(c.lower() if c.isalnum() else "-" for c in name).strip("-") or "style"
            ids={str(s.get("id")) for s in styles}; sid=base; n=2
            while sid in ids: sid=f"{base}-{n}"; n+=1
            style={"id":sid,"name":name,"description":description or "Пользовательский стиль.","prompt":prompt,"builtin":False}
            styles.append(style); self._save({"selected":sid,"styles":styles}); return style
    def delete(self,style_id:str)->bool:
        with self._lock:
            styles=self.load(); target=next((s for s in styles if str(s.get("id"))==style_id),None)
            if target is None or bool(target.get("builtin")): return False
            selected="normal" if self.get_selected_id()==style_id else self.get_selected_id()
            styles=[s for s in styles if str(s.get("id"))!=style_id]
            self._save({"selected":selected,"styles":styles}); return True
